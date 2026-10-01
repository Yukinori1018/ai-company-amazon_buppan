#!/usr/bin/env python3
"""Amazon 側の「1個」が卸の何点にあたるか。**単位を揃えるための1枚**（純関数）。

なぜ要るか（2026-09-30 カズヨが実画面で発見）
--------------------------------------------
卸サイトは「1点あたり」で売り、Amazon は「N点セット」で売ります。
B0DJNX12KZ は Amazon 側が **【2点セット】…×2点セット**、NETSEA 側は **1点 920円（税抜）**。
私は原価を 1,012円/個として利益率33.3%・GO と出しましたが、
正しい原価は **2,024円/個**で、採算は **▲181円/個**。**損益分岐売価3,194円**に対し売価2,980円。
手数料をゼロにしても+278円しか残らず、どう組んでも黒字になりません。

根は「**単位が違う2つの数字を突き合わせているのに、突き合わせの前に単位を揃える段が無かった**」ことです。
先に見つけた「保管料206円の漏れ」は式の**項**が足りない話でしたが、これは**単位**の話です。
利益率が妙に良い行は、単価だけでなく**単位**も疑うこと。

`set_num`（NETSEA の最小発注ロットの倍数）とは**別の概念**です。混ぜないこと。
- `amazon_set_count` … Amazon の1個 ＝ 卸の何点か（**原価の倍率**）
- `set_num`          … 卸が何点単位でしか売らないか（**発注数の丸め**）

読めないときは 1 にしません
--------------------------
セットを匂わせる語があるのに個数が読めない（「まとめ買い」「お得セット」）ときは **None** を返します。
呼び出し側はこれを **UNKNOWN**（人が見る）にします。**1 と決め打つと原価を N 分の1に見誤ります。**
"""

from __future__ import annotations

import re
import unicodedata

# 「N点セット」等で数えてよい助数詞。**粒・錠・g・ml・日分は数えない**
# （「600粒」は600セットではない）。
COUNTABLE = r"点|個|枚|本|袋|双|膳|脚|客|色|巻|束|足|P|p|pcs|pc"

# 「セット」を含むが**セット品ではない**語。先に消してから数える。
# 「エレコム ゲーミングヘッドセット」を「セット品だが個数不明」と読んでしまったため
# （2026-09-30・UNKNOWN が1件増えただけで済んだが、母数を静かに削る型のバグ）。
NON_SET_WORDS = (
    # 「セット」を含む複合語
    "ヘッドセット", "ハンドセット", "インカムセット", "オフセット", "リセット",
    "プリセット", "インセット", "アウトセット", "コルセット", "ヘッドフォンセット",
    # 「組」を含むが組み立て作業の意味（「木製 簡単組立」を N 不明のセット品と読んでいた）
    "組立て", "組み立て", "組立", "組み合わせ", "組合せ",
    # 社名に「パックス」が入るだけ（「富士パックス販売」の包丁を N 不明のセット品と読んでいた）
    "パックス",
)

# 「個数は読めないが、セット品である」ことを示す語。これがあれば 1 と決め打たず None にする。
# ⚠️ **数字を伴わない「組」「パック」「set」は入れない。**
#    「簡単組立」「富士パックス販売」「ヘッドセット」を全部セット品と読んでしまい、
#    候補が静かに UNKNOWN へ落ちていました（母数を削る型のバグ）。
SETWORD_RE = re.compile(r"(セット|まとめ買い|詰め合わせ|詰合せ|アソート|ペア)", re.I)

# 「セット」の語が無くても数えてよい助数詞（物理的な多入り）。
# 「ウルフピー4袋」「ヒトデdeでんでん 2袋」は卸1袋に対して Amazon が4袋・2袋で売っている。
# 個/本/枚/点は**単体では数えない**（「3枚刃」「1本」のような仕様表記に当たるため）。
STANDALONE_RE = re.compile(r"(\d+)\s*(?:袋|箱|缶|膳|双|客|脚)(?![\dA-Za-z])")

# 個数つきの型。**すべて突き合わせ、食い違ったら None**（黙って片方を採らない）。
PATTERNS = (
    # 【2点セット】 / 2点セット / 2個セット / 2枚組 / 2色組み / 2P組
    re.compile(rf"(\d+)\s*(?:{COUNTABLE})\s*(?:セット|組み?|入り?)"),
    # ×2点セット / ×2個 / x2セット（寸法の「幅70×奥行32」に当てないため助数詞を必須にする）
    re.compile(rf"[×xX]\s*(\d+)\s*(?:{COUNTABLE})(?:\s*(?:セット|組み?))?"),
    # 2セット / 2パック / 2pack
    re.compile(r"(\d+)\s*(?:セット|パック|pack)", re.I),
    # セット2点 / 組2個 / セット数:4pcs
    re.compile(rf"(?:セット|組)\s*数?\s*[:：]?\s*(\d+)\s*(?:{COUNTABLE})?"),
    # 4pcs / 4pc
    re.compile(r"(\d+)\s*pcs?\b", re.I),
)

# 「ペアセット」「ペア組」は2点。
PAIR_RE = re.compile(r"ペア\s*(?:セット|組み?)")

