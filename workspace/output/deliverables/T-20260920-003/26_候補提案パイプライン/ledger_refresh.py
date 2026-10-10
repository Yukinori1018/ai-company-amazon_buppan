#!/usr/bin/env python3
"""商品判定台帳（Googleスプレッドシート）を最新の採点で引き直し、足りない行を足す。

社長指示（2026-10-10 夜）の要旨:
  「取引できる卸から仕入れられる商品を必ず台帳に加えろ。SD も加えろ。
    仕入れられない商品も載せてよいが、満たさない基準を明示し、
    『こう変えれば仕入れられる』というコメントを付けろ。」

やること（この順）
  1. NETSEA 側：旧プール(10/04)＋新規逆引き(10/09) を score_20261004 で採点し直す
     （Keepa は叩かない。手元の取得済みデータだけで再計算＝トークン0・§3.3-21）
  2. 10/09 のゲート実機確認（restrictions/approve）の結果を反映する
  3. SD 側：sd_candidates_private.csv（SD 起点 375行）を ASIN 単位で1行にして足す。
     カズヨが社長の Chrome で読んだ卸価格（sd_price_manual_20261010.csv）があれば採算を確定する。
     **SD への自動取得はしない**（CLAUDE.md §3.3-14・18）
  4. 判定理由を「未達（§3.5 の項目番号）／こう変えれば／人が見る項目」の3段に揃える
  5. 機械判定が全部通った行も GO にしない。**人の実画面確認（キーゾン・カート）が済むまで
     UNKNOWN**（§3.3-16）。判定理由に「機械判定は通過・実画面確認待ち」と書く

守ること
  - 列の追加・削除・様式変更はしない。値の更新と行の追記だけ
  - 「確認者」が人（カズヨ）の行は**一切上書きしない**（§3.3-16）
  - 卸値・卸率・購入先URL は**シートにだけ**書く。このスクリプトは値を持たない（PUBLIC リポ）
  - 捨てない。NO-GO も理由つきで残す

規定と実装のずれ（2026-10-10 タカシが発見。ここで規定側に合わせて読み替える）
  - 実売：実装は「ランク 30万位より下で FAIL」。§3.3-8 は「10万〜50万位は UNKNOWN、
    50万位より下で NO-GO」。→ 30万〜50万位の FAIL は UNKNOWN（キーゾンで決める）に読み替える
  - 採算：実装の C は「中央値で利益率20%未満かつ手残り400円未満」。§3.5 #18 の C は
    「中央値で利益率5%未満かつ手残り400円未満」。→ 中央値5%以上の C は B（最小ロットで1回）
    に読み替える
  どちらも判定理由に「（§…による読み替え・実装は FAIL/C）」と明記する。

使い方
  python3 ledger_refresh.py --dry-run     # シートに書かず、集計と差分だけ出す
  python3 ledger_refresh.py               # シートへ書く（書く前の全値を before_*.json に退避）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
BUY = WORK / "buylist20261009"
SDB = WORK / "sd_buylist20261009"
OUT = WORK / "ledger20261010"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))
sys.path.insert(0, str(BUY))

import score_20261004 as S     # noqa: E402
import fba_cost                # noqa: E402
sys.path.insert(0, str(REPO / "scripts/sourcing_gate"))
import consistency as K        # noqa: E402

WAIT_FULL: list[dict] = []     # 実画面確認待ち（NETSEA）の全列。autofill.py に渡す


def consistency_gate(s: dict, comp: dict) -> dict:
    """実画面確認待ちに上げる前に、算術を consistency.py（§3.3-17）で検算する。
    崩れていたら待ちに上げず、理由を書いて UNKNOWN に留める（数字は直さない）。"""
    if not comp["waiting"]:
        return comp
    row = S.as_row(s, full=True)
    res = K.check_row(row)
    if res.ok:
        WAIT_FULL.append(row)
        return comp
    msg = " ／ ".join(clean(f.line(), 80) for f in res.blocking[:3])
    comp = dict(comp)
    comp["waiting"] = False
    comp["verdict"] = "UNKNOWN"
    comp["reason"] = (f"整合性検査 NG（§3.3-17・採算の数字は信用しない）：{msg} ／"
                      f"【こう変えれば】卸と Amazon の画面で単位・売価を人が確かめれば決まる ／ "
                      + comp["reason"])[:1800]
    return comp

SHEET_ID = "1ppyXCnp2S_9Xwi3vJHGOT6iJCfsEqt88n30aqUFtX3I"
CRED = Path.home() / ".config/claude-session-sheets/credentials.json"
TICKET = "T-20260920-003"
TODAY = date.today().isoformat()
SD_MANUAL = SDB / "sd_price_manual_20261010.csv"

#: score_20261004 のゲート名 → CLAUDE.md §3.5 の項目番号
ITEM = {
    "価格の動き": "#13-14 販売価格・価格の傾き",
    "カート保持者": "#5 カートの販売元",
    "実売": "#9 実売",
    "仕入れ": "#17 卸の在庫",
    "セット数": "#15 Amazon側のセット構成",
    "採算": "#18 採算等級",
    "季節の窓": "#11 季節の窓",
    "取り直し": "#13 価格データ",
    "取引条件": "#4 仕入れ先の Amazon 出品可否",
    "Amazonカタログ": "#16 カタログJAN",
    "ゲート": "#1-2 出品許可",
}
HUMAN_ITEMS_BASE = ["#9 キーゾンで3か月の実数（型番ごと）",
                    "#5 カートの販売元を実画面で読む",
                    "#7 新品出品者の内訳（出品一覧）"]


def clean(t: str, n: int = 90) -> str:
    t = re.sub(r"\*\*|`", "", t or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def yen(x) -> str:
    return f"{int(round(x)):,}円"


# ── NETSEA 側の採点（make_list.py と同じ母集団・同じ採点）──────────────────

def score_netsea() -> list[dict]:
    import score_new  # buylist20261009/
    old = S.score_all()
    for s in old:
        s["_src"] = "旧プール(10/04)"
    new_rows = json.loads((BUY / "new_rows.json").read_text())
    prods = score_new.load_products()
    idx = json.loads((WORK / "pipeline/netsea_jan_index.json").read_text())["jans"]
    names = json.loads((WORK / "pipeline/seller_names.json").read_text())
    rc: Counter = Counter()
    for p in prods.values():
        cur = (p.get("stats") or {}).get("current") or []
        if len(cur) > 3 and cur[3] and cur[3] > 0:
            rc[cur[3]] += 1
    new = []
    for a, r in new_rows.items():
        s = S.build(r, {"fba_yen": r.get("_fba_yen") or None}, prods[a], idx, names,
                    "2026-10-01", None, dict(rc))
        s["_src"] = "新規逆引き(10/09)"
        s["_supplier_url"] = r.get("_supplier_url")
        new.append(s)
    return old + new


def load_gate_checks() -> dict[str, dict]:
    p = BUY / "gate_check_20261009.csv"
    return {r["ASIN"]: r for r in csv.DictReader(p.open(encoding="utf-8-sig"))}


def reread_gates(s: dict) -> list[tuple[str, str, str, str]]:
    """(ゲート, 状態, 理由, 読み替えの注記)。§3.3-8 / §3.5 #18 に合わせて読み替える。"""
    out = []
    e = s.get("econ")
    for name, st, why in s["gates"]:
        note = ""
        # 2026-10-11：実売（§3.3-8）と採算 B（§3.5 #18）の読み替えは、ライブラリ本体
        # （score_20261004.velocity_of / fba_cost.grade）を規定に合わせて直したので撤去した。
        if name == "採算" and st == "FAIL" and e and e.grade in ("A", "B") \
                and e.order_total > S.MAX_ORDER_TOTAL_YEN:
            st, note = "PASS", (f"等級 {e.grade}。発注額 {yen(e.order_total)} が1SKU枠を超えるだけ"
                                f"＝最小ロットに減らせば枠内（§3.5 B は最小ロットで1回）")
        out.append((name, st, why, note))
    return out


