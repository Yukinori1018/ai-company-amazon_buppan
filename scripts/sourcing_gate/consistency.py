#!/usr/bin/env python3
"""候補 CSV の整合性検査（妥当性チェック）— 当社の数字がどれだけ信用できるかを機械で測る。

背景（CLAUDE.md §3.3-17 / §3.3-21 / §3.3-28）
  当社は「単位ずれで赤字を黒字と報告」を3回、「原価の57%が架空」を1回やっています。
  どれも**人が表を読めば気づけたはずの算術の崩れ**でした。人の注意力は当てにならないので、
  **不変条件を機械で検査**します。

このモジュールの約束（§3.3-17 をそのままコードにしたもの）
  1. **崩れていたら数字を黙って直さない。**「NG」と書いて**採算欄を空にする**。
     どちらが正しいか分からないまま辻褄だけ合わせると、嘘が一段深いところに潜ります。
  2. **判定できない項目は UNKNOWN と理由を書く。空欄で埋めない。**
  3. **番兵**（卸率が異常に低い／利益率が異常に高い）は自動で UNKNOWN。
     ⚠️ 印を付けるだけでは足りません。**採算欄も空にします**
     （2026-09-07 の事故：印を付けながら数字を出し続け、まぼろしの利益率71〜78%が上位を独占した）。
  4. **入力が無い検査は「不合格」ではなく「対象外」。**空欄を NG にすると、
     2回目の実行で自分が空けた欄を自分が NG にし続け、永久に収束しません。
  5. 捨てた数字は `--report` の JSON に原本ごと残します。**隠すのではなく、独り歩きを止める。**

使い方
    # 検査するだけ（何も書き換えない）
    python3 scripts/sourcing_gate/consistency.py check <candidates.csv> [--private <private.csv>]

    # 是正する（NG 行の採算欄を空にし、整合性検査の列を立てる）
    python3 scripts/sourcing_gate/consistency.py fix <candidates.csv> \\
        --out <fixed.csv> --report <report.json>

    # 2回目が0行であることを確かめる（§3.3-17「是正スクリプトは2回目で0行になるまで未完成」）
    python3 scripts/sourcing_gate/consistency.py fix <fixed.csv> --out <again.csv>

列の名前は `COLS` に集めています。CSV の列名が変わったらここだけ直せば動きます。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

# fba_cost.py（公式料金表ベースの純関数）を再計算の物差しに使う。
# ★ パイプラインが書いた数字を、**同じ公式料金表の関数で引き直して突き合わせる**のが目的。
_REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
_FBA_COST_DIR = Path(os.environ.get("FBA_COST_DIR") or (
    _REPO / "workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"))
if _FBA_COST_DIR.is_dir():
    sys.path.insert(0, str(_FBA_COST_DIR))
try:
    import fba_cost as F  # type: ignore
except Exception as _e:  # 物差しが無いなら「検査できた」と言ってはいけない
    F = None
    _FBA_IMPORT_ERROR = str(_e)
else:
    _FBA_IMPORT_ERROR = ""


# ── 列名 ──────────────────────────────────────────────────────────────────
class COLS:
    asin = "ASIN"
    verdict = "判定"
    grade = "等級"
    sell = "販売価格(90日中央値)"
    sell_worst = "保守値(90日の下位25%)"
    price_now = "現在価格"
    price_src = "価格の出どころ"
    buybox = "カートの販売元"
    category = "カテゴリー"
    sell_basis = "採算の基準売価"
    sell_basis_src = "基準売価の出どころ"
    tier = "サイズ区分"
    referral = "販売手数料"
    fba = "FBA配送代行"
    other = "その他固定費"
    unit_cost = "Amazon1個あたり原価(税込)"
    #: 同じ意味で使われている別の列名。**どちらでも読む**（表ごとに違う）。
    unit_cost_alt = "Amazon1個あたり仕入原価(税込)"
    set_count = "Amazon側のセット数(Amazon1個=卸何点か)"
    set_conf = "セット数の確度"
    net = "1個手残り"
    margin = "利益率(%)"
    net_worst = "悲観の手残り"
    margin_worst = "悲観の利益率(%)"
    qty = "発注点数(Amazon何個)"
    amount = "発注額(円・税込)"
    net_total = "手残り合計"
    months = "売り切る月数"
    d_order = "発注日"
    d_arrive = "着荷の見込み"
    d_fba = "FBA納品完了の見込み"
    d_start = "販売開始日"
    d_target = "売り切り目標月"
    # 非公開（agent_output にしか置かない）側の列
    wholesale_unit = "卸の1点あたり原価(税込)"
    wholesale_lot = "卸の最小ロット(点)"
    # このモジュールが足す列
    result = "整合性検査"
    detail = "整合性検査の詳細"


#: NG / 番兵のときに空にする「採算欄」。**ここに売価と日付は入れません。**
#: 売価は採算の*入力*であって結果ではなく、消すと「なぜ落ちたか」が読めなくなります。
PROFIT_COLS = (
    COLS.referral, COLS.fba, COLS.other, COLS.unit_cost,
    COLS.net, COLS.margin, COLS.net_worst, COLS.margin_worst,
    COLS.qty, COLS.amount, COLS.net_total,
)
#: 等級・判定は空にせず UNKNOWN にする（空は「未処理」と読まれるため）。
UNKNOWN = "UNKNOWN"

# ── 許容差と番兵の線（すべて仮置き。根拠を横に書く＝§3.1）──────────────────
YEN_TOL = 1.0        # 円の丸め差。これを超えたら式が違う
PCT_TOL = 0.15       # % の丸め差（小数1桁表示 ＝ ±0.05 ＋ 余裕）
STEP_TOL = 0.15      # 販売手数料の段に当てるときの許容

#: 番兵①：原価が売価に対して異常に安い行。2026-09-30 に「利益率64.7%」で断トツだった
#: オリヒロ 玉葱エキス粒は**仕入れが存在せず**、同日の「75.5%」は**単位ずれで実は赤字**だった。
#: どちらも「安すぎる原価」が共通のサイン。
#: ★ 15.0 は `score_20261004.MIN_PLAUSIBLE_COST_RATIO` と**同じ値**。
#:   最初 10.0 で書いたが、生成側に既にある線と二重定義になっていた（別々の線を持つと、
#:   生成側が落とした行を検査側が通すことが起きる）。**既にある会社の線に揃える**（§3.1）。
COST_RATIO_FLOOR_PCT = 15.0
#: 番兵②：利益率が異常に高い行。上の2件（64.7% / 75.5%）を確実に拾う線として 60%。
MARGIN_CEIL_PCT = 60.0
#: 回転の上限（§3.3「回転上限6ヶ月は既定」）。発注日→売り切り目標月末。
MAX_SELL_THROUGH_DAYS = 183
#: 死に帯（§3.3-23）。750円→751円で手数料が5%→15.4%、1,000円→1,001円で FBA が66円上がる。
DEATH_BANDS = ((751, 900), (1001, 1100))


# ── 値の読み取り ──────────────────────────────────────────────────────────
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def num(v) -> Optional[float]:
    """表示用の文字列から数値を取り出す。取れなければ None（0 にしない）。

    「21,930」「3,715円」「68.3%」「12ヶ月」は読む。
    「未確定（月販非表示・3ヶ月で仮置き）」のような**注記つきの文**は読まない
    （先頭の数字だけ拾うと「3ヶ月で仮置き」が「3」に化けて、仮置きが確定値になる）。
    """
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    s = re.sub(r"[円%]|ヶ月|個|点|位|社", "", s).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def get(row: dict, col: str) -> str:
    """BOM 付きの先頭列（'\\ufeffASIN'）にも当たるようにして取る。"""
    if col in row:
        return row[col] or ""
    for k in row:
        if k and k.lstrip("﻿") == col:
            return row[k] or ""
    return ""


def set_cell(row: dict, col: str, value: str) -> bool:
    """実在する列にだけ書く。書き換えたら True。"""
    for k in list(row):
        if k and k.lstrip("﻿") == col:
            if (row[k] or "") == value:
                return False
            row[k] = value
            return True
    return False


# ── 検査結果 ──────────────────────────────────────────────────────────────
NG = "NG"
WARN = "WARN"
SENTINEL = "UNKNOWN"      # 番兵。NG と同じく採算欄を空にする
NA = "対象外"              # 入力が無く検査できなかった（不合格ではない）


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    numbers: dict = field(default_factory=dict)

    def line(self) -> str:
        return f"[{self.check}] {self.message}"


@dataclass
class RowResult:
    asin: str
    findings: list[Finding] = field(default_factory=list)

    def of(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def blocking(self) -> list[Finding]:
        """採算欄を空にすべき理由（NG と番兵）。"""
        return [f for f in self.findings if f.severity in (NG, SENTINEL)]

    @property
    def ok(self) -> bool:
        return not self.blocking


# ── 個々の検査 ────────────────────────────────────────────────────────────
# どの検査も「入力が揃っていなければ何も返さない」。空欄を NG にしないための約束。

def _c_order_amount(row: dict, ctx: dict) -> Optional[Finding]:
    """発注額 ≒ Amazon1個あたり原価(税込) × 発注点数(Amazon何個)。

    §3.3-17 の不変条件そのもの。2026-09-30・10-01 に同じ単位ずれを2回出している。
    """
    cost, qty, amt = ctx["cost"], ctx["qty"], ctx["amount"]
    if None in (cost, qty, amt):
        return None
    exp = cost * qty
    if abs(amt - exp) <= YEN_TOL:
        return None
    return Finding("order_amount", NG,
                   f"発注額が合いません。Amazon1個あたり原価 {cost:,.0f}円 × 発注点数 {qty:,.0f}個 "
                   f"= {exp:,.0f}円 ですが、表は {amt:,.0f}円（差 {amt - exp:+,.0f}円）。",
                   {"原価": cost, "点数": qty, "表の発注額": amt, "計算値": exp})


def _c_unit_cost_from_wholesale(row: dict, ctx: dict) -> Optional[Finding]:
    """Amazon1個あたり原価 ≒ 卸の1点あたり原価(税込) × Amazon側のセット数。

    卸は「1点あたり」、Amazon は「N点セットで1個」。2つのデータ源をつなぐ口であり、
    当社が3回踏んだ単位ずれの発生源。卸値は非公開なので `--private` を渡したときだけ検査する。
    """
    cost, n, w = ctx["cost"], ctx["set_count"], ctx["wholesale_unit"]
    if None in (cost, n, w):
        return None
    exp = w * n
    if abs(cost - exp) <= 1.5:   # 税や端数の処理で1円強ずれることがある
        return None
    return Finding("unit_cost_from_wholesale", NG,
                   f"Amazon1個あたり原価が、卸の1点 × セット数 と合いません"
                   f"（セット数 {n:g}・計算値 {exp:,.0f}円 ↔ 表 {cost:,.0f}円）。"
                   f"**単位ずれは「幅」ではなく「真偽」です。**",
                   {"セット数": n, "計算値": exp, "表の原価": cost})


def _c_min_lot(row: dict, ctx: dict) -> Optional[Finding]:
    """発注点数(Amazon何個) × セット数 が、卸の最小ロット(点) を満たしているか。

    「Amazon 何個」と「卸 何点」を分けて検算する（§3.3-17）。
    """
    qty, n, lot = ctx["qty"], ctx["set_count"], ctx["wholesale_lot"]
    if None in (qty, n, lot) or lot <= 0:
        return None
    points = qty * n
    if points >= lot - 1e-9:
        return None
    return Finding("min_lot", NG,
                   f"発注点数が卸の最小ロットに届きません。Amazon {qty:g}個 × セット数 {n:g} "
                   f"= 卸 {points:g}点 ですが、最小ロットは {lot:g}点 です。",
                   {"Amazon個数": qty, "セット数": n, "卸点数": points, "最小ロット": lot})


def _c_net_per_unit(row: dict, ctx: dict) -> Optional[Finding]:
    """1個手残り ＝ 売価 − 販売手数料 − FBA配送代行 − その他固定費 − Amazon1個あたり原価。

    足し引きが合っているかを見る。合わないときは**どの売価で計算したのか**を逆算して出す
    （表の売価と内部の売価が違う事故を、人が読める形にするため）。
    """
    sell, fee, fba, oth, cost, net = (
        ctx["sell"], ctx["referral"], ctx["fba"], ctx["other"], ctx["cost"], ctx["net"])
    if None in (sell, fee, fba, oth, cost, net):
        return None
    exp = sell - fee - fba - oth - cost
    if abs(net - exp) <= YEN_TOL:
        return None
    implied = net + fee + fba + oth + cost
    return Finding("net_per_unit", NG,
                   f"1個手残りが引き算と合いません。{sell:,.0f} − {fee:,.0f} − {fba:,.0f} "
                   f"− {oth:,.0f} − {cost:,.0f} = {exp:,.0f}円 ですが、表は {net:,.0f}円。"
                   f"**表の手残りから逆算した売価は {implied:,.0f}円** で、"
                   f"表の90日中央値 {sell:,.0f}円 と違います。",
                   {"表の売価": sell, "逆算した売価": implied,
                    "表の手残り": net, "計算値": exp})


def _c_net_total(row: dict, ctx: dict) -> Optional[Finding]:
    """手残り合計 ≒ 1個手残り × 発注点数。"""
    net, qty, tot = ctx["net"], ctx["qty"], ctx["net_total"]
    if None in (net, qty, tot):
        return None
    exp = net * qty
    if abs(tot - exp) <= YEN_TOL:
        return None
    return Finding("net_total", NG,
                   f"手残り合計が合いません。{net:,.0f}円 × {qty:g}個 = {exp:,.0f}円 "
                   f"ですが、表は {tot:,.0f}円。",
                   {"計算値": exp, "表の合計": tot})


def _c_margin(row: dict, ctx: dict) -> Optional[Finding]:
    """利益率 ≒ 1個手残り ÷ 売価 × 100。"""
    net, sell, mar = ctx["net"], ctx["sell"], ctx["margin"]
    if None in (net, sell, mar) or not sell:
        return None
    exp = net / sell * 100.0
    if abs(mar - exp) <= PCT_TOL:
        return None
    return Finding("margin_pct", NG,
                   f"利益率が合いません。{net:,.0f} ÷ {sell:,.0f} × 100 = {exp:.1f}% "
                   f"ですが、表は {mar:.1f}%。",
                   {"計算値": round(exp, 2), "表の利益率": mar})


def _c_referral_cliff(row: dict, ctx: dict) -> Optional[Finding]:
    """販売手数料が **750円の崖**（§3.3-23）を正しく踏んでいるか。

    - 売上の合計が750円以下 → **一律5%**（段階制ではない）・最低30円（税抜）
    - 750円超 → 公式に存在する段（5.0 を除く 8.4 / 10.4 / 12.4 / 15.4 / 45.4）のどれか

    カテゴリーは CSV に無いので「どの段か」は決められない。**どの段でもないこと**と
    **崖の向きを間違えていること**だけを見る（出所に依存しない検査にする）。
    """
    sell, fee = ctx["sell"], ctx["referral"]
    if None in (sell, fee) or sell <= 0 or F is None:
        return None
    if sell <= F.REFERRAL_CLIFF_YEN:
        exp = round(max(sell * 5.0 / 100.0, float(F.MIN_REFERRAL_YEN_EXCL)) * F.TAX)
        if abs(fee - exp) <= YEN_TOL:
            return None
        return Finding("referral_cliff", NG,
                       f"売価 {sell:,.0f}円 は750円以下なので販売手数料は一律5%（最低30円）＝"
                       f"{exp:,.0f}円（税込）のはずですが、表は {fee:,.0f}円 です。",
                       {"売価": sell, "計算値": exp, "表の手数料": fee})
    pct = fee / F.TAX / sell * 100.0
    if abs(pct - 5.0) < STEP_TOL:
        return Finding("referral_cliff", NG,
                       f"売価 {sell:,.0f}円 は750円を**超えている**のに、販売手数料が5%"
                       f"（{fee:,.0f}円）で計算されています。崖の向きが逆です。",
                       {"売価": sell, "逆算した料率": round(pct, 2)})
    # カテゴリーが取れている行は、**どの段かまで完全一致で**検査する。
    cat = get(row, COLS.category).strip()
    if cat and cat in F.CATEGORY_OVER_750:
        exp_pct = F.CATEGORY_OVER_750[cat]
        exp = F.referral_yen(sell, category=cat)
        if abs(fee - exp) <= YEN_TOL:
            return None
        return Finding("referral_cliff", NG,
                       f"販売手数料がカテゴリーの料率と合いません。「{cat}」は {exp_pct}% なので "
                       f"売価 {sell:,.0f}円 なら {exp:,.0f}円（税込）ですが、表は {fee:,.0f}円 "
                       f"（割り戻すと {pct:.2f}%）です。",
                       {"カテゴリー": cat, "公式の料率": exp_pct, "計算値": exp,
                        "表の手数料": fee, "逆算した料率": round(pct, 2)})
    steps = [s for s in F.OFFICIAL_STEPS if s > 5.0]
    if any(abs(pct - s) < STEP_TOL for s in steps):
        return None
    return Finding("referral_cliff", NG,
                   f"販売手数料 {fee:,.0f}円 を売価 {sell:,.0f}円 で割り戻すと {pct:.2f}% で、"
                   f"公式の段（{' / '.join(f'{s}' for s in steps)}）のどれにも当たりません。"
                   f"（カテゴリー列が{'空' if not cat else f'「{cat}」で料率表に無い'}ので"
                   f"段の特定はできていません）",
                   {"売価": sell, "表の手数料": fee, "逆算した料率": round(pct, 2),
                    "カテゴリー": cat})


def _c_death_band(row: dict, ctx: dict) -> Optional[Finding]:
    """死に帯（§3.3-23）。751〜900円と1,001〜1,100円は値下げした方が手残りが増える。"""
    sell = ctx["sell"]
    if sell is None:
        return None
    for lo, hi in DEATH_BANDS:
        if lo <= sell <= hi:
            return Finding("death_band", WARN,
                           f"売価 {sell:,.0f}円 は死に帯（{lo:,}〜{hi:,}円）です。"
                           f"{lo - 1:,}円に下げた方が手残りが増える可能性があります。",
                           {"売価": sell, "帯": [lo, hi]})
    return None


def _c_fba_fee(row: dict, ctx: dict) -> Optional[Finding]:
    """FBA配送代行が、サイズ区分と売価（1,000円以下は安い列）から再計算した額と合うか。"""
    tier, sell, fba = get(row, COLS.tier), ctx["sell"], ctx["fba"]
    if not tier or None in (sell, fba) or F is None:
        return None
    if tier not in F.FBA:
        return Finding("fba_fee", SENTINEL,
                       f"サイズ区分「{tier}」が公式の区分表にありません。固定費が決まらないので"
                       f"採算を計算できません。", {"区分": tier})
    exp = F.fba_fee_yen(tier, sell)
    if abs(fba - exp) <= YEN_TOL:
        return None
    col = ("安い列（売価1,000円以下）" if sell <= F.FBA_LOW_PRICE_CLIFF_YEN
           else "通常の列（売価1,000円超）")
    other = F.FBA[tier][1] if sell > F.FBA_LOW_PRICE_CLIFF_YEN else F.FBA[tier][0]
    hint = ("。**表の額は安い列の値です＝1,000円の崖を逆向きに踏んでいます**"
            if abs(fba - other) <= YEN_TOL else "")
    return Finding("fba_fee", NG,
                   f"FBA配送代行が合いません。区分 {tier}・売価 {sell:,.0f}円 は"
                   f"{col}なので {exp:,.0f}円 ですが、表は {fba:,.0f}円 です"
                   f"（{exp - fba:+,.0f}円 の差）{hint}。",
                   {"区分": tier, "売価": sell, "計算値": exp, "表の額": fba,
                    "適用される列": col})


def _c_other_costs(row: dict, ctx: dict) -> Optional[Finding]:
    """その他固定費（保管・納品送料・梱包資材・外注）を区分と消化月数から再計算して突き合わせる。"""
    tier, oth = get(row, COLS.tier), ctx["other"]
    if not tier or oth is None or F is None or tier not in F.FBA:
        return None
    months = ctx["months"] if ctx["months"] is not None else 3.0
    exp = F.other_costs(tier, months).total
    if abs(oth - exp) <= 1.5:
        return None
    return Finding("other_costs", NG,
                   f"その他固定費が合いません。区分 {tier}・消化 {months:g}ヶ月 で再計算すると "
                   f"{exp:,.1f}円 ですが、表は {oth:,.0f}円 です。",
                   {"区分": tier, "消化月数": months, "計算値": round(exp, 1), "表の額": oth})


#: 採算の基準として認める売価の出どころ。**現在価格は認めない**（§3.3-28）。
ALLOWED_BASIS = ("90日中央値", "180日中央値", "実画面")


def _c_price_basis(row: dict, ctx: dict) -> Optional[Finding]:
    """採算を**どの売価で計算したか**を検査する（§3.3-28）。

    認めるのは「90日中央値」「180日中央値」「人が実画面で見た価格」。
    **現在価格で計算していたら NG**（スナップショットで判定するのが誤り）。

    生成側が `採算の基準売価` を渡していればそれで検算し、渡していなければ
    90日中央値を基準と見なして、現在価格で計算していないかを逆算で見る。
    """
    fee, fba, oth, cost, net = (ctx["referral"], ctx["fba"], ctx["other"],
                                ctx["cost"], ctx["net"])
    if None in (fee, fba, oth, cost, net):
        return None
    implied = net + fee + fba + oth + cost
    basis, src, median90, now = (ctx["sell_basis"], ctx["sell_basis_src"],
                                 ctx["sell_median90"], ctx["price_now"])

    if basis is not None:
        if src and not any(a in src for a in ALLOWED_BASIS):
            return Finding("price_basis", NG,
                           f"採算の基準売価の出どころが「{src}」です。認めるのは "
                           f"{' / '.join(ALLOWED_BASIS)} だけで、**現在価格では判定しません**"
                           f"（§3.3-28）。", {"出どころ": src, "基準売価": basis})
        if abs(implied - basis) > YEN_TOL:
            return Finding("price_basis", NG,
                           f"採算の基準売価は {basis:,.0f}円 と書いてありますが、"
                           f"手残りから逆算した売価は {implied:,.0f}円 です。"
                           f"**宣言した基準で計算されていません。**",
                           {"宣言した基準": basis, "逆算した売価": implied})
        return None

    if median90 is None:
        return Finding("price_basis", NG,
                       f"90日中央値も基準売価も空欄なのに採算が計算されています"
                       f"（手残りから逆算した売価 {implied:,.0f}円）。"
                       f"採算の基準は90日中央値です（§3.3-28）。",
                       {"逆算した売価": implied})
    if now is None or abs(now - median90) <= YEN_TOL:
        return None
    if abs(implied - now) <= YEN_TOL and abs(implied - median90) > YEN_TOL:
        return Finding("price_basis", NG,
                       f"採算が**現在価格 {now:,.0f}円**で計算されています。"
                       f"基準は90日中央値 {median90:,.0f}円 です（§3.3-28）。",
                       {"90日中央値": median90, "現在価格": now, "逆算した売価": implied})
    return None


def _c_set_count_decided(row: dict, ctx: dict) -> Optional[Finding]:
    """セット数が確定していないのに採算が計算されていないか。

    §3.3-17「確定していない行は金額を膨らませず**計算しない（UNKNOWN）**」。
    """
    conf = get(row, COLS.set_conf).strip()
    if not conf or conf in ("確定", "単独"):
        return None
    if ctx["net"] is None and ctx["cost"] is None:
        return None     # 正しく計算を止めている
    return Finding("set_count_undecided", SENTINEL,
                   f"セット数の確度が「{conf}」なのに採算が計算されています。"
                   f"Amazon の1個が卸の何点かが決まらない行は計算しません。",
                   {"確度": conf})


def _c_grade_unknown_with_numbers(row: dict, ctx: dict) -> Optional[Finding]:
    """等級が UNKNOWN なのに採算の金額が入っている行は UNKNOWN（金額を独り歩きさせない）。

    等級 UNKNOWN ＝ サイズ区分・単位・売価のどれかが決まらず**判定できなかった**行。
    印を付けながら数字を出すと、解けなかった行が必ず利益率の上位に来る
    （2026-09-07 の事故）。等級 C は「計算できた上での不合格」なので対象にしない。
    """
    g = get(row, COLS.grade).strip().upper()
    if g != "UNKNOWN":
        return None
    nums = {c: num(get(row, c)) for c in (COLS.net, COLS.margin, COLS.unit_cost)}
    if all(v is None for v in nums.values()):
        return None
    tier = get(row, COLS.tier).strip()
    return Finding("grade_unknown_with_numbers", SENTINEL,
                   f"等級が UNKNOWN（判定できなかった行）なのに採算の金額が入っています"
                   f"（手残り {nums[COLS.net]}・利益率 {nums[COLS.margin]}・"
                   f"サイズ区分 {tier or '空'}）。**印を付けることと、数字を出さないことは別です。**",
                   {k: v for k, v in nums.items() if v is not None})


def _c_sentinel_cost_ratio(row: dict, ctx: dict) -> Optional[Finding]:
    """番兵①：原価が売価に対して異常に安い行は UNKNOWN（§3.3-17）。"""
    cost, sell = ctx["cost"], ctx["sell"]
    if None in (cost, sell) or sell <= 0:
        return None
    ratio = cost / sell * 100.0
    if ratio >= COST_RATIO_FLOOR_PCT:
        return None
    return Finding("sentinel_cost_ratio", SENTINEL,
                   f"原価が売価の {ratio:.1f}%（下限 {COST_RATIO_FLOOR_PCT:g}%）しかありません。"
                   f"**仕入れの実在・内容量・セット数を人が確かめるまで採算を出しません。**"
                   f"2026-09-30 に「利益率64.7%で断トツ」だった行は仕入れ自体が存在せず、"
                   f"「75.5%」の行は単位ずれで実際は赤字でした。",
                   {"原価": cost, "売価": sell, "卸率(%)": round(ratio, 1)})


def _c_sentinel_margin(row: dict, ctx: dict) -> Optional[Finding]:
    """番兵②：利益率が異常に高い行は UNKNOWN（§3.3-17 / 終売バイアス）。"""
    mar = ctx["margin"]
    if mar is None or mar < MARGIN_CEIL_PCT:
        return None
    return Finding("sentinel_margin", SENTINEL,
                   f"利益率 {mar:.1f}% は上限 {MARGIN_CEIL_PCT:g}% を超えています。"
                   f"**利益率の異常な高さは終売・単位ずれ・仕入れ不在のサインです。**"
                   f"人が卸サイトと Amazon の両方の画面を見るまで採算を出しません。",
                   {"利益率(%)": mar})


def _c_grade_rule(row: dict, ctx: dict) -> Optional[Finding]:
    """等級が A/B/C の規定どおりか（中央と悲観の数字から再判定して突き合わせる）。

    規定（`fba_cost.grade()`）: A＝中央も悲観も「利益率20%以上 **または** 手残り400円以上」／
    B＝中央は満たすが悲観で割れる／C＝中央で満たさない。
    ⚠️ CLAUDE.md §3.5 の表には「利益率20%以上」しか書いておらず、**実装の OR 条件が落ちています**。
       規定と実装の粒度ずれ（§3.3-22）なので、ここでは**実装＝社長指示（単価ではなく利益額で切る）**
       に合わせ、文書の方を直してもらうよう報告します。
    """
    g = get(row, COLS.grade).strip()
    if g not in ("A", "B", "C") or F is None:
        return None
    net, mar, wn, wm = ctx["net"], ctx["margin"], ctx["net_worst"], ctx["margin_worst"]
    if None in (net, mar, wn, wm):
        return Finding("grade_rule", NG,
                       f"等級が {g} なのに、中央・悲観の手残り／利益率のどれかが空欄です。"
                       f"根拠の数字が無い等級は使えません。",
                       {"中央手残り": net, "中央利益率": mar,
                        "悲観手残り": wn, "悲観利益率": wm})
    tgt, floor = F.TARGET_MARGIN * 100, F.MIN_PROFIT_YEN
    ok_mid = mar >= tgt or net >= floor
    ok_bad = wm >= tgt or wn >= floor
    exp = "C" if not ok_mid else ("A" if ok_bad else "B")
    if exp == g:
        return None
    return Finding("grade_rule", NG,
                   f"等級が合いません。中央 {net:,.0f}円/{mar:.1f}%・悲観 {wn:,.0f}円/{wm:.1f}% なら "
                   f"**{exp}**（基準：利益率{tgt:g}%以上 または 手残り{floor:,}円以上）ですが、"
                   f"表は {g} です。",
                   {"表の等級": g, "計算値": exp})


# ── 日付 ──────────────────────────────────────────────────────────────────
_MD_RE = re.compile(r"^(\d{1,2})\s*[/月-]\s*(\d{1,2})")
_YM_RE = re.compile(r"^(\d{4})\s*[-/年]\s*(\d{1,2})")


_ISO_RE = re.compile(r"^(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})")


def _resolve_md(s: str, base: date) -> Optional[date]:
    """日付を解決する。`YYYY-MM-DD`（年つき）と `10/04`（年なし）の両方を受ける。

    年なしは `base` に最も近い年で解く。年末年始をまたぐ鎖（12/28 → 01/05）を正しく
    並べるため、前の日付を `base` に渡して順に解く。

    ⚠️ **当社の表は書式が揃っていません。**自分の生成物だけで試すと、他のエージェントが
    作った表（ISO 形式）を「日付として読めません」と誤検知する
    （2026-10-09：サトルの SD 起点候補 375行のうち **305行を誤検知した**）。
    **検査は、当社が実際に使っている書式を全部受けること。**
    """
    txt = (s or "").strip()
    m = _ISO_RE.match(txt)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _MD_RE.match(txt)
    if not m:
        return None
    mo, da = int(m.group(1)), int(m.group(2))
    best: Optional[date] = None
    for y in (base.year - 1, base.year, base.year + 1):
        try:
            cand = date(y, mo, da)
        except ValueError:
            continue
        if best is None or abs((cand - base).days) < abs((best - base).days):
            best = cand
    return best


def _resolve_month_end(s: str) -> Optional[date]:
    """「2027-01」を 2027-01-31 にする（目標は月いっぱい使える、と読む）。"""
    m = _YM_RE.match((s or "").strip())
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return date(y, mo, monthrange(y, mo)[1])


def _c_timeline(row: dict, ctx: dict) -> Optional[Finding]:
    """発注日 < 着荷 < FBA納品完了 < 販売開始 ≦ 売り切り目標月末、かつ売り切りまで6ヶ月以内。"""
    base: date = ctx["base_date"]
    chain = [(COLS.d_order, get(row, COLS.d_order)),
             (COLS.d_arrive, get(row, COLS.d_arrive)),
             (COLS.d_fba, get(row, COLS.d_fba)),
             (COLS.d_start, get(row, COLS.d_start))]
    if not any(v for _, v in chain) and not get(row, COLS.d_target):
        return None
    resolved: list[tuple[str, date]] = []
    cursor = base
    for name, raw in chain:
        if not raw:
            continue
        d = _resolve_md(raw, cursor)
        if d is None:
            return Finding("timeline", NG,
                           f"{name} 「{raw}」が日付として読めません。", {"列": name, "値": raw})
        resolved.append((name, d))
        cursor = d
    target = _resolve_month_end(get(row, COLS.d_target))
    if target:
        resolved.append((COLS.d_target, target))
    for (n1, d1), (n2, d2) in zip(resolved, resolved[1:]):
        if d2 < d1:
            return Finding("timeline", NG,
                           f"日付の順序が逆です。{n1} {d1.isoformat()} → "
                           f"{n2} {d2.isoformat()}。",
                           {"前": [n1, d1.isoformat()], "後": [n2, d2.isoformat()]})
    if resolved and target:
        span = (target - resolved[0][1]).days
        if span > MAX_SELL_THROUGH_DAYS:
            return Finding("timeline", NG,
                           f"売り切りまで {span} 日（{span / 30.4:.1f}ヶ月）で、上限6ヶ月を超えます。",
                           {"日数": span})
    return None


def _c_timeline_stale(row: dict, ctx: dict) -> Optional[Finding]:
    """発注日が過去なら、その予定表はもう使えない（§3.3-26「判定データは4日で陳腐化」）。

    ⚠️ これは **WARN** です。NG にして採算欄を空にすると、表が1日古くなるだけで
    648行ぜんぶの数字が消えます。§3.3-17 の「空にする」は**算術が崩れている行**への処置で、
    「正しいが古い」行への処置ではありません。鮮度は発注ゲート側（`checklist_spec.json` の
    `max_age_days`）が ASIN ごとに見ているので、ここで二重に執行しません。
    """
    d = _resolve_md(get(row, COLS.d_order), ctx["base_date"])
    if d is None:
        return None
    today: date = ctx["today"]
    if d >= today:
        return None
    return Finding("timeline_stale", WARN,
                   f"発注日 {d.isoformat()} はすでに過去です（本日 {today.isoformat()}・"
                   f"{(today - d).days}日前）。価格と卸値を取り直して予定表を引き直してください。",
                   {"発注日": d.isoformat(), "本日": today.isoformat()})


CHECKS: tuple[Callable[[dict, dict], Optional[Finding]], ...] = (
    _c_order_amount,
    _c_unit_cost_from_wholesale,
    _c_min_lot,
    _c_net_per_unit,
    _c_net_total,
    _c_margin,
    _c_referral_cliff,
    _c_fba_fee,
    _c_other_costs,
    _c_price_basis,
    _c_set_count_decided,
    _c_grade_unknown_with_numbers,
    _c_sentinel_cost_ratio,
    _c_sentinel_margin,
    _c_grade_rule,
    _c_death_band,
    _c_timeline,
    _c_timeline_stale,
)


# ── 1行を検査する ─────────────────────────────────────────────────────────
def check_row(row: dict, *, today: Optional[date] = None,
              base_date: Optional[date] = None,
              wholesale: Optional[dict] = None) -> RowResult:
    """候補1行を全検査に通す。`wholesale` は {卸の1点あたり原価, 卸の最小ロット} の辞書（任意）。"""
    today = today or date.today()
    wholesale = wholesale or {}
    # 🔴 **算術の検算は「採算を計算した売価」で行う。**生成側がそれを渡してくれるなら
    #    その値を使う。90日中央値の列で検算すると、**人が実画面で見た価格で計算した行を
    #    「算術が崩れている」と誤検知する**（2026-10-09 に実際に5行を誤検知した）。
    basis = num(get(row, COLS.sell_basis))
    median90 = num(get(row, COLS.sell))
    ctx = {
        "sell": basis if basis is not None else median90,
        "sell_median90": median90,
        "sell_basis": basis,
        "sell_basis_src": get(row, COLS.sell_basis_src).strip(),
        "sell_worst": num(get(row, COLS.sell_worst)),
        "price_now": num(get(row, COLS.price_now)),
        "referral": num(get(row, COLS.referral)),
        "fba": num(get(row, COLS.fba)),
        "other": num(get(row, COLS.other)),
        "cost": num(get(row, COLS.unit_cost) or get(row, COLS.unit_cost_alt)),
        "set_count": num(get(row, COLS.set_count)),
        "net": num(get(row, COLS.net)),
        "margin": num(get(row, COLS.margin)),
        "net_worst": num(get(row, COLS.net_worst)),
        "margin_worst": num(get(row, COLS.margin_worst)),
        "qty": num(get(row, COLS.qty)),
        "amount": num(get(row, COLS.amount)),
        "net_total": num(get(row, COLS.net_total)),
        "months": num(get(row, COLS.months)),
        # 卸の条件は ①同じ行（full=True のCSV）→ ②--private の突き合わせ の順に探す。
        # ①が入るようになったので、648行すべてで単位ずれを検算できる（2026-10-09）。
        "wholesale_unit": num(get(row, COLS.wholesale_unit)
                              or wholesale.get(COLS.wholesale_unit)),
        "wholesale_lot": num(get(row, COLS.wholesale_lot)
                             or wholesale.get(COLS.wholesale_lot)),
        "today": today,
        "base_date": base_date or today,
    }
    res = RowResult(get(row, COLS.asin).strip().upper())
    if F is None:
        res.findings.append(Finding("tooling", NG,
                                    f"原価モデル fba_cost.py を読み込めないため再計算で検算できません"
                                    f"（{_FBA_IMPORT_ERROR}）。**検査できないことを「合格」にしません。**"))
    for fn in CHECKS:
        try:
            f = fn(row, ctx)
        except Exception as e:   # 検査自体の失敗を「合格」にしない
            name = fn.__name__[3:] if fn.__name__.startswith("_c_") else fn.__name__
            f = Finding(name, NG, f"検査が例外で終わりました: {e}")
        if f:
            res.findings.append(f)
    return res


_MARK_RE = re.compile(r"(NG|WARN)\s*:\s*([^|]*)")
_DETAIL_RE = re.compile(r"\[([A-Za-z0-9_]+)\]")


def _parse_mark(s: str) -> tuple[set[str], set[str]]:
    """既にある `整合性検査` 列から、NG の検査名集合と WARN の検査名集合を読み戻す。"""
    ng: set[str] = set()
    warn: set[str] = set()
    for sev, body in _MARK_RE.findall(s or ""):
        names = {t.strip() for t in body.split(",") if t.strip()}
        (ng if sev == "NG" else warn).update(names)
    return ng, warn


def _parse_detail(s: str) -> dict[str, str]:
    """既にある `整合性検査の詳細` 列を {検査名: 1行} に戻す。"""
    out: dict[str, str] = {}
    for part in (s or "").split(" ／ "):
        part = part.strip()
        m = _DETAIL_RE.match(part)
        if m:
            out[m.group(1)] = part
    return out


def remediate(row: dict, res: RowResult) -> list[str]:
    """§3.3-17 の是正：NG・番兵の行は**採算欄を空にし**、等級と判定を UNKNOWN にする。

    数字を黙って直さない（どちらが正しいか分からないため）。捨てた値は呼び出し側が
    レポートに残す。変更した列名のリストを返す（空なら何も触っていない＝収束）。

    **収束のしかけ**：採算欄を空にすると、その欄を使っていた検査は次回「対象外」になって
    所見が消えます。素朴に書き直すと印が毎回変わり、2回目が0行になりません。そこで
    **既にある印と詳細を読み戻し、新しい所見と和を取る**。消えた所見は「前回こう落ちた」
    として残り、新しい所見だけが増えます。印が消えて行が健全に見えることは起きません。
    """
    changed: list[str] = []
    prior_ng, prior_warn = _parse_mark(get(row, COLS.result))
    prior_detail = _parse_detail(get(row, COLS.detail))

    new_ng = {f.check for f in res.blocking}
    new_warn = {f.check for f in res.of(WARN)}
    all_ng = prior_ng | new_ng
    all_warn = (prior_warn | new_warn) - all_ng

    if all_ng:
        for c in PROFIT_COLS:
            if set_cell(row, c, ""):
                changed.append(c)
        for c in (COLS.grade, COLS.verdict):
            if set_cell(row, c, UNKNOWN):
                changed.append(c)

    bits = []
    if all_ng:
        bits.append("NG: " + ", ".join(sorted(all_ng)))
    if all_warn:
        bits.append("WARN: " + ", ".join(sorted(all_warn)))
    mark = " | ".join(bits) if bits else "OK"

    lines = dict(prior_detail)
    for f in res.findings:
        lines.setdefault(f.check, f.line())   # 既にある説明は上書きしない（印を安定させる）
    detail = " ／ ".join(lines[k] for k in sorted(lines))

    if set_cell(row, COLS.result, mark):
        changed.append(COLS.result)
    if set_cell(row, COLS.detail, detail):
        changed.append(COLS.detail)
    return changed


# ── CSV の読み書き ────────────────────────────────────────────────────────
def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def load_private(path: Optional[Path]) -> dict[str, dict]:
    """卸値・最小ロットを ASIN で引ける辞書にする（agent_output 専用・PUBLIC には出さない）。"""
    if not path:
        return {}
    _, rows = read_rows(path)
    out: dict[str, dict] = {}
    for r in rows:
        a = get(r, COLS.asin).strip().upper()
        if a:
            out[a] = {COLS.wholesale_unit: get(r, COLS.wholesale_unit),
                      COLS.wholesale_lot: get(r, COLS.wholesale_lot)}
    return out


def run(path: Path, *, private: Optional[Path] = None, today: Optional[date] = None,
        base_date: Optional[date] = None) -> tuple[list[str], list[dict], list[RowResult]]:
    cols, rows = read_rows(path)
    wh = load_private(private)
    results = [check_row(r, today=today, base_date=base_date,
                         wholesale=wh.get(get(r, COLS.asin).strip().upper()))
               for r in rows]
    return cols, rows, results


def summarize(results: Iterable[RowResult], rows: Optional[list[dict]] = None) -> dict:
    """集計。`rows` を渡すと「前回の NG の印が残っている行」も数える。

    ★ 是正した CSV をもう一度 check にかけると、採算欄が空なので**所見は0件**になる。
      そこだけ見ると「表は健全」と読めてしまうので、**印に残っている NG を必ず併記する**。
    """
    results = list(results)
    by_check: dict[str, dict[str, int]] = {}
    for res in results:
        for f in res.findings:
            by_check.setdefault(f.check, {"NG": 0, "WARN": 0, "UNKNOWN": 0})
            by_check[f.check][f.severity] = by_check[f.check].get(f.severity, 0) + 1
    carried = 0
    if rows is not None:
        for row in rows:
            ng, _ = _parse_mark(get(row, COLS.result))
            if ng:
                carried += 1
    return {
        "母集団": len(results),
        "印にNGが残っている行": carried,
        "NG(採算欄を空にした行)": sum(1 for r in results if r.blocking),
        "うち番兵のみ": sum(1 for r in results
                       if r.blocking and not r.of(NG)),
        "WARNのみ": sum(1 for r in results if not r.blocking and r.of(WARN)),
        "問題なし": sum(1 for r in results if not r.findings),
        "検査別": by_check,
    }


# ── CLI ───────────────────────────────────────────────────────────────────
def _print_summary(s: dict) -> None:
    print(f"母集団 {s['母集団']}行")
    if s.get("印にNGが残っている行"):
        print(f"  🔴 前回の NG の印が残っている行  {s['印にNGが残っている行']}行"
              f"（採算欄は空のまま。所見が0件でも健全ではありません）")
    print(f"  今回の所見で NG（採算欄を空にする）  {s['NG(採算欄を空にした行)']}行"
          f"（うち番兵のみ {s['うち番兵のみ']}行）")
    print(f"  WARN のみ               {s['WARNのみ']}行")
    print(f"  問題なし                {s['問題なし']}行")
    print("  検査別:")
    for k, v in sorted(s["検査別"].items(), key=lambda x: -sum(x[1].values())):
        bits = " ".join(f"{sev}={n}" for sev, n in v.items() if n)
        print(f"    {k:28} {bits}")


def cmd_check(a) -> int:
    cols, rows, results = run(Path(a.csv), private=Path(a.private) if a.private else None,
                              today=a.today, base_date=a.base_date)
    s = summarize(results, rows)
    _print_summary(s)
    if a.show:
        for res in results:
            if res.blocking:
                print(f"\n● {res.asin}")
                for f in res.findings:
                    print(f"    {f.severity:8} {f.line()}")
    return 1 if (s["NG(採算欄を空にした行)"] or s["印にNGが残っている行"]) else 0


def cmd_fix(a) -> int:
    src = Path(a.csv)
    cols, rows, results = run(src, private=Path(a.private) if a.private else None,
                              today=a.today, base_date=a.base_date)
    out_cols = list(cols)
    for c in (COLS.result, COLS.detail):
        if not any((k or "").lstrip("﻿") == c for k in out_cols):
            out_cols.append(c)
    report = []
    changed_rows = 0
    for row, res in zip(rows, results):
        before = {c: get(row, c) for c in PROFIT_COLS + (COLS.grade, COLS.verdict)}
        for c in (COLS.result, COLS.detail):
            row.setdefault(c, "")
        changed = remediate(row, res)
        if changed:
            changed_rows += 1
        if res.findings:
            report.append({
                "ASIN": res.asin,
                "変更した列": changed,
                "空にする前の値": {k: v for k, v in before.items() if v} if res.blocking else {},
                "所見": [{"検査": f.check, "重さ": f.severity,
                        "内容": f.message, "数字": f.numbers} for f in res.findings],
            })
    out = Path(a.out) if a.out else src
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({(k or "").lstrip("﻿"): v for k, v in row.items()})
    s = summarize(results, rows)
    _print_summary(s)
    print(f"\n書き換えた行: {changed_rows}行 → {out}")
    if a.report:
        Path(a.report).write_text(
            json.dumps({"入力": str(src), "集計": s, "行": report},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"レポート（捨てた数字の原本つき）: {a.report}")
    print("\n※ 2回目の実行で「書き換えた行: 0行」になることを必ず確かめてください（§3.3-17）。")
    return 0


def _day(s: str) -> date:
    return date.fromisoformat(s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="候補CSVの整合性検査（CLAUDE.md §3.3-17）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("check", cmd_check), ("fix", cmd_fix)):
        p = sub.add_parser(name)
        p.add_argument("csv")
        p.add_argument("--private", help="卸値・最小ロットを持つ CSV（agent_output 専用）")
        p.add_argument("--today", type=_day, help="本日（既定: 実日付）。テスト用")
        p.add_argument("--base-date", type=_day, dest="base_date",
                       help="年なし日付（10/04 等）を解決する基準日（既定: --today）")
        p.set_defaults(fn=fn)
        if name == "check":
            p.add_argument("--show", action="store_true", help="NG 行の所見を全部出す")
        else:
            p.add_argument("--out", help="出力先（既定: 入力を上書き）")
            p.add_argument("--report", help="所見と捨てた数字を残す JSON")
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
