"""人が実画面で見た結果（カート保持者・新品の出品可否・キーゾン実売）を判定に合流させる。

なぜ別モジュールか（2026-10-11 タカシ）
--------------------------------------
これまでは人の確認を台帳のセルに直接書き、`確認者` に「カズヨ」が入った行は機械が以後
一切触らない（凍結）運用だった。これだと

  - SD の卸価格が後から入っても、カートだけ人が見た行は採算が引き直されない
  - 人の確認の根拠がシートのセルにしか残らず、どの画面をいつ見たかが追えない

ので、**人の確認はファイル（agent_output の CSV ＝証跡）に置き、台帳を引き直すたびに
機械判定へ上書き合流する**形にした。台帳は「機械判定 × 人の確認」の投影であり、
ここに載っている ASIN は `ledger_refresh` が凍結せずに毎回引き直す（人の値は毎回同じに戻る）。

入力（すべて人が見たもの。機械の推定は入れない）
  - ledger20261010/cart_check_*.csv     カズヨ Chrome 実画面：カートの販売元・カート価格・過去1か月表示
  - ledger20261010/gate_check_*.csv     カズヨ セラセン実画面：restrictions/approve?itemcondition=New
  - ledger20261010/cart_maker_flags_*.csv  カートがメーカー/ブランド本人（確定・疑い）
  - シートのタブ「実売とゲート_20261005」  カズヨ キーゾン実画面（ASIN 単位・3か月）

判定のしかた（CLAUDE.md §3.3 / §3.5）
  #5  カート：Amazon.co.jp → FAIL／メーカー本人（確定）→ FAIL／疑い → UNKNOWN／
      カートなし・高値で非表示 → UNKNOWN（誰も持っていない＝相場に戻せば取れる可能性）／それ以外 PASS
  #1-2 ゲート：最新の確認日の結果を採る（ブランド申請の前後で変わる・§3.3-25）
  #9  実売：キーゾンがある ASIN はキーゾンだけで決める（兄弟の値は流用しない・§3.3-29）。
      無ければ、Keepa の monthlySold があり実画面の「過去1か月」表示と一致すれば PASS。
      それ以外は UNKNOWN「キーゾン未確認」
  #10 取り分＝月販 ÷（カート対象の FBA ＋ カート対象の自己発送 ＋ 1）。3個/月未満は FAIL。
      在庫月数＝推奨初回点数 ÷ 取り分。6か月超は FAIL
"""
from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
OUT = WORK / "ledger20261010"
KEIZON_TAB = "実売とゲート_20261005"
MIN_SHARE = 3          # §3.5 #10 取り分の下限（個/月）
MAX_MONTHS = 6         # §3.5 #10 在庫月数の上限
TARGET_MONTHS = 3      # 3か月を超えるのはロット・ゲート10点が理由のときだけ

#: Keepa 生データ（buyBoxEligibleOfferCounts を読むため）。後ろほど新しい
RAW_FILES = [WORK / "refetch20261004/raw.jsonl",
             WORK / "buylist20261009/resolve_raw.jsonl",
             WORK / "buylist20261009/buybox_raw.jsonl"]


@dataclass
class Cart:
    holder: str
    price: str
    sold_label: str        # 実画面の「過去1か月で◯点以上購入」の◯+（空＝表示なし）
    checked_at: str
    maker: str = ""        # "確定" / "疑い" / ""
    maker_note: str = ""


@dataclass
class Keizon:
    label: str             # 例 "9/13/12（平均11個）"・"表示なし"
    avg: float | None
    months: list[str] = field(default_factory=list)
    checked: str = ""


@dataclass
class ScreenChecks:
    cart: dict[str, Cart]
    gate: dict[str, dict]
    keizon: dict[str, Keizon]

    def covers(self, asin: str) -> bool:
        return asin in self.cart or asin in self.gate or asin in self.keizon


def _num(x) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(x or "").replace(",", ""))
    return float(m.group()) if m else None