def fix_for(name: str, st: str, why: str, s: dict) -> tuple[str, bool]:
    """(こう変えれば, 変えようがないか)。"""
    e = s.get("econ")
    if name == "カート保持者" and st == "FAIL":
        return "変えようがない：Amazon 本体がカート（値下げしても取れない・§3.3-1）", True
    if name == "カート保持者":
        return "実画面でカートの販売元を読めば決まる（カート不在なら出品者の内訳を見る）", False
    if name == "実売" and st == "FAIL":
        sea = s.get("season")
        if sea and sea.peak_months:
            pk = "・".join(f"{m}月" for m in sea.peak_months)
            return f"通年では売れていない。ピーク {pk} の2か月前に再判定すれば拾える可能性", False
        return f"変えようがない：売れている根拠がない（{clean(why, 50)}）", True
    if name == "実売":
        return "キーゾンで3か月の実数を見れば決まる（月3個以上の取り分があれば可）", False
    if name == "価格の動き" and st == "FAIL":
        return "下落が止まり、90日の後半が前半比-5%以内に戻れば再判定で通る", False
    if name in ("価格の動き", "取り直し"):
        return "実画面で売価（カート価格）を確認すれば採算を計算できる", False
    if name == "仕入れ" and st == "FAIL":
        return "NETSEA 品切れ。再入荷か、SD 等で同一 JAN を探せば可", False
    if name == "仕入れ":
        return "卸サイトで同一 JAN の在庫・卸値を確認すれば決まる", False
    if name == "セット数":
        return "Amazon と卸の画面で「Amazon1個＝卸何点」を人が確認すれば採算を計算できる", False
    if name == "季節の窓":
        sea = s.get("season")
        pk = "・".join(f"{m}月" for m in (sea.peak_months if sea else ())) or "ピーク"
        return f"今季は間に合わない。{pk}の2〜3か月前に発注すれば窓に入る", False
    if name == "採算":
        return fix_profit(s), False
    return "人が確認すれば決まる", False


