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
_VALID_MATCH = {"any_substring"}


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


def _hit(text: str, terms) -> str:
    for k in terms:
        nk = _n(k)
        if nk and nk in text:
            return k
    return ""


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
            # 光源系（1F の語）に当たり、かつ brand が空 → メーカー不明で HARD
            h = _hit(text, _RULES["1F"]["terms"])
            if h and not has_brand:
                fired.append((rid, "brand欠落"))
                if not v.rule_id:
                    v.verdict, v.rule_id, v.hit = "HARD", rid, "brand欠落"
            continue

        h = _hit(text, r.get("terms", []))
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