def load_cart() -> dict[str, Cart]:
    flags = {}
    for p in sorted(OUT.glob("cart_maker_flags_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            flags[r["ASIN"]] = (r["区分"], r["根拠"])
    out = {}
    for p in sorted(OUT.glob("cart_check_*.csv")):          # 名前順＝日付順。後の確認が勝つ
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            a = r["ASIN"].strip()
            holder = (r.get("カート保持者(実画面)") or "").strip()
            if (r.get("カートあり") or "").strip() == "N" and not holder:
                holder = "カートなし"
            sold = (r.get("過去1か月(実画面)") or r.get("過去1か月(実画面・下限)") or "").strip()
            c = Cart(holder, (r.get("カート価格") or "").strip(), sold, r.get("確認時刻", ""))
            if "疑い" in (r.get("注意") or ""):
                c.maker, c.maker_note = "疑い", r["注意"]
            if a in flags:
                c.maker, c.maker_note = flags[a]
            out[a] = c
    return out


def load_gate(fallback: dict[str, dict]) -> dict[str, dict]:
    """{ASIN: {"ゲート判定": OK/NG, "根拠", "確認日", "確認者"}}。新しい確認が勝つ。"""
    out = dict(fallback)
    for p in sorted(OUT.glob("gate_check_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            ok = r["新品の出品可否"].strip().upper().startswith("OK")
            out[r["ASIN"].strip()] = {
                "ゲート判定": "OK" if ok else "NG",
                "根拠": ("新品可（その他の商品なし）" if ok else r["新品の出品可否"]),
                "確認日": (r.get("確認時刻") or "")[:10],
                "確認者": r.get("確認者") or "",
                "人": True,
            }
    return out


def load_keizon(sheet) -> dict[str, Keizon]:
    try:
        vals = sheet.worksheet(KEIZON_TAB).get_all_values()
    except Exception:
        return {}
    h = vals[0]
    out = {}
    for row in vals[1:]:
        r = dict(zip(h, row))
        lab = r.get("キーゾン実売（ASIN単位）", "")
        m = re.match(r"\s*(\d+)/(\d+)/(\d+)", lab)
        out[r["ASIN"]] = Keizon(lab, _num(r.get("平均月販")) if m else None,
                                list(m.groups()) if m else [], r.get("確認者", ""))
    return out


def load_legal() -> dict[str, tuple[str, str]]:
    """法務判定で販売を止める行（{ASIN: (区分, 判定理由に書く文)}）。"""
    out = {}
    for p in sorted(OUT.glob("legal_flags_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[r["ASIN"].strip()] = (r["区分"].strip(), r["判定理由に書く文"].strip())
    return out


#: 法務46（電気用品・危険物）。GO 行に「発注前に書類を取り寄せる」を足すための語。
#: 🔴 ふるい落とし・並べ替えには使わない（§3.3-20：語で判定しない）。注記だけに使う
PSE_WORDS = ("蛍光灯", "蛍光ランプ", "ランプ", "ヘアアイロン", "ケーブル", "ブロワ", "ACアダプタ")
SDS_WORDS = ("スプレー", "エアゾール", "ミスト", "洗剤", "消臭", "芳香", "クリーナー", "電池", "霧")


def doc_note(name: str) -> str:
    need = []
    if any(w in name for w in PSE_WORDS):
        need.append("PSE 書類")
    if any(w in name for w in SDS_WORDS):
        need.append("SDS")
    if not need:
        return ""
    return f"発注前にメーカーから {'／'.join(need)} を取り寄せ（Amazon の審査用・法務46）"


def load(sheet, gate_fallback: dict[str, dict]) -> ScreenChecks:
    return ScreenChecks(load_cart(), load_gate(gate_fallback), load_keizon(sheet))


_OFFERS: dict[str, tuple[int, int, str]] | None = None


def offers(asin: str) -> tuple[int, int, str] | None:
    """(カート対象 FBA 数, カート対象 自己発送数, 取得元)。Keepa buyBoxEligibleOfferCounts。"""
    global _OFFERS
    if _OFFERS is None:
        _OFFERS = {}
        for f in RAW_FILES:
            if not f.exists():
                continue
            for line in f.open():
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                p = o.get("product") or {}
                bb = p.get("buyBoxEligibleOfferCounts")
                if o.get("asin") and bb and len(bb) >= 2:
                    _OFFERS[o["asin"]] = (max(bb[0], 0), max(bb[1], 0), f.parent.name)
    return _OFFERS.get(asin)


# ── 各項目 ────────────────────────────────────────────────────────────

def cart_gate(c: Cart) -> tuple[str, str]:
    """(状態, 理由)。§3.3-1・§3.3-5。"""
    h = c.holder
    if "Amazon.co.jp" in h:
        return "FAIL", f"カートは Amazon.co.jp（カズヨ実画面 {c.checked_at}）"
    if c.maker == "確定":
        return "FAIL", f"カートはメーカー/ブランド本人：{h}（{c.maker_note}）"
    if c.maker == "疑い":
        return "UNKNOWN", f"カート {h} はメーカー/ブランド本人の疑い（{c.maker_note}）"
    if h in ("カートなし", "高値で非表示") or not h:
        return "UNKNOWN", (f"カートなし（{h or '表示なし'}・カズヨ実画面 {c.checked_at}）"
                           "＝誰もカートを持っていない。売価を相場に戻せば取れる可能性")
    return "PASS", f"カートは第三者 {h}（{c.price}円・カズヨ実画面 {c.checked_at}）"


def sales(asin: str, s: dict, machine_st: str, sc: ScreenChecks) -> tuple[str, str, float | None]:
    """(状態, 理由, 月販)。キーゾンが最優先・無ければ Keepa monthlySold ＋実画面表示の一致。"""
    k = sc.keizon.get(asin)
    if k:
        if k.avg is None:
            return "UNKNOWN", f"キーゾン表示なし（{k.checked}）＝この ASIN の実数が取れない", None
        if k.avg <= 0:
            return "FAIL", f"キーゾン3か月 {k.label}＝実質ゼロ（{k.checked}）", 0
        return "PASS", f"キーゾン3か月 {k.label}（ASIN 単位・{k.checked}）", k.avg
    ms = s.get("monthlySold")
    c = sc.cart.get(asin)
    shown = _num(c.sold_label) if c else None
    if machine_st == "PASS" and ms:
        if c is None:
            return "PASS", f"Keepa 過去1か月 {ms}個（実画面未確認）", float(ms)
        if not shown:
            return ("UNKNOWN", f"Keepa は月{ms}個だが実画面に販売数表示なし（2根拠がずれる・"
                    "キーゾン未確認）", None)
        lo, hi = sorted((float(ms), shown))
        if hi >= 2 * lo:
            return ("UNKNOWN", f"Keepa 月{ms}個と実画面 {c.sold_label} が2倍以上ずれる（キーゾン未確認）",
                    None)
        return "PASS", f"実画面 過去1か月 {c.sold_label}（Keepa {ms}個と一致）", min(float(ms), shown)
    return "UNKNOWN", "キーゾン未確認（月販表示なし＝月50個未満。ASIN 単位の実数が無い）", None


def share_gate(asin: str, monthly: float, qty: int | None, min_lot: float | None,
               gated_needs_10: bool) -> tuple[str, str, dict]:
    """§3.5 #10。(状態, 理由, 付帯情報)。"""
    off = offers(asin)
    if not off:
        return "UNKNOWN", "出品者の内訳が取れない（Keepa 生データなし）", {}
    fba, fbm, src = off
    share = monthly / (fba + fbm + 1)
    info = {"fba": fba, "fbm": fbm, "share": share, "src": src}
    brk = f"カート対象 FBA {fba}・自己発送 {fbm}（Keepa {src}）"
    if share < MIN_SHARE:
        need = math.ceil(MIN_SHARE * (fba + fbm + 1))
        rivals_ok = int(monthly // MIN_SHARE) - 1        # 取り分3個を満たす競合数の上限
        fix = f"月販が {need}個以上になる月なら可（キーゾンで毎月の実数を見て再判定）"
        if rivals_ok >= 0 and rivals_ok < fba + fbm:
            fix += (f"／出品一覧の画面実数で、カート対象の競合が {rivals_ok}社以下なら可"
                    f"（Keepa {src} では {fba + fbm}社）")
        elif rivals_ok < 0:
            fix += f"／月販 {monthly:g}個では競合ゼロでも3個に届かない"
        return ("FAIL", f"取り分 {share:.1f}個/月（基準3個）＝月販 {monthly:g}÷({fba}+{fbm}+1)。{brk}",
                {**info, "fix": fix})
    floor = max(int(min_lot or 1), 10 if gated_needs_10 else 1)
    rec = qty or floor
    if rec / share > TARGET_MONTHS:
        rec = max(floor, math.floor(share * TARGET_MONTHS))
    months = rec / share
    info.update(rec=rec, months=months, floor=floor)
    if months > MAX_MONTHS:
        return ("FAIL", f"最小ロット {floor}点で在庫 {months:.1f}か月（上限6か月）。取り分 {share:.1f}個/月",
                {**info, "fix": f"最小ロットが {math.floor(share * MAX_MONTHS)}点以下の仕入れ先なら可"})
    why = f"取り分 {share:.1f}個/月・推奨初回 {rec}点で在庫 {months:.1f}か月。{brk}"
    if months > TARGET_MONTHS:
        why += f"（3か月超は最小ロット {floor}点のため）"
    return "PASS", why, info