def fix_profit(s: dict) -> str:
    e = s.get("econ")
    if not e:
        lv = s.get("price")
        miss = []
        if not (lv and lv.sell_for_profit):
            miss.append("売価（実画面）")
        if not s.get("per_pt"):
            miss.append("卸の1点単価")
        if not s.get("n_set"):
            miss.append("セット数")
        return (f"{'・'.join(miss) or 'FBA手数料'}が決まれば計算できる"
                if miss else "FBA 手数料（サイズ区分）が決まれば計算できる")
    if e.grade not in ("A", "B", "C"):
        return "寸法が分かればサイズ区分が決まり計算できる（セラセンの商品登録画面で確認）"
    if e.cost_ratio_pct < S.MIN_PLAUSIBLE_COST_RATIO:
        return (f"卸率{e.cost_ratio_pct}%は低すぎる＝単位ずれか終売の疑い。"
                f"卸と Amazon の画面で単位を確かめれば決まる")
    base = e.sell - e.referral_fee_yen - e.fba_yen - e.other_unit_costs
    cap = max(base - e.sell * 0.05, base - fba_cost.MIN_PROFIT_YEN)   # §3.5 B の原価上限
    n = s.get("n_set") or 1
    parts = []
    if cap > 0:
        per_pt_excl = cap / n / 1.1
        now_pt = (s.get("per_pt") or e.unit_cost_incl / n) / 1.1
        parts.append(f"卸1点 {yen(per_pt_excl)}（税抜）以下なら B（いま {yen(now_pt)}）")
    else:
        parts.append(f"売価 {yen(e.sell)} では原価0円でも利益率5%に届かない")
    tier = e.size_tier
    if tier:
        need = fba_cost.required_sell(e.unit_cost_incl, tier, 0.05,
                                      category=s.get("category"))
        if need:
            parts.append(f"売価 {yen(need)} 以上の棚なら B")
        try:
            bn, btxt = fba_cost.bundle_advice(tier, e.sell / n, e.unit_cost_incl / n,
                                              category=s.get("category"))
            if bn and bn > 1:
                parts.append(f"セット組 {bn}個なら固定費が割れる（{clean(btxt, 60)}）")
        except Exception:
            pass
    if e.cliff_note:
        parts.append(clean(e.cliff_note, 70))
    return "／".join(parts)


