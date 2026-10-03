#!/usr/bin/env python3
"""既存プール（N=648）を **Keepa 0トークンで** 判定し直す。

    python3 regrade.py                    # 件数を出して CSV と表を書く
    python3 regrade.py --asin B0CDR4RV75  # 1件だけ検算する（計算の過程を全部出す）

なぜ再スキャンが要らないか
--------------------------
直すのは**判定のしかた**だけで、取ってきた事実は同じです。必要な材料はすべて手元にあります。

| 材料 | 出どころ |
|---|---|
| 売価・販売手数料率・FBA配送代行・卸値・ロット・セット数 | `agent_output/.../pipeline/discovered.json` |
| カート保持者・本体365日在庫率・セラー数・ランク・季節・判定理由 | `buy_list_private.csv`（判定台帳のダンプ） |

直した3箇所（2026-10-04）
-------------------------
① **原価を区分別にした** … `profit.OTHER_UNIT_COSTS_YEN = 206`（土鍋1点の実測）を廃止し、
   `fba_cost.other_costs()` がサイズ区分から引く（小型63円〜標準8 739円）。
   FBA配送代行も Keepa の ASIN 別実測から区分を逆引きして、売価1,000円以下の安い列を効かせる。
   販売手数料は **750円の崖**つき・Keepa の丸めた率を公式の段へ切り上げ（**厳しくなる向き**）。
② **「Amazon 本体の存在」での除外を「カート保持者」判定に変えた** … CLAUDE.md §3.3-1 が
   禁じているのは「本体がカートを持つ棚への発注」。本体が出品していることでは落とさない。
③ **誤差幅（売価7%＋200円）を撤去**し、A/B/C 等級に置き換えた。

**人が実画面で確認した行は機械で上書きしません**（CLAUDE.md §3.3-16）。
`--screen-checked` に ASIN を並べると、その行は結論を据え置きます。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUARD = HERE.parent / "24_カート保持者ガード"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(GUARD))

import fba_cost                                    # noqa: E402
import profit                                      # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
OUT = REPO / "workspace/output/agent_output/T-20260920-003/regrade"

GO, NO_GO, UNKNOWN = "GO", "NO-GO", "UNKNOWN"
PASS, FAIL = "PASS", "FAIL"

# 2026-10-01 にカズヨが実画面で確認して NO-GO にした行（機械で上書きしない）。
# 台帳の `確認方法` 列が「機械判定のみ」でない行がこれに当たる。
SCREEN_CHECKED_NO_GO: tuple[str, ...] = (
    "B0FNWB76NG", "B001LOOR4E", "B0FN3NWKYZ", "B0015XNJMW",
)

MAX_ORDER_TOTAL_YEN = 80_000      # 1 SKU の発注額の上限（テスト予算の残枠）

# 単位ずれ・終売・仕入れ不存在の番兵（CLAUDE.md §3.3-17）。`candidate_pipeline` と同じ値。
MIN_PLAUSIBLE_COST_RATIO = 15.0
MAX_PLAUSIBLE_MARGIN_PCT = 50.0

# 本体が統計期間中にカートを取った割合。過半なら実質「本体の棚」＝FAIL。
# 旧実装はここを **1%** にしていて、第三者が98%以上カートを持つ棚まで落としていた。
fba_cost_FAIL_WON_PCT = 50.0


# ── 判定理由の文字列から、各ゲートの status を復元する ──────────────────────
# 台帳の `判定理由` には **PASS でないゲートだけ**が「<接頭辞>. <理由>」の形で並びます
# （`candidate_pipeline.build_row`）。だから「その接頭辞が居るか」で非PASSが分かり、
# FAIL と UNKNOWN は理由文の定型句で見分けられます。
FAIL_MARKERS = {
    "1": ("Amazon.co.jp 本体です", "統計期間中に本体がカートを"),
    "2": ("本体が直近1年の", "直近90日に本体の在庫があります"),
    "3": ("Amazon 本体が混ざっています",),
    "5": ("メーカー本人・ブランド公式が相手では", "メーカーが1社で売っている棚です"),
    "生存": ("実質ゼロの棚", "いま仕入れると売れるまで在庫を抱えます"),
    "仕入れ": ("この仕入れ先からは Amazon に出せません",),
}
PREFIXES = ("1", "2", "3", "5", "採算", "生存", "仕入れ", "単位")


def split_reasons(reason: str) -> dict[str, str]:
    """`判定理由` を `{接頭辞: 理由文}` に割る。先頭の `【…】` は捨てる。"""
    body = re.sub(r"^(【[^】]*】)+", "", reason or "")
    out: dict[str, str] = {}
    for seg in body.split(" ／ "):
        seg = seg.strip()
        for pre in PREFIXES:
            if seg.startswith(f"{pre}. "):
                out[pre] = seg[len(pre) + 2:]
                break
    return out


def recorded_status(pre: str, text: str) -> str:
    """その理由文が FAIL だったか UNKNOWN だったか。"""
    return FAIL if any(m in text for m in FAIL_MARKERS.get(pre, ())) else UNKNOWN


# ── ② カート保持者だけで判定し直す ───────────────────────────────────────


def cart_gate(row: dict, segs: dict[str, str]) -> tuple[str, str]:
    """**落とすのは「カートを本体が持っている」行だけ。**

    本体の在庫履歴（`本体365日在庫率`）と出品一覧への本体の混在は**補助情報**に格下げ。
    カート保持者が決まらない行は今も UNKNOWN（fail-closed。ここは緩めない）。
    """
    cart = row.get("カートの販売元") or ""
    seg1 = segs.get("1", "")

    if "Amazon.co.jp" in cart and "本体" in cart:
        return (FAIL, "カート保持者が Amazon.co.jp 本体です。値下げしてもカートは取れません。")
    if "Amazon.co.jp（AN1VRQENFRJN5）" in cart or cart.startswith("Amazon.co.jp"):
        return (FAIL, "カート保持者が Amazon.co.jp 本体です。値下げしてもカートは取れません。")

    # 旧実装が FAIL にしていた「いまは第三者だが本体が期間中に n% カートを取った」。
    m = re.search(r"本体がカートを ([\d.]+)% 取っています", seg1)
    if m:
        won = float(m.group(1))
        if won >= fba_cost_FAIL_WON_PCT:
            return (FAIL, f"本体が統計期間中にカートを {won:.1f}% 取っています"
                          f"（過半＝実質『本体の棚』）。")
        return (PASS, f"カートは第三者が持っています（本体の期間カート獲得 {won:.1f}%・"
                      f"過半ではないので落としません。実画面で確認してください）。")

    if "不明" in cart or "食い違い" in cart:
        return (UNKNOWN, "カート保持者が決まりません（独立2本の一致が取れていない）。"
                         "実画面で確認してください。")
    if not cart:
        return (UNKNOWN, "カート保持者の列が空です。実画面で確認してください。")

    instock = row.get("本体365日在庫率") or ""
    note = ""
    if row.get("Amazon本体の有無") == "あり":
        note = (f"⚠️ 本体は出品しています（365日在庫率 {instock or '未確認'}）が、"
                f"**カートは第三者（{cart[:28]}）が持っています。**"
                "在庫を持つこととカートを取ることは別です（§3.3-1）。")
    return (PASS, f"カート保持者は第三者（{cart[:28]}）です。{note}")


# ── ① ③ 採算を新モデルで引き直す ────────────────────────────────────────


def _num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("%", "").replace("円", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def econ_gate(row: dict, cand: dict, segs: dict[str, str]):
    """新しい原価モデルで採算を引き直し、(status, reason, Economics|None) を返す。"""
    sell = _num(row.get("売価")) or (cand.get("sell") if cand else None)
    fee_pct = cand.get("fee_pct") if cand else None
    fba_yen = cand.get("fba_yen") if cand else None
    qty = int(_num(row.get("発注点数(Amazon何個)")) or 0)
    months = _num(row.get("売り切る月数"))

    # セット数（Amazon の1個 ＝ 卸の何点か）。**確定していなければ計算しません。**
    # 単位ずれは「幅」ではなく「真偽」です（CLAUDE.md §3.3-17 / 成果物33 §6.2 ④）。
    conf = (row.get("セット数の確度") or "").strip()
    n_set = _num(row.get("Amazon側のセット数(Amazon1個=卸何点か)"))
    decided = conf == "確定" or (conf == "単独" and n_set == 1)
    if not decided:
        return (UNKNOWN,
                f"Amazon の1個が卸の何点かが確定していません（確度『{conf or '不明'}』）。"
                "**金額を膨らませず計算しません。**人が卸サイトと Amazon の両方の画面を"
                "見てください。", None)

    unit_cost = _num(row.get("Amazon1個あたり原価(税込)"))
    if not unit_cost:
        per_point = _num(row.get("卸の1点あたり原価(税込)")) or (
            cand.get("unit_cost_incl") if cand else None)
        if per_point and n_set:
            unit_cost = per_point * n_set

    if not sell or not unit_cost or not fba_yen:
        missing = [n for n, v in (("売価", sell), ("Amazon1個あたり原価", unit_cost),
                                  ("FBA配送代行手数料（サイズ区分の逆引きに要る）", fba_yen))
                   if not v]
        return (UNKNOWN,
                f"採算を計算できません（{' / '.join(missing)} が手元のデータに無い）。"
                "**金額を膨らませず計算しません。**この行は Keepa の再取得が必要です"
                "（古い実行で作られた行で、発掘キャッシュに残っていません）。",
                None)

    # 台帳に消化月数があれば保管料の計上月数に反映させる（無ければ3ヶ月を置く）。
    ms = int(round(max(1, qty) / months)) if months and months > 0 else None
    e = profit.compute(sell, float(fee_pct or 0) or None, fba_yen, unit_cost,
                       max(1, qty), monthly_sold=ms, unit_decided=decided)

    note = f"【等級 {e.grade}】{e.grade_reason}"
    if e.cliff_note:
        note += f" {e.cliff_note}"

    # ── 単位ずれの番兵（CLAUDE.md §3.3-17）。**等級より先に置く。**
    # 原価モデルを直したからといって、ここを外してはいけません。卸が売価の15%未満 /
    # 利益率50%超は「単位ずれ・終売・仕入れの不存在」のサインです
    # （memory: knowledge_discontinued_bias_in_margin_ranking「利益率の異常な高さは終売のサイン」）。
    if e.cost_ratio_pct < MIN_PLAUSIBLE_COST_RATIO:
        return (UNKNOWN,
                f"卸率が売価の {e.cost_ratio_pct}% しかありません"
                f"（{MIN_PLAUSIBLE_COST_RATIO:.0f}% 未満）。卸は普通 売価の40〜70%です。"
                "**単位がずれているか、終売品か、仕入れが存在しない**サインで、"
                "人が卸サイトと Amazon の両方の画面を見るまで候補にしません。" + note, e)
    if e.net_margin_pct > MAX_PLAUSIBLE_MARGIN_PCT:
        return (UNKNOWN,
                f"利益率 {e.net_margin_pct}% は高すぎます"
                f"（{MAX_PLAUSIBLE_MARGIN_PCT:.0f}% 超）。同じサインの裏側です。"
                "**利益率が突出して良い行は、まず仕入れの実在を疑う**（§3.3-6）。" + note, e)
    if e.grade == fba_cost.GRADE_UNKNOWN:
        return (UNKNOWN, note, e)
    if e.grade == fba_cost.GRADE_C:
        return (FAIL, note, e)
    if e.order_total and e.order_total > MAX_ORDER_TOTAL_YEN:
        return (FAIL, f"1 SKU の発注額が {e.order_total:,}円で、残枠 "
                      f"{MAX_ORDER_TOTAL_YEN:,}円を超えます。{note}", e)
    # 🔴 **B は落としません。**「中央で黒字・悲観で20%未満」＝**最小ロットで1回だけ実測する**
    # 候補です（社長は小さく試したい）。採算ゲートとしては PASS にし、**行動の違いは
    # 等級の列**で出します。UNKNOWN（計算できなかった）と混ぜると、何をすべきかが消えます。
    return (PASS, note, e)


# ── 合成 ─────────────────────────────────────────────────────────────────


def regrade_row(row: dict, cand: dict) -> dict:
    segs = split_reasons(row.get("判定理由") or "")
    asin = row["ASIN"]

    cart_st, cart_why = cart_gate(row, segs)
    econ_st, econ_why, e = econ_gate(row, cand, segs)

    # 変えていないゲートは、台帳に記録された status をそのまま使う（再計算しない）。
    others: dict[str, tuple[str, str]] = {}
    for pre in ("5", "生存", "仕入れ"):
        if pre in segs:
            others[pre] = (recorded_status(pre, segs[pre]), segs[pre])
    # チェック2・3 は補助情報へ格下げ。ただし「取得できなかった」UNKNOWN は残す。
    for pre in ("2", "3"):
        if pre in segs and "取得できませんでした" in segs[pre]:
            others[pre] = (UNKNOWN, segs[pre])

    statuses = [cart_st, econ_st] + [s for s, _ in others.values()]
    if FAIL in statuses:
        verdict = NO_GO
    elif UNKNOWN in statuses:
        verdict = UNKNOWN
    else:
        verdict = GO

    pinned = ""
    if asin in SCREEN_CHECKED_NO_GO:
        verdict, pinned = NO_GO, "人が実画面で確認して NO-GO にした行（機械で上書きしない）"

    reasons = []
    if cart_st != PASS:
        reasons.append(f"カート. {cart_why}")
    if econ_st != PASS:
        reasons.append(f"採算. {econ_why}")
    for pre, (st, why) in others.items():
        reasons.append(f"{pre}. {why}")
    if not reasons:
        reasons = [f"カート. {cart_why}", f"採算. {econ_why}"]
    if pinned:
        reasons.insert(0, f"据え置き. {pinned}")

    return {
        "asin": asin,
        "旧判定": row.get("判定"),
        "判定": verdict,
        "等級": e.grade if e else fba_cost.GRADE_UNKNOWN,
        "サイズ区分": (e.size_tier or "未確定") if e else "未確定",
        "売価": int(_num(row.get("売価")) or 0),
        "1個手残り(新)": e.net_per_unit if e else None,
        "利益率(新)": e.net_margin_pct if e else None,
        "悲観利益率": e.worst_margin_pct if e else None,
        "その他固定費(新)": e.other_unit_costs if e else None,
        "販売手数料(新)": e.referral_fee_yen if e else None,
        "FBA配送代行(新)": e.fba_yen if e else None,
        "1個手残り(旧)": _num(row.get("1個手残り(円)")),
        "利益率(旧)": _num(row.get("利益率(%)")),
        "崖の助言": e.cliff_note if e else "",
        "カート判定": cart_st,
        "採算判定": econ_st,
        "判定理由(新)": " ／ ".join(reasons)[:1200],
        "row": row,
        "cand": cand,
        "econ": e,
    }


def load() -> list[dict]:
    rows = list(csv.DictReader((WORK / "buy_list_private.csv").open(encoding="utf-8-sig")))
    cands = json.loads((WORK / "discovered.json").read_text())["candidates"]
    return [regrade_row(r, cands.get(r["ASIN"]) or {}) for r in rows]


# ── 1件検算（社長・秘書向け。計算の過程を全部出す）──────────────────────────


def explain(asin: str) -> int:
    for g in load():
        if g["asin"] != asin:
            continue
        r, e = g["row"], g["econ"]
        print(f"=== {asin} / {r['商品名'][:60]}")
        print(f"カート保持者 : {r['カートの販売元']}")
        print(f"Amazon本体   : {r['Amazon本体の有無']}（365日在庫率 {r['本体365日在庫率']}）")
        print(f"セラー数     : {r['セラー数']}")
        print(f"売価         : {r['売価']}円 / 卸率 {r['卸率(売価比)']}")
        print(f"セット数     : {r['Amazon側のセット数(Amazon1個=卸何点か)']}"
              f"（確度 {r['セット数の確度']}）")
        print()
        print(f"--- 旧モデル: 1個手残り {r['1個手残り(円)']}円・利益率 {r['利益率(%)']}%"
              f"（その他固定費は一律206円・誤差幅 売価7%+200円）")
        if not e:
            print(f"--- 新モデル: 計算できません → {g['判定理由(新)']}")
            return 0
        print(f"--- 新モデル: サイズ区分 {e.size_tier}")
        print(f"    販売手数料   {e.referral_fee_yen}円"
              f"（率 {fba_cost.referral_pct(e.sell, None, g['cand'].get('fee_pct')):.1f}%"
              f"・750円の崖つき）")
        print(f"    FBA配送代行  {e.fba_yen}円")
        print(f"    その他固定費 {e.other_unit_costs}円 {e.other_breakdown}")
        print(f"    原価         {e.unit_cost_incl}円")
        print(f"    手残り       {e.net_per_unit}円 ＝ 利益率 {e.net_margin_pct}%")
        print(f"    悲観         {e.worst_net_per_unit}円 ＝ 利益率 {e.worst_margin_pct}%")
        print(f"    等級         {e.grade} … {e.grade_reason}")
        if e.cliff_note:
            print(f"    崖           {e.cliff_note}")
        print()
        print(f"旧判定 {g['旧判定']} → 新判定 {g['判定']}")
        print(f"理由: {g['判定理由(新)']}")
        return 0
    print(f"{asin} は台帳にありません。")
    return 1


# ── 集計 ─────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asin", help="1件だけ検算する")
    a = ap.parse_args(argv)
    if a.asin:
        return explain(a.asin)

    graded = load()
    OUT.mkdir(parents=True, exist_ok=True)

    from collections import Counter
    g_cnt = Counter(g["等級"] for g in graded)
    v_cnt = Counter(g["判定"] for g in graded)
    print(f"台帳の本チケット行: {len(graded)}件（Keepa 0トークン）")
    print("── 等級（採算だけを見たとき）")
    for k in ("A", "B", "C", "UNKNOWN"):
        print(f"   {k:8s} {g_cnt.get(k, 0):4d}件")
    print("── 総合判定（カート保持者・生存・仕入れ・メーカー直販も合わせたとき）")
    for k in (GO, UNKNOWN, NO_GO):
        print(f"   {k:8s} {v_cnt.get(k, 0):4d}件")
    print("── 旧 → 新 の移動")
    for (o, n), c in sorted(Counter((g["旧判定"], g["判定"]) for g in graded).items(),
                            key=lambda kv: -kv[1]):
        print(f"   {o:8s} → {n:8s} {c:4d}件")
    print("── なぜ落ちたか（新判定が GO でない行の、最初の非PASSゲート）")
    for k, c in Counter(
            ("カート保持者" if g["カート判定"] == FAIL else
             "カート保持者が不明" if g["カート判定"] == UNKNOWN else
             "採算（C=中央で赤字）" if g["採算判定"] == FAIL else
             "採算（B/UNKNOWN）" if g["採算判定"] == UNKNOWN else "生存・仕入れ・メーカー直販")
            for g in graded if g["判定"] != GO).most_common():
        print(f"   {k:24s} {c:4d}件")

    cols = ["asin", "旧判定", "判定", "等級", "サイズ区分", "売価",
            "販売手数料(新)", "FBA配送代行(新)", "その他固定費(新)",
            "1個手残り(新)", "利益率(新)", "悲観利益率",
            "1個手残り(旧)", "利益率(旧)", "崖の助言", "カート判定", "採算判定",
            "判定理由(新)"]
    with (OUT / "regrade.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for g in graded:
            w.writerow([g.get(c) for c in cols])
    json.dump({"等級": dict(g_cnt), "判定": dict(v_cnt), "総数": len(graded)},
              (OUT / "summary.json").open("w"), ensure_ascii=False, indent=1)
    print(f"\n書き出し: {OUT / 'regrade.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
