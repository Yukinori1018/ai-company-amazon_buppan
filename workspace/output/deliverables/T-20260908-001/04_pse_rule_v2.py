#!/usr/bin/env python3
"""#1 電気用品（PSE）ルール v2 — 参照実装。

T-20260908-001 / 法務ハルオ / 2026-09-08

━━ この実装の位置づけ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
仕様の正は `03_pse_rules_v2.json` です。**このモジュールは JSON を読んで動きます。**
語彙をコードに埋め込んでいないのは、仕様とコードが黙って食い違う事故を防ぐためです
（T-20260904-004 で、仕様が自分の挙げた反例と矛盾していた前例があります）。

━━ 3レーン ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    HARD   … 自動除外。緩めない
    REVIEW … 除外しない。「PSE要確認」の印を立てて候補に残す（発注は不可）
    PASS   … 電気用品安全法の電気用品に当たらない

━━ 評価順（v2.1。順序そのものが仕様です）━━━━━━━━━━━━━━━━━━━━━
    1A〜1D  真の危険類型（特定電気用品・電池・輸入経路・海外電圧）→ 常に最優先
    1F_PRE  曖昧さのない照明製品 → 1E より前。判定 §4-4 の human_gate と扱いを揃える
    1G      照明系だがメーカー不明
    1E      家電本体
    1F      光源系の弱い語（照明の文脈語との共起が必要）
    1H      乾電池駆動（電安法の電気用品ではない）

━━ 呼び出し側への要求 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    verdict == "HARD"   → 従来どおり除外する
    verdict == "REVIEW" → 除外しない。CSV に review_note を出し、発注は保留する
    verdict == "PASS"   → #1 では何もしない（他のルールは別途当てる）

    `other_rule_hits` は必ず記録すること。判定は勝者から、記録は全員から。
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent / "03_pse_rules_v2.json"

_VALID_VERDICTS = {"HARD", "REVIEW", "PASS"}
_VALID_MATCH = {"any_substring", "any_substring_with_context"}


class SpecError(RuntimeError):
    """仕様が読めない・知らない値が入っている。**黙って読み飛ばさず落とす。**"""


def load_spec(path: Path = SPEC_PATH) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    for r in spec["rules"]:
        if r["verdict"] not in _VALID_VERDICTS:
            raise SpecError(f"未知の verdict: {r['verdict']}（規則 {r['id']}）")
        if "match" in r and r["match"] not in _VALID_MATCH:
            raise SpecError(f"未知の match 種別: {r['match']}（規則 {r['id']}）")
        if "match" not in r and "condition" not in r:
            raise SpecError(f"規則 {r['id']} に match も condition も無い")
    return spec


_SPEC = load_spec()
_RULES = {r["id"]: r for r in _SPEC["rules"]}
_ORDER = [r["id"] for r in _SPEC["rules"]]


def _n(t) -> str:
    return unicodedata.normalize("NFKC", str(t or ""))


def _hit(text: str, terms, negation_terms=(), lookahead: int = 0) -> str:
    """一致語を返す。**直後 lookahead 文字に否定語があれば一致とみなさない。**

    否定の穴（T-20260904-004 で作った前科）を塞ぐための仕掛けです。
    「電池**不要**」「ライト**ベージュ**」を素通しさせないために、距離条件を持たせます。
    """
    negs = [_n(x) for x in (negation_terms or []) if _n(x)]
    for k in terms:
        nk = _n(k)
        if not nk:
            continue
        start = 0
        while True:
            i = text.find(nk, start)
            if i < 0:
                break
            tail = text[i + len(nk): i + len(nk) + max(lookahead, 0)]
            if not any(tail.startswith(ng) for ng in negs):
                return k
            start = i + 1          # 否定された出現は飛ばし、次の出現を探す
    return ""


def _rule_hit(r: dict, text: str) -> str:
    """1規則ぶんの照合。match 種別ごとの違いはここに閉じ込める。"""
    negs = r.get("negation_terms", [])
    look = r.get("negation_lookahead_chars", 0)
    if r.get("match") == "any_substring_with_context":
        # 複合語なら文脈は要求しない（「デスクランプ」は単体で光源）
        h = _hit(text, r.get("compound_terms", []), negs, look)
        if h:
            return h
        h = _hit(text, r.get("terms", []), negs, look)
        if not h:
            return ""
        # 弱い語は、照明の文脈語と共起したときにだけ発火させる
        if _hit(text, r.get("context_terms", [])):
            return h
        return ""
    return _hit(text, r.get("terms", []), negs, look)


@dataclass
class PseVerdict:
    verdict: str = "PASS"
    rule_id: str = ""
    hit: str = ""
    other_rule_hits: list = field(default_factory=list)
    review_note: str = ""

    @property
    def blocked(self) -> bool:
        """従来の `blocked` に相当するのは HARD だけ。REVIEW は落とさない。"""
        return self.verdict == "HARD"

    @property
    def blocks_purchase(self) -> bool:
        """候補には残すが、書類が揃うまで発注してはいけない状態。"""
        return self.verdict == "REVIEW"


def judge_pse(
    *,
    netsea_name: str = "",
    amazon_title: str = "",
    brand: str = "",
    category_names=None,
    supplier_name: str = "",
) -> PseVerdict:
    """1SKU を #1 v2 に当てる。引数はキーワード専用（順番の取り違え防止）。"""
    cats = list(category_names or [])
    text = _n(" ".join([netsea_name or "", amazon_title or "", " ".join(cats)]))
    has_brand = bool(_n(brand).strip())

    v = PseVerdict()
    fired = []          # (rule_id, hit) — 発火した全規則

    for rid in _ORDER:
        r = _RULES[rid]

        if rid == "1G":
            # 照明系（1F_PRE または 1F）に当たり、かつ brand が空 → メーカー不明で HARD
            h = _rule_hit(_RULES["1F_PRE"], text) or _rule_hit(_RULES["1F"], text)
            if h and not has_brand:
                fired.append((rid, "brand欠落"))
                if not v.rule_id:
                    v.verdict, v.rule_id, v.hit = "HARD", rid, "brand欠落"
            continue

        h = _rule_hit(r, text)
        if not h:
            continue
        fired.append((rid, h))
        if not v.rule_id:
            v.verdict, v.rule_id, v.hit = r["verdict"], rid, h
            if r["verdict"] == "REVIEW":
                v.review_note = r.get("review_note", "")

    v.other_rule_hits = [f"{rid}:{h}" for rid, h in fired if rid != v.rule_id]
    return v


if __name__ == "__main__":  # 手で叩いて挙動を見るとき用
    import sys
    name = " ".join(sys.argv[1:]) or "LED蛍光灯 直管40形 昼白色"
    r = judge_pse(netsea_name=name, brand="サンプル社")
    print(json.dumps(r.__dict__, ensure_ascii=False, indent=2))