def compose_netsea(s: dict, gate: dict | None) -> dict:
    gates = reread_gates(s)
    if gate:
        if gate["ゲート判定"] == "NG":
            gates.append(("ゲート", "FAIL", gate["根拠"], ""))
        else:
            gates.append(("ゲート", "PASS", gate["根拠"], ""))
    miss = [(n, st, w, nt) for n, st, w, nt in gates if st != "PASS"]
    lines_miss, fixes, never = [], [], []
    for n, st, w, nt in miss:
        lines_miss.append(f"{ITEM.get(n, n)} {st}：{clean(w, 70)}" + (f"（{nt}）" if nt else ""))
        if n == "ゲート":
            never.append("変えようがない：新品の申請経路が無い（§3.3-25）")
            continue
        if n == "採算" and st == "UNKNOWN" and any(
                x[0] in ("価格の動き", "セット数", "取り直し") and x[1] != "PASS" for x in gates):
            continue  # 売価・セット数の側で「こう変えれば」を書いている（重複させない）
        f, nv = fix_for(n, st, w, s)
        (never if nv else fixes).append(f)
    adj = [nt for n, st, w, nt in gates if st == "PASS" and nt]
    sts = [st for _, st, _, _ in gates]
    machine = "NO-GO" if "FAIL" in sts else ("UNKNOWN" if "UNKNOWN" in sts else "GO")
    if s.get("pinned"):
        machine = "NO-GO"
    human = []
    if not (s.get("monthlySold")):
        human.append(HUMAN_ITEMS_BASE[0])
    human += HUMAN_ITEMS_BASE[1:]
    if not gate:
        human.append("#1-2 ゲート（restrictions/approve）")
    human.append("#4 仕入れ先の Amazon 出品可否")
    waiting = False
    if machine == "GO":
        verdict, waiting = "UNKNOWN", True
        head = "機械判定は通過・実画面確認待ち"
        reason = (f"{head}。" + (f"読み替え：{' ／ '.join(adj)}。" if adj else "")
                  + f"人が見る項目：{'・'.join(human)}")
    else:
        verdict = machine
        reason = "未達：" + " ／ ".join(lines_miss)
        if never:
            reason += " ／【こう変えれば】" + never[0]
        else:
            reason += " ／【こう変えれば】" + " ／ ".join(dict.fromkeys(fixes))
        if machine == "UNKNOWN" and not never:
            only_human = all(n in ("実売", "カート保持者") for n, *_ in miss)
            if only_human:
                waiting = True
                reason = ("機械判定は通過・実画面確認待ち（残りは人が見れば決まる項目だけ）。"
                          + reason)
        if adj:
            reason += " ／ 読み替え：" + " ／ ".join(adj)
    return {"verdict": verdict, "reason": reason[:1800], "waiting": waiting,
            "gates": gates}


def netsea_cells(s: dict, gate: dict | None, comp: dict) -> dict:
    e, lv, r = s.get("econ"), s.get("price"), s["row"]
    has = bool(e and e.grade in ("A", "B", "C"))
    g = {}
    g["判定日"] = TODAY
    g["Amazon価格"] = (lv.sell_for_profit if lv and lv.sell_for_profit else "未確認")
    g["カートの販売元"] = s.get("カート保持者") or "未確認"
    if gate:
        g["ゲート種別"] = f"restrictions/approve（{gate['確認日']}）：{gate['根拠']}"
        g["ゲート可否"] = "可（新品）" if gate["ゲート判定"] == "OK" else "不可（新品の申請経路なし）"
    for col, val in (("卸率(売価比)", e.cost_ratio_pct if has else None),
                     ("発注点数", e.qty if has else None),
                     ("発注額(円・税込)", e.order_total if has else None),
                     ("1個粗利(円)", e.net_per_unit if has else None),
                     ("利益率(%)", e.net_margin_pct if has else None),
                     ("売り切る月数", (e.months_to_sell or "未確定（月販非表示）") if has else None),
                     ("半値処分時の損失(円)", e.half_disposal_loss if has else None)):
        g[col] = val if val is not None else "未確認"
    g["判定"] = comp["verdict"]
    g["判定理由"] = comp["reason"]
    g["確認方法"] = ("Keepa 取得済みデータで再採点（価格90日中央値・ランク12ヶ月・buybox）"
                     f"{TODAY}" + ("＋セラセン restrictions/approve 10/09" if gate else ""))
    g["確認者"] = "タカシ（機械判定・実画面未確認）"
    return g


