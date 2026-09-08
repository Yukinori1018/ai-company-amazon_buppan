#!/usr/bin/env python3
"""社長にお出しする候補を絞る条件（2026-09-07/08 の社長判断＋法務判定）。

パイプラインに入っていなかった条件を、ここ1箇所に実装します。

    1. 蛍光灯を除外。**ただし LED を含むものは残す**（社長判断 2026-09-07）
    2. Amazon 本体が出品している商品を除外
    3. 知財ブランド（ポケモン・サンリオ等）は **除外ではなくフラグ**
    4. #1 電気用品（PSE）は法務ハルオの v2 に置き換え（HARD/REVIEW/PASS の3レーン）

━━ 触ってはいけない設計上の一線 ━━━━━━━━━━━━━━━━━━━━━━━━━━━
**直管形LED（LED蛍光灯）を機械で落とさないこと。**
電安法の対象と対象外が**同じ商品名の中に混在**し、商品名・JAN・カテゴリからは
判別できません（法務判定 T-20260908-001 の human_gate）。
`直管` を無条件に落とす条件を書くと、**残すと決めた LED 蛍光灯まで消えます。**
判定は人間が現物で行います。ここは REVIEW（要書類確認）で候補に残すのが正解です。
"""

from __future__ import annotations

import importlib.util
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PSE_DIR = REPO / "workspace/output/deliverables/T-20260908-001"


def _load_pse():
    """法務ハルオの参照実装をそのまま読み込む。**語彙を写経しない。**

    写経すると、法務が仕様を直したときにこちらが古いまま黙って動き続ける。
    仕様の正は 03_pse_rules_v2.json、参照実装は 04_pse_rule_v2.py。
    """
    spec = importlib.util.spec_from_file_location(
        "pse_rule_v2", PSE_DIR / "04_pse_rule_v2.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("pse_rule_v2", mod)
    spec.loader.exec_module(mod)
    return mod


PSE = _load_pse()


def _n(t) -> str:
    return unicodedata.normalize("NFKC", str(t or ""))


# LED を表す書き方。NFKC 正規化すると「ＬＥＤ」は "LED" になる。
_LED_TERMS = ("LED", "led", "Led", "エルイーディー", "発光ダイオード")

# 蛍光灯そのものを指す語。**LED を含む商品名には当てない**（下の judge を参照）。
_FLUORESCENT_TERMS = ("蛍光灯", "蛍光ランプ", "蛍光管", "グロー球", "点灯管", "安定器")

# 知財ブランド。**除外しない。**ゲート確認の対象として印を付けるだけ（社長判断）。
_IP_BRANDS = (
    "ポケモン", "ポケットモンスター", "ピカチュウ", "サンリオ", "ハローキティ", "キティ",
    "マイメロ", "シナモロール", "クロミ", "ディズニー", "ミッキー", "ミニー", "プーさん",
    "トイストーリー", "スターウォーズ", "マーベル", "スヌーピー", "ムーミン",
    "リラックマ", "すみっコぐらし", "ちいかわ", "ハイキュー", "鬼滅", "ワンピース",
    "ドラえもん", "アンパンマン", "ジブリ", "トトロ", "キャラクター",
    "ドラゴンボール", "ガンダム", "セーラームーン", "エヴァンゲリオン", "スプラトゥーン",
    "マリオ", "カービィ", "ゼルダ", "どうぶつの森",
)


@dataclass
class Selection:
    """1SKU ぶんの判定。**落とすのか、印を付けるだけなのかを混ぜない。**"""

    excluded: bool = False
    exclude_reasons: list = field(default_factory=list)
    flags: list = field(default_factory=list)          # 除外しない。人が確認する印
    pse_verdict: str = "PASS"
    pse_rule_id: str = ""
    pse_hit: str = ""
    pse_other_rule_hits: list = field(default_factory=list)
    pse_review_note: str = ""

    @property
    def requires_document_check(self) -> bool:
        """**通過だが要書類確認**。候補には残すが、発注してはいけない状態。

        「通過＝発注可」ではありません（社長判断待ち）。
        """
        return self.pse_verdict == "REVIEW"

    @property
    def label(self) -> str:
        if self.excluded:
            return "除外: " + " / ".join(self.exclude_reasons)
        if self.flags:
            return "通過（要確認: " + " / ".join(self.flags) + "）"
        return "通過"


def is_led(text: str) -> bool:
    t = _n(text)
    return any(k in t for k in _LED_TERMS)


def judge(
    *,
    netsea_name: str = "",
    amazon_title: str = "",
    brand: str = "",
    category_names=None,
    supplier_name: str = "",
    availability_amazon=None,
    amazon_offer_flag: str = "",
) -> Selection:
    """1SKU を今回の条件に当てる。引数はキーワード専用（順番の取り違え防止）。

    `availability_amazon` は Keepa の値。**-1 が「Amazon 本体の出品なし」**で、
    それ以外（0 以上）は本体が在庫を持っている＝勝てないので除外する。
    """
    cats = list(category_names or [])
    text = _n(" ".join([netsea_name or "", amazon_title or "", " ".join(cats)]))
    s = Selection()

    # ── 1. 蛍光灯（LED は残す）────────────────────────────────────────
    # ★順番が命。**先に LED かどうかを見る。**
    #   「LED蛍光灯」「直管形LED」は社長判断で**残す**と決まっている。
    #   ここを「蛍光灯なら落とす」と単純に書くと、残すと決めた商品が消える。
    if not is_led(text):
        for k in _FLUORESCENT_TERMS:
            if _n(k) in text:
                s.excluded = True
                s.exclude_reasons.append(f"蛍光灯（「{k}」・LED表記なし）")
                break

    # ── 2. Amazon 本体あり ───────────────────────────────────────────
    has_amazon = None
    if availability_amazon is not None:
        has_amazon = availability_amazon != -1
    elif amazon_offer_flag:
        has_amazon = _n(amazon_offer_flag).strip() not in ("", "なし", "無", "無し", "-")
    if has_amazon:
        s.excluded = True
        s.exclude_reasons.append("Amazon本体が出品している")

    # ── 3. 知財ブランド → 除外しない。印だけ ───────────────────────────
    brand_text = _n(" ".join([brand or "", amazon_title or "", netsea_name or ""]))
    for k in _IP_BRANDS:
        if _n(k) in brand_text:
            s.flags.append(f"知財ブランド「{k}」＝ゲート確認の対象")
            break

    # ── 4. #1 電気用品（PSE）v2 ──────────────────────────────────────
    p = PSE.judge_pse(netsea_name=netsea_name, amazon_title=amazon_title,
                      brand=brand, category_names=cats, supplier_name=supplier_name)
    s.pse_verdict = p.verdict
    s.pse_rule_id = p.rule_id
    s.pse_hit = p.hit
    s.pse_other_rule_hits = list(p.other_rule_hits)
    s.pse_review_note = p.review_note
    if p.verdict == "HARD":
        s.excluded = True
        s.exclude_reasons.append(f"#1 電気用品 {p.rule_id}（「{p.hit}」）")
    elif p.verdict == "REVIEW":
        # ★除外しない。候補に残して「要書類確認」の印を立てる。
        #   ただし **通過＝発注可ではない**（発注の可否は社長判断待ち）。
        s.flags.append("PSE要書類確認（発注前にメーカー書類。通過＝発注可ではない）")

    return s