# 「N〈単位〉入り」の〈単位〉が**内容量とも個数とも読める**もの。
# 2026-10-01 の事故: 「カップ麺 110g、18食入り」を**単品**と読み、原価を18分の1に見誤った
# （卸268円/点 × 18 = 4,824円が正しい原価。1個手残りを +3,706円と報告したが実際は ▲778円）。
#   「18食入り」＝カップ麺18個（＝卸18点）
#   「90包入り」＝青汁1箱の中身（＝卸1点）
# **同じ書き方で意味が逆になるので、機械では決められない。**だから 1 とも N とも決めずに
# None（UNKNOWN）を返し、人に見せる。CLAUDE.md §3.3-7。
AMBIGUOUS_RE = re.compile(r"(\d+)\s*(?:食|包|缶|杯|玉|丁|尾|房|株|輪|カット|パウチ)\s*入り?")

# 「2P」「4P」のようなパック表記。**卸の1点が1枚なのか1パックなのかは商品名から分からない。**
# 2026-10-01: 「いいタオル バスタオル2P」を単品と読んでいた。
AMBIGUOUS_PACK_RE = re.compile(r"(?<![A-Za-z0-9])(\d+)\s*[Pp](?![A-Za-z0-9])")

# 現実的な上限。これを超える数は「600粒」型の誤読なので採らない。
MAX_PLAUSIBLE = 60


def parse_amazon_set_count(title: str | None) -> int | None:
    """商品タイトルから「Amazon の1個 ＝ 卸の何点か」を読む。

    戻り値:
      1     … 単品（セットを示す語が無い）
      N     … N点セット
      None  … セットらしいが個数が読めない／読んだ数が食い違う → **UNKNOWN にすること**
    """
    if not title:
        return None
    t = unicodedata.normalize("NFKC", str(title))
    for w in NON_SET_WORDS:
        t = t.replace(w, "")

    # **曖昧な表記を先に見る。**読めるふりをしないのが一番安全（下流は UNKNOWN になる）。
    for pat in (AMBIGUOUS_RE, AMBIGUOUS_PACK_RE):
        m = pat.search(t)
        if m and 1 < int(m.group(1)) <= MAX_PLAUSIBLE:
            return None

    found: set[int] = set()
    for pat in PATTERNS + (STANDALONE_RE,):
        for m in pat.finditer(t):
            n = int(m.group(1))
            if 1 <= n <= MAX_PLAUSIBLE:
                found.add(n)

    if not found and PAIR_RE.search(t):
        return 2

    if len(found) == 1:
        return found.pop()

    if len(found) > 1:
        # 「【2点セット】…×2点セット」なら両方2で一致する。食い違うのは読み違えの疑い。
        return None

    # 個数は読めなかった。セットを匂わせる語があるなら 1 と決め打たない。
    if SETWORD_RE.search(t):
        return None
    return 1


def cost_multiplier(title: str | None) -> tuple[int | None, str]:
    """(原価の倍率, 人が読める理由) を返す。倍率が None なら UNKNOWN。"""
    n = parse_amazon_set_count(title)
    if n is None:
        return (None,
                "商品名から「Amazon の1個 ＝ 卸の何点か」が確定できません"
                "（『18食入り』型は中身の数とも個数とも読めます）。原価の倍率が決まらないので"
                "**卸サイトと Amazon の両方を人が見てください。**")
    if n == 1:
        return (1, "単品（Amazon の1個 ＝ 卸の1点）。")
    return (n, f"Amazon の1個 ＝ 卸の{n}点（原価は卸単価の{n}倍）。")


def order_lot_in_amazon_units(netsea_set_num: int, amazon_set_count: int) -> int:
    """卸のロット（点）を Amazon の個数に直す。

    卸が `set_num` 点単位でしか売らず、Amazon の1個が `amazon_set_count` 点なら、
    Amazon 何個単位で発注することになるか。割り切れないぶんは切り上げ（余りは在庫として持つ）。
    """
    set_num = max(1, int(netsea_set_num or 1))
    per = max(1, int(amazon_set_count or 1))
    return max(1, -(-set_num // per))


# ── 内容量（人が目で突き合わせるための表示）────────────────────────────────

# 機械では卸と突き合わせられないが、**人が見るときに目に入る**ようにする（§3.3-7）。
# 「卸は300粒・Amazon は600粒」型のずれは商品名だけでは判定できず、人が両方を見るしかない。
VOLUME_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(粒|錠|包|カプセル|袋|枚|本|回分|日分|食|膳|人前|ml|mL|L|l|g|kg|cc|m|cm|mm|畳|W|V|A|lm|ルーメン)"
    r"(?![\dA-Za-z])")

# 内容量として意味のあるもの（サイズ・電気仕様は除く）。
VOLUME_UNITS = ("粒", "錠", "包", "カプセル", "袋", "枚", "本", "回分", "日分",
                "食", "膳", "人前", "ml", "mL", "L", "l", "g", "kg", "cc")


def extract_content_volume(title: str | None, limit: int = 3) -> str:
    """商品名から内容量らしい表記を拾って、人が読める1行にする。

    「600粒」「約60日分」「200g」「1L」など。寸法（cm）や電気仕様（W/V/lm）は入れません。
    見つからなければ空文字（台帳には「表記なし」と書きます）。
    """
    if not title:
        return ""
    t = unicodedata.normalize("NFKC", str(title))
    out: list[str] = []
    for m in VOLUME_RE.finditer(t):
        num, unit = m.group(1), m.group(2)
        if unit not in VOLUME_UNITS:
            continue
        s = f"{num}{unit}"
        if s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return " / ".join(out)