def netsea_new_row(s: dict, header: list[str], gate, comp) -> list:
    r = s["row"]
    base = {h: "未確認" for h in header}
    base.update({
        "チケットID": TICKET, "ASIN": s["asin"], "商品名": (r.get("商品名") or "")[:80],
        "ブランド": r.get("ブランド") or "未確認",
        "Amazon URL": r.get("AmazonURL") or f"https://www.amazon.co.jp/dp/{s['asin']}",
        "新品出品者数(画面実数)": f"未確認（Keepa {r.get('セラー数') or '—'}）",
        "Amazon本体の有無": r.get("Amazon本体の有無") or "未確認",
        "ゲート種別": r.get("ゲート種別") or "未確認",
        "購入元の名前": r.get("購入元の名前") or "未確認",
        "卸サイト": "NETSEA" if s.get("在庫") in ("在庫あり", "品切れ") else "未確認",
        "購入先URL": s.get("_supplier_url") or "未確認",
        "発注状況": "未発注",
    })
    base.update(netsea_cells(s, gate, comp))
    return [base[h] for h in header]


# ── SD 側 ────────────────────────────────────────────────────────────────

def load_sd_manual() -> dict[str, dict]:
    if not SD_MANUAL.exists():
        return {}
    out = {}
    for r in csv.DictReader(SD_MANUAL.open(encoding="utf-8-sig")):
        a = (r.get("ASIN") or "").strip()
        if a:
            out.setdefault(a, []).append(r)
    return out


def sd_trading_status() -> dict[str, bool]:
    d = json.loads((WORK / "pipeline/sd_approval_requests.json").read_text())
    return {x["出展企業"]: bool(x.get("既に取引中")) for x in d}


def parse_sd_gates(txt: str) -> list[tuple[str, str, str]]:
    return [(m.group(1), m.group(2), m.group(3).strip())
            for m in re.finditer(r"\[([^:\]]+):([A-Z]+)\]([^｜]*)", txt or "")]


def num(x):
    try:
        return float(str(x).replace(",", "").replace("円", ""))
    except Exception:
        return None


