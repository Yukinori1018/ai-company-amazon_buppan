"""商品名から「入数（パック数 / 個数）」を推定するパーサ。

なぜ要るか（タカシ・honesty-first の核心）:
  社長が踏んだ重大バグ＝Yahooの「1個入り」とAmazonの「20個入り」が突合され、
  巨大な"偽の利益"で原石判定された。原因は仕入値(Yahoo, 個数不問)と
  売値(Amazon, 個数不問)を **個数正規化せず1対1比較** したこと。
  Keepa は1ASINに複数JANを持つため、単品JANが多包装ASINに"一応一致"し得る。

  そこで「商品名に書かれた入数」を両側で抜き出し、突合時に個数を揃える/降格する
  ための土台がこのモジュール。**抽出できなければ素直に None**（でっち上げない）。

設計方針:
- 純関数・正規表現だけ。外部依存なし（YAGNI）。
- 「個 / 本 / 袋 / セット / 缶 / 枚 / パック / P / コ / pcs」等の日本語/英語表記を広く拾う。
- 「×20」「20個入り」「20本セット」「2個セット」「20P」「単品」「1個」等に対応。
- 誤検出を避けるため、容量・サイズ由来の数字（ml / g / cm / mAh 等）は個数として拾わない。
- 自信が持てない曖昧表記は None を返す（過剰検出より「不明」の方が正直で安全）。

返り値: 推定入数（int, >=1）または None（不明）。
"""

import re
from typing import Optional

# 入数を表す「単位」語（この語に数字が前後すると個数とみなす）。
# ※ "ml" "g" "kg" "cm" "mm" "mAh" "W" 等の容量/サイズ単位はここに含めない（誤検出防止）。
_COUNT_UNITS = [
    "個入り", "個入", "個セット", "個パック", "個組", "個",
    "本入り", "本入", "本セット", "本パック", "本",
    "袋入り", "袋入", "袋セット", "袋",
    "缶入り", "缶入", "缶セット", "缶",
    "枚入り", "枚入", "枚セット", "枚",
    "包入り", "包入", "包",
    "食入り", "食分", "食",
    "粒入り", "粒",
    "回分", "回",
    "セット", "パック", "組", "コ", "ヶ", "ケ", "P", "pcs", "pc", "pack",
]

# 単位語を正規表現の選択肢に（長い語を先に＝最長一致）。
_UNIT_PATTERN = "|".join(re.escape(u) for u in _COUNT_UNITS)

# パターン1: 「×20」「x20」「✕20」形式（掛け算記号 + 数）。最も信頼できる入数表現。
_RE_TIMES = re.compile(r"[×x✕*]\s*(\d{1,4})\b", re.IGNORECASE)

# パターン2: 「20個入り」「20本セット」「20P」「2個セット」など 数字+単位語。
_RE_NUM_UNIT = re.compile(r"(\d{1,4})\s*(?:" + _UNIT_PATTERN + r")", re.IGNORECASE)

# パターン3: 「単品」「1個」「ばら売り」など「1個である」と明示する表現。
_RE_SINGLE = re.compile(r"単品|ばら売り|バラ売り|1個$|１個$")

# 誤検出ガード: これらの単位が数字の直後に来ているものは「個数」ではない（容量/サイズ）。
# 例: 「500ml」「20g」「2L」「3000mAh」「24cm」を個数20/2/3000/24 と誤読しない。
_RE_MEASURE = re.compile(
    r"\d+\s*(?:ml|mL|ML|l|L|リットル|cc|g|kg|mg|cm|mm|m|inch|インチ"
    r"|mah|mAh|wh|w|v|a|hz|gb|tb|mb|度|℃|円)\b",
    re.IGNORECASE,
)


def parse_quantity(name: Optional[str]) -> Optional[int]:
    """商品名から入数（個数）を推定する。抽出できなければ None。

    優先順位:
      1) 「×20」系（掛け算記号）— 最も入数の意図が明確
      2) 「20個入り / 20本 / 20P」等の 数字+個数単位
      3) 「単品 / 1個」等の単数明示 → 1
    いずれも当たらなければ None（＝不明。突合側で要確認に降格する）。
    """
    if not name:
        return None

    text = str(name)

    # まず容量/サイズ表現の「数字+単位」を伏字化して、個数の誤検出を防ぐ。
    masked = _RE_MEASURE.sub(" ", text)

    # 1) ×20 / x20 形式（最優先）
    m = _RE_TIMES.search(masked)
    if m:
        q = _coerce(m.group(1))
        if q is not None:
            return q

    # 2) 数字+個数単位（複数ヒット時は最大値を採る。「2個セット×10」等で総数寄りに）
    candidates = []
    for m in _RE_NUM_UNIT.finditer(masked):
        q = _coerce(m.group(1))
        if q is not None:
            candidates.append(q)
    if candidates:
        return max(candidates)

    # 3) 単品 / 1個 の明示 → 1
    if _RE_SINGLE.search(text):
        return 1

    return None


def _coerce(raw: str) -> Optional[int]:
    """数字文字列を 1〜9999 の妥当な入数に整える。範囲外や0は None。"""
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v <= 0 or v > 9999:
        return None
    return v
