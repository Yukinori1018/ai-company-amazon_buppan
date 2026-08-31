"""出品の「入数」を商品名から読む —— **利益計算の正しさが、ここ1つに懸かっています。**

━━ なぜ独立したモジュールなのか ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
同種の事故を **2回** 起こしました。どちらも「同じ JAN で結んだ2つの数字が、
違う単位を指していた」ことが原因です。

  1回目: NETSEA 蒟蒻ゼリー1個117円 × Amazon「130gパウチ×48本入」6,798円
         → 利益率77.1% と表示。実際は赤字
  2回目: NETSEA シャンデリア球1個310円 × Amazon「【ケース販売 10個セット】」3,380円
         → 利益率58.4%「原石」と表示。実際は仕入3,100円/売価3,380円でほぼ利益なし
         （秘書カズヨが Amazon の実ページを開いて発見。**こちらの自動判定は素通しだった**）

2回目を通してしまった直接の原因は、括弧の中の数字を
「**括弧の直後にある数字**」としてしか探していなかったこと。
`【3個セット】` は読めるのに `【ケース販売 10個セット】` は読めませんでした。

━━ 設計の方針 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**読めないときに「1」と答えないこと。** それが2回とも事故の形でした。
このモジュールは「読めた数」と「自信が無い」を**別々に**返します。
自信が無いものは利益計算に回さず「要確認」に落とします（推測で片方を採らない）。
"""

import re
import unicodedata

# 助数詞。日本語の助数詞だけを信頼する（ASCII の "P" などは型番と区別できない）。
_JP_COUNTER = "個|本|枚|袋|包|缶|箱|種|パック|セット|パウチ"

# 個数トークン。「×48本入」「10個入」「(2個セット)」「５０本入」をまとめて1つの式で拾う。
# ⚠️ **掛け算(×)と素の個数を別々に扱ってはいけません。**
#    「10個入 FCB5【×20セット】」は 10×20＝200 で、片方だけ見ると20（1/10）になります。
#    最初その作りにして取りこぼしました。**全部まとめて拾い、後で数を見て判断する。**
_COUNT = re.compile(r"(?:[×xX]\s*)?(\d{1,4})\s*(?:" + _JP_COUNTER + r")")

# 「まとめ売りだ」と言っているのに個数が書かれていない語。読めなければ要確認にする。
# ⚠️ 「まとめ」単体を入れないこと。「まとめるチューブ」という商品名が実在します。
_SET_HINTS = ("セット", "ｾｯﾄ", "_set", " set", "ケース販売", "まとめ買い", "業務用", "ケース入")

# 個数トークンがこれより多い商品名は、内訳と総数が混ざっていて機械では解けない。
#   例「12個入（2種類×6個）×6袋」→ 12・2・6・6 の4つ。正解は72だが、
#      素直に全部掛けると864になる。**推測で答えを作らず要確認に落とす。**
_MAX_TOKENS = 2

# 末尾の「×10」（助数詞なし）。行末に限るのは「20×30cm」のような寸法を拾わないため。
# 実在例:「変換名人 LAN 中継アダプタ LAN-BB ×10」「サンワサプライ コネクタカバー TK-CA×10」
_TRAILING_MULT = re.compile(r"[×xX]\s*(\d{1,3})\s*$")

# これ以上は誤検知の方が疑わしい。
_PACK_MAX = 1000


class PackReading:
    """入数の読み取り結果。**「読めた数」と「自信が無い」を分けて持つ。**"""

    __slots__ = ("size", "uncertain", "reason", "tokens")

    def __init__(self, size: int, uncertain: bool, reason: str, tokens=()):
        self.size = size
        self.uncertain = uncertain
        self.reason = reason
        self.tokens = tuple(tokens)

    def __repr__(self):
        return f"PackReading(size={self.size}, uncertain={self.uncertain}, reason={self.reason!r})"


def _normalize(text: str) -> str:
    """全角を半角へ。「５０本入」「２００ｍｍ」のような表記が実在します。"""
    return unicodedata.normalize("NFKC", str(text or ""))


def detect_pack(title: str) -> PackReading:
    """商品名から入数を読む。

    戻り値の `size` は「この出品1つに商品が何個入っているか」。
    `uncertain=True` は「まとめ売りらしいが個数を確定できない」＝**利益計算に回してはいけない**。
    """
    text = _normalize(title)
    if not text:
        return PackReading(1, False, "商品名なし")

    counts = [int(m.group(1)) for m in _COUNT.finditer(text)]
    counts = [n for n in counts if 2 <= n <= _PACK_MAX]
    if not counts:
        # 助数詞が無い末尾の「×10」だけは拾う（型番の後ろに付く実在の書き方）。
        counts = [int(n) for n in _TRAILING_MULT.findall(text) if 2 <= int(n) <= _PACK_MAX]

    has_hint = any(h in text for h in _SET_HINTS)

    if len(counts) > _MAX_TOKENS:
        return PackReading(
            1, True,
            f"個数の表記が{len(counts)}個あり内訳と総数を判別できない（{counts}）", counts)

    if not counts:
        if has_hint:
            return PackReading(1, True, "「セット」等の表記があるが個数が読めない")
        return PackReading(1, False, "まとめ売りの表記なし")

    size = 1
    for n in counts:
        size *= n
    if size > _PACK_MAX:
        return PackReading(1, True, f"入数が大きすぎる（{size}）")
    return PackReading(size, False, f"商品名から{size}個と読み取り（{counts}）", counts)


def detect_pack_size(title: str) -> int:
    """互換用。**自信が無い場合も1を返すので、単体で使わないこと。**"""
    return detect_pack(title).size


def resolve_multiplier(netsea_name: str, amazon_title: str):
    """NETSEA 1単位に対して、Amazon の1出品が何単位ぶんかを出す。

    **ここが今回の事故の急所です。** 「Amazon の入数」をそのまま卸値に掛けてはいけません。
    NETSEA 側も既に複数個入りのことがあるからです。

      電球   : NETSEA 1個 / Amazon 10個セット → 倍率 10
      イヤーパッド: NETSEA 6個入 / Amazon 6個入 → 倍率 **1**（同じ物を数えている）

    戻り値: (倍率, 説明, 要確認か)
    **割り切れない・どちらかが不明なときは倍率を返さず要確認にします**（推測しない）。
    """
    a = detect_pack(amazon_title)
    n = detect_pack(netsea_name)

    if a.uncertain or n.uncertain:
        which = "Amazon側" if a.uncertain else "NETSEA側"
        why = a.reason if a.uncertain else n.reason
        return 1, f"入数を確定できません（{which}: {why}）", True

    if a.size % n.size != 0:
        return (1,
                f"入数が食い違います（NETSEA {n.size}個 / Amazon {a.size}個・割り切れない）",
                True)

    mult = a.size // n.size
    if mult == 1:
        return 1, f"入数は同じ（NETSEA {n.size}個 / Amazon {a.size}個）", False
    return mult, f"Amazonはケース売り（NETSEA {n.size}個 → Amazon {a.size}個 ＝ {mult}倍）", False