def sd_rows(header: list[str]) -> tuple[list[list], list[dict]]:
    rows = list(csv.DictReader((SDB / "sd_candidates_private.csv").open(encoding="utf-8-sig")))
    manual = load_sd_manual()
    trading = sd_trading_status()
    order = {"要・卸値確認（Amazon側PASS）": 0, "UNKNOWN": 1, "NO-GO": 2}
    best: dict[str, dict] = {}
    for r in rows:
        k = r["ASIN"]
        ms = num(re.sub(r"[^0-9]", "", r.get("過去1ヶ月の販売数") or "")) or 0
        key = (order.get(r["判定"], 3), -ms)
        if any(r.get("SD品番", "").startswith((m.get("SD品番") or "#").strip())
               for m in manual.get(k, [])):
            key = (-1, 0)   # カズヨが卸価格を見た SD 品番の行を優先する
        if k not in best or key < best[k][0]:
            best[k] = (key, r)
    out, waiting = [], []
    for a, (_, r) in best.items():
        gates = parse_sd_gates(r["判定理由"])
        sup = re.sub(r"（スーパーデリバリー）", "", r["購入元の名前"])
        is_trading = trading.get(sup)
        price_rows = manual.get(a) or []
        mp = None
        for pr in price_rows:
            if r.get("SD品番", "").startswith((pr.get("SD品番") or "#").strip()):
                mp = pr
                break
        sell = num(r["販売価格(90日中央値)"])
        n = num(r["Amazon側のセット数(Amazon1個=卸何点か)"]) or None
        tier = r.get("サイズ区分") or None
        gr = None
        split_note = ""
        def _grade(nn):
            # 売り切り月数は3か月の仮置き（SD 行は月販から月数を出していない）＝推定費目
            return fba_cost.grade(sell, num(mp["卸価格_税抜_1点"]) * 1.1 * nn, tier,
                                  keepa_pct=num(r["販売手数料率(%)"]),
                                  sell_worst=num(r["保守値(90日の下位25%)"]),
                                  estimated=("保管月数（3か月の仮置き）",))
        if mp and num(mp.get("卸価格_税抜_1点")) and sell and n and tier:
            if r.get("セット数の確度") in ("確定", "単独"):
                gr = _grade(n)
            else:
                # セット数が未確定でも、候補の全部（1点・表記の n 点）で同じ等級なら
                # 結論は動かない。違えば UNKNOWN（単位ずれは真偽・§3.3-17）。
                g1, gn = _grade(1), _grade(n)
                if g1.grade == gn.grade == "C" or (g1.grade in ("A", "B") and gn.grade in ("A", "B")):
                    gr = gn
                    gr.reason += (f"（セット数は未確定だが、1点でも{int(n)}点でも等級 "
                                  f"{g1.grade}/{gn.grade} で結論は同じ）")
                else:
                    split_note = (f"#15 セット数 UNKNOWN（{r.get('セット数の確度')}）：SD 卸1点 "
                                  f"{mp['卸価格_税抜_1点']}円なら、Amazon1個＝卸1点で等級 {g1.grade}"
                                  f"（{g1.mid.get('利益率(%)')}%）・{int(n)}点で等級 {gn.grade}"
                                  f"（{gn.mid.get('利益率(%)')}%）。どちらかで結論が変わる")
        miss, fixes, never = [], [], []
        sold_out = bool(mp and "SOLD OUT" in (mp.get("在庫") or "").upper()
                        and "あり" not in (mp.get("在庫") or ""))
        if sold_out:
            miss.append(f"#17 卸の在庫 FAIL：SD で SOLD OUT（{mp['確認時刻']} 実画面）")
            fixes.append("SD で再入荷すれば可（同一 JAN を NETSEA でも探す）")
        for nme, st, why in gates:
            if st == "PASS":
                continue
            if nme == "採算" and gr:
                continue  # 卸価格が入ったので下で引き直す
            miss.append(f"{ITEM.get(nme, nme)} {st}：{clean(why, 70)}")
            if nme == "取引条件":
                never.append("変えようがない：この卸は Amazon 出品を認めていない（取引条件表）")
            elif nme == "Amazonカタログ":
                never.append("変えようがない：JAN が Amazon のカタログに無い（新規出品なら別検討）")
            elif nme == "採算" and "原価0円でも" in why:
                fixes.append("売価が低すぎる。Amazon 側に多い個数のセット ASIN があればそちらで計算")
            elif nme == "採算":
                fixes.append(f"卸1点 {r.get('B等級に必要な卸値上限(1点・税抜)') or '—'}円（税抜）以下なら B・"
                             f"{r.get('A等級に必要な卸値上限(1点・税抜)') or '—'}円以下なら A")
            else:
                f, nv = fix_for(nme if nme != "季節" else "季節の窓", st, why, {"econ": None})
                (never if nv else fixes).append(f)
        sts = [st for nm_, st, _ in gates if not (nm_ == "採算" and gr)]
        if sold_out:
            sts.append("FAIL")
        if gr:
            if gr.grade == "C":
                sts.append("FAIL")
                miss.append(f"#18 採算等級 C：{clean(gr.reason, 90)}")
                cap = r.get("B等級に必要な卸値上限(1点・税抜)")
                fixes.append(f"卸1点 {cap}円（税抜）以下なら B（いま {mp['卸価格_税抜_1点']}円）")
            elif gr.grade == "UNKNOWN":
                sts.append("UNKNOWN")
                miss.append(f"#18 採算等級 UNKNOWN：{clean(gr.reason, 70)}")
        elif split_note:
            sts.append("UNKNOWN")
            miss.append(split_note)
            fixes.append("Amazon の商品画像・商品名と SD の入数を人が見て「Amazon1個＝卸何点」を決めれば確定")
        elif r["判定"].startswith("要・卸値確認"):
            sts.append("UNKNOWN")
            miss.append("#17 卸価格未確認（SDログインで要確認）")
            fixes.append(f"卸1点 {r.get('B等級に必要な卸値上限(1点・税抜)') or '—'}円（税抜）以下なら B・"
                         f"{r.get('A等級に必要な卸値上限(1点・税抜)') or '—'}円以下なら A")
        if is_trading is False:
            miss.append("#17 SD 取引申請が必要（取引企業リストに無い）")
            fixes.append("SD で取引申請すれば卸価格が見えて発注できる")
        machine = "NO-GO" if "FAIL" in sts else ("UNKNOWN" if "UNKNOWN" in sts else "GO")
        human = [HUMAN_ITEMS_BASE[0]] if not num(re.sub(r"[^0-9]", "", r["過去1ヶ月の販売数"] or "")) \
            else []
        human += HUMAN_ITEMS_BASE[1:] + ["#1-2 ゲート（restrictions/approve）"]
        wait = False
        if machine == "GO":
            verdict, wait = "UNKNOWN", True
            reason = (f"機械判定は通過・実画面確認待ち（SD 卸価格 {mp['確認時刻'] if mp else ''} 確認済み・"
                      f"等級 {gr.grade}）。人が見る項目：{'・'.join(human)}")
        else:
            verdict = machine
            reason = "未達：" + " ／ ".join(miss)
            reason += " ／【こう変えれば】" + (never[0] if never else " ／ ".join(dict.fromkeys(fixes)))
            if machine == "UNKNOWN" and not never:
                pending = [m for m in miss if not m.startswith(("#9", "#5"))]
                if all(("卸価格未確認" in m) or ("取引申請" in m) for m in pending):
                    reason = "Amazon側の機械判定は通過・卸価格待ち。" + reason
        cells = {h: "未確認" for h in header}
        has = gr and gr.grade in ("A", "B", "C")
        cells.update({
            "判定日": TODAY, "チケットID": TICKET, "ASIN": a, "商品名": r["商品名"][:80],
            "ブランド": "未確認", "Amazon URL": r["AmazonURL"],
            "Amazon価格": sell or "未確認",
            "新品出品者数(画面実数)": f"未確認（{clean(r['セラー数'], 40)}）",
            "Amazon本体の有無": clean(r["Amazon本体の有無"], 60),
            "カートの販売元": r["カートの販売元"] or "未確認",
            "ゲート種別": r.get("ゲート種別") or "未確認",
            "購入元の名前": r["購入元の名前"], "卸サイト": "スーパーデリバリー",
            "購入先URL": (mp or {}).get("購入先URL") or r.get("購入先URL") or "未確認",
            "卸率(売価比)": (round(gr.mid["原価"] / sell * 100, 1) if has else "未確認"),
            "1個粗利(円)": (gr.mid["手残り"] if has else "未確認"),
            "利益率(%)": (gr.mid["利益率(%)"] if has else "未確認"),
            "判定": verdict, "判定理由": reason[:1800],
            "確認方法": ("SD 商品ページ（非ログイン・9/30〜10/09）＋取引条件表＋Keepa（JAN 逆引き）"
                         + ("＋卸価格はカズヨが社長 Chrome で確認" if mp else "")),
            "確認者": "タカシ（機械判定・実画面未確認）"
                      + ("／カズヨ（SD 卸価格のみ実画面）" if mp else ""),
            "発注状況": "未発注",
        })
        out.append([cells[h] for h in header])
        if wait or reason.startswith("Amazon側の機械判定は通過"):
            waiting.append({"ASIN": a, "商品名": r["商品名"][:40], "卸サイト": "SD",
                            "購入元": sup, "利益率": cells["利益率(%)"],
                            "手残り": cells["1個粗利(円)"], "月販": r["過去1ヶ月の販売数"],
                            "状態": "実画面確認待ち" if wait else "卸価格待ち",
                            "取引中": is_trading})
    return out, waiting


# ── 本体 ────────────────────────────────────────────────────────────────

def is_human(row: dict) -> bool:
    return "カズヨ" in (row.get("確認者") or "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    import gspread
    from google.oauth2.service_account import Credentials
    gc = gspread.authorize(Credentials.from_service_account_file(
        str(CRED), scopes=["https://www.googleapis.com/auth/spreadsheets"]))
    ws = gc.open_by_key(SHEET_ID).worksheet("判定台帳")
    vals = ws.get_all_values()
    stamp = date.today().strftime("%Y%m%d") + "_" + os.environ.get("RUN_TAG", "run")
    (OUT / f"before_{stamp}.json").write_text(json.dumps(vals, ensure_ascii=False))
    header, body = vals[0], vals[1:]
    rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in body]

    def count(rs):
        return (dict(Counter(r["判定"] for r in rs)), dict(Counter(r["卸サイト"] for r in rs)))
    before = count(rows)

    scored = score_netsea()
    gates = load_gate_checks()
    by_asin: dict[str, dict] = {}
    for s in scored:  # 同じ ASIN が2行あれば、判定の良い方（GO>UNKNOWN>NO-GO）を採る
        k = s["asin"]
        rank = {"GO": 0, "UNKNOWN": 1, "NO-GO": 2}.get(s["判定"], 3)
        if k not in by_asin or rank < {"GO": 0, "UNKNOWN": 1, "NO-GO": 2}.get(by_asin[k]["判定"], 3):
            by_asin[k] = s

    waiting = []
    updated = skipped_human = 0
    for r in rows:
        if r["卸サイト"] == "スーパーデリバリー":
            continue
        s = by_asin.get(r["ASIN"])
        if not s:
            continue
        if is_human(r):
            skipped_human += 1
            continue
        comp = consistency_gate(s, compose_netsea(s, gates.get(r["ASIN"])))
        r.update(netsea_cells(s, gates.get(r["ASIN"]), comp))
        updated += 1
        if comp["waiting"]:
            waiting.append(wait_row(s, r, "NETSEA"))

    have_netsea = {r["ASIN"] for r in rows if r["卸サイト"] != "スーパーデリバリー"}
    appended = []
    for k, s in by_asin.items():
        if k in have_netsea:
            continue
        comp = consistency_gate(s, compose_netsea(s, gates.get(k)))
        line = netsea_new_row(s, header, gates.get(k), comp)
        appended.append(line)
        if comp["waiting"]:
            waiting.append(wait_row(s, dict(zip(header, line)), "NETSEA"))

    # SD 行：既にある行も引き直す（人の行は触らない）。2026-10-11 まで既存の SD 行は
    # 飛ばしていたため、卸価格や規定が変わっても台帳に反映されなかった。
    sd_lines, sd_wait = sd_rows(header)
    ia = header.index("ASIN")
    sd_by_asin = {ln[ia]: ln for ln in sd_lines}
    have_sd = set()
    for r in rows:
        if r["卸サイト"] != "スーパーデリバリー":
            continue
        have_sd.add(r["ASIN"])
        ln = sd_by_asin.get(r["ASIN"])
        if not ln:
            continue
        if is_human(r):
            skipped_human += 1
            continue
        r.update(dict(zip(header, ln)))
        updated += 1
    human_sd = {r["ASIN"] for r in rows
                if r["卸サイト"] == "スーパーデリバリー" and is_human(r)}
    sd_wait = [w for w in sd_wait if w["ASIN"] not in human_sd]
    sd_lines = [ln for ln in sd_lines if ln[ia] not in have_sd]
    waiting += sd_wait

    final = [[r[h] for h in header] for r in rows] + appended + sd_lines
    after = count([dict(zip(header, x)) for x in final])
    summary = {"前": before, "後": after, "更新": updated, "人の行(据え置き)": skipped_human,
               "追記NETSEA": len(appended), "追記SD": len(sd_lines),
               "実画面確認待ち": Counter(w["状態"] for w in waiting),
               "実画面確認待ち_経路": Counter(w["卸サイト"] for w in waiting),
               "SD手入力卸価格": SD_MANUAL.exists()}
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    with (OUT / "waiting_list.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["状態", "ASIN", "商品名", "卸サイト", "購入元", "月販",
                                          "利益率", "手残り", "取引中"], extrasaction="ignore")
        w.writeheader()
        for x in sorted(waiting, key=lambda x: (x["状態"], x["卸サイト"])):
            w.writerow(x)
    if WAIT_FULL:
        with (OUT / "waiting_netsea_full.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(WAIT_FULL[0].keys()), extrasaction="ignore")
            w.writeheader()
            w.writerows(WAIT_FULL)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    if a.dry_run:
        (OUT / "after_dryrun.json").write_text(json.dumps([header] + final, ensure_ascii=False))
        return 0

    need = len(final) + 1 - ws.row_count
    if need > 0:
        ws.add_rows(need + 10)
    ws.update(range_name="A2", values=final, value_input_option="USER_ENTERED")
    (OUT / f"after_{stamp}.json").write_text(json.dumps([header] + final, ensure_ascii=False))
    print(f"書き込み {len(final)}行")
    return 0


def wait_row(s: dict, cells: dict, route: str) -> dict:
    return {"ASIN": s["asin"], "商品名": (s["row"].get("商品名") or "")[:40], "卸サイト": route,
            "購入元": s["row"].get("購入元の名前"), "利益率": cells.get("利益率(%)"),
            "手残り": cells.get("1個粗利(円)"),
            "月販": (f"{s['monthlySold']}個" if s.get("monthlySold") else "表示なし"),
            "状態": "実画面確認待ち"}


if __name__ == "__main__":
    raise SystemExit(main())
