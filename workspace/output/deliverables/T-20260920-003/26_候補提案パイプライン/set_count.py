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

# 「セット」の語が無くても数える助数詞（物理的な多入り）。**ただし中身の数かもしれない**ので、
# 下の PACK と同じく卸の商品名と突き合わせて初めて倍率にする（2026-10-11 「20膳」は卸も20膳）。
# 個/本/枚/点は**単体では数えない**（「3枚刃」「1本」のような仕様表記に当たるため）。
STANDALONE_RE = re.compile(r"(\d+)\s*(?:袋|箱|缶|膳|双|客|脚)(?![\dA-Za-z])")

# ── 2種類の「N」を分ける（2026-10-11 サトル実測を受けて書き直し）────────────────
#
# 旧実装は「12個入」「35枚組」「8点デラックスセット」「ペアセット」の N を全部
# 「Amazon の1個 ＝ 卸の N点」と読んでいた。サトルが179行を人の目で確かめたところ、
# **台帳にセット数の値があって人が数を確定できた34行のうち31行が誤り**で、31行すべてが
# 「商品名の数をそのまま倍率にした」ものだった（正解は1が29行）。卸も同じ「12個入」を1点で
# 売っているので、原価を12倍に見ていた（§3.3-17）。
#
#   EXPLICIT … 売り手が単品を束ねた表記。「×2点セット」「×3個」「2セット」「3パック」
#              → これは倍率として読む（B0DJNX12KZ の【2点セット】…×2点セット）
#   PACK     … 1つの商品の中身の数とも、束ねた数とも読める表記。
#              「12個入」「35枚組」「4点セット」「2個セット」「ペアセット」「20膳」「6食」「2P」
#              → **卸の商品名と突き合わせないと決めない。**卸の商品名が無ければ None（UNKNOWN）

_UNIT = rf"(?:{COUNTABLE}|袋|箱|缶|膳|双|客|脚)"
_UNIT_NO_MAI = r"(?:点|個|本|袋|双|膳|脚|客|色|巻|束|足|P|p|pcs|pc|箱|缶)"

# 「4L (4個)」「18枚入 (4個)」— 括弧書きの個数。**束ね表記のことも中身の言い直しのこともある**
# （人の確認：「ティポス 除菌アルコール 4L (4個)」＝4、「2袋（4本）」＝1）。
# 他に多入り表記が無ければ束ね、あれば卸と突き合わせる。
PAREN_RE = re.compile(r"[\(（]\s*(\d+)\s*(?:個|本|点|袋|箱|缶|セット)\s*[\)）]")

EXPLICIT_PATTERNS = (
    # ×2点セット / ×2個 / x2セット（寸法の「幅70×奥行32」に当てないため助数詞かセットを必須にする）
    # 「FX 8点」の X（型番の英字）に当てないため、x/X は英数字の直後を除く
    # 「フェイスタオル×2枚」は**ギフト箱の中身**（2026-10-11 今治タオル3件・人の確認は1）なので
    # 枚 は束ね表記に数えない（PACK 側で卸と突き合わせる）
    re.compile(rf"(?:×|(?<![A-Za-z0-9])[xX])\s*(\d+)\s*(?:{_UNIT_NO_MAI}|セット|組)"),
    # 2セット / 2パック / 2pack（数字の直後がセット＝「4点セット」は含まない）
    re.compile(r"(?<![\d.])(\d+)\s*(?:セット|パック|pack)", re.I),
    # 2026-10-11 人の確認で見つかった束ね表記3つ（どれも旧版は 1＝原価を安く見る側に読んでいた）
    # 「15本ロット」（アルボナース・人=15）
    re.compile(rf"(\d+)\s*(?:{_UNIT_NO_MAI})?\s*ロット"),
    # 「【5個】イカちゃんぽん」（人=5）「【8個セット】」
    re.compile(r"【\s*(\d+)\s*(?:個|本|袋|点|箱|缶|食)\s*(?:セット|入り?)?\s*】"),
    # 「(1g×150粒)×3」— 括弧の規格のあとの裸の ×N（ZOO ビタミンC・人=3）
    re.compile(r"[\)）]\s*[×xX]\s*(\d+)(?![\d.])"),
)

# 「20g×12個」「50ml×6本」は**1つの商品の中身の規格**（20g の小袋が12個で1箱）。束ね表記ではない。
# ただし後ろに「セット」「組」が付く「500ml ×2点セット」は束ね表記（ステンレスボトル2本）。
# 2026-10-11 B01M1NNOEE（蒟蒻ゼリー 20gx12個）を12倍に読んでいた（人の確認は1）。
# 「12mm×9m×24巻」のように寸法が連なる規格も1つの中身として扱う
_MEAS = r"(?:g|kg|ml|mL|L|l|cc|cm|mm|m|M|粒|錠)"
CONTENT_X_RE = re.compile(
    rf"\d+(?:\.\d+)?\s*{_MEAS}(?:\s*[×xX]\s*\d+(?:\.\d+)?\s*{_MEAS})*\s*[×xX]\s*(\d+)(?!\d)"
    rf"(?!\s*(?:{_UNIT})?\s*(?:セット|組))\s*(?:{_UNIT})?")

PACK_PATTERNS = (
    CONTENT_X_RE,
    # 12個入 / 35枚組 / 4点セット / 2個セット / 2袋入
    re.compile(rf"(\d+)\s*{_UNIT}\s*(?:セット|組み?|入り?)"),
    # セット数:4pcs / 組数 4（「ギフトタオルセット 34X66cm」の 34 を拾わないよう「数」を必須にした）
    re.compile(r"(?:セット|組)\s*数\s*[:：]?\s*(\d+)"),
    # 4pcs / 4pc
    re.compile(r"(\d+)\s*pcs?\b", re.I),
    STANDALONE_RE,
)

# 「ペアセット」「ペア組」は2点。**卸もペアで1点のことがある**（小倉陶器ビアタンブラー）。
PAIR_RE = re.compile(r"ペア\s*(?:セット|組み?)")

# 「N〈単位〉入り」の〈単位〉が**内容量とも個数とも読める**もの。
# 2026-10-01 の事故: 「カップ麺 110g、18食入り」を**単品**と読み、原価を18分の1に見誤った
# （卸268円/点 × 18 = 4,824円が正しい原価。1個手残りを +3,706円と報告したが実際は ▲778円）。
#   「18食入り」＝カップ麺18個（＝卸18点）
#   「90包入り」＝青汁1箱の中身（＝卸1点）
# **同じ書き方で意味が逆になるので、機械では決められない。**CLAUDE.md §3.3-7。
# 2026-10-11：旧式は `入り?`（「入」必須）で「120g、6食」を素通りして単品と読んでいた（人の確認は6）。
AMBIGUOUS_RE = re.compile(r"(\d+)\s*(?:食|包|缶|杯|玉|丁|尾|房|株|輪|カット|パウチ)(?:\s*入り?)?")

# 「2P」「4P」のようなパック表記。**卸の1点が1枚なのか1パックなのかは商品名から分からない。**
AMBIGUOUS_PACK_RE = re.compile(r"(?<![A-Za-z0-9])(\d+)\s*[Pp](?![A-Za-z0-9])")

# 「×24本入×(2ケース)」の**ケース数**。中身（24本入）とは別の段の束ねなので、ケース数を外して
# 中身側を卸と突き合わせ、最後にケース数を掛ける（2026-10-11 B004B8N8CE：卸1点＝200ml x 24本の
# 1ケース・人の確認は 2）。「iPhone 15 ケース」に当てないため、× か括弧の直後に限る。
CASE_RE = re.compile(r"(?:[×xX]\s*[\(（]?|[\(（])\s*(\d+)\s*ケース\s*[\)）]?")

# 現実的な上限。これを超える数は「600粒」型の誤読なので採らない。
MAX_PLAUSIBLE = 60
# 束ね表記（×N個・Nセット・Nロット）だけは上限を広げる。2026-10-11「2袋 × 64 個セット」（人=64）を
# 60超で捨てて、残った「2袋」で単品と読んでいた（原価を 1/64 に見る側）。中身の数（90包入）は 60 のまま。
MAX_EXPLICIT = 120


def _normalize(title: str) -> str:
    t = unicodedata.normalize("NFKC", str(title))
    for w in NON_SET_WORDS:
        t = t.replace(w, "")
    return t


def _numbers(t: str, patterns, cap: int = MAX_PLAUSIBLE) -> set[int]:
    out: set[int] = set()
    for pat in patterns:
        for m in pat.finditer(t):
            n = int(m.group(1))
            if 1 <= n <= cap:
                out.add(n)
    return out


def _pack_numbers(t: str) -> set[int]:
    """中身の数とも束ねた数とも読める N（2以上）。"""
    found = {n for n in _numbers(t, PACK_PATTERNS + (AMBIGUOUS_RE, AMBIGUOUS_PACK_RE)) if n > 1}
    if PAIR_RE.search(t):
        found.add(2)
    return found


def has_pack_expression(title: str | None) -> bool:
    """商品名に「12個入」型の（卸と突き合わせないと決まらない）数があるか。"""
    return bool(title) and bool(_pack_numbers(_normalize(title)))


ONE_RE = re.compile(rf"(?<![\d.])1\s*{_UNIT}(?![\dA-Za-z])")


def wholesale_count(wholesale_title: str | None, wholesale_lot: int | None = None) -> int | None:
    """卸の商品名に書かれた「1点の中の数」。

    「1袋」のように1と明記されていれば 1、「12個入」なら 12。
    **数が書かれていなければ None**（＝分からない）。2026-10-11 の実測で、卸の商品名に数が無い
    「タオルセット」「法善寺あられ みやびかぜ」は卸もギフト箱1点で、Amazon の「2枚組」「14袋入」を
    倍率にすると誤りだった（22行中12行）。

    `wholesale_lot` … 卸の最小ロット（点）。**商品名末尾の「xN」が最小ロットと同じなら、それは入数（ロット）で
    1点の中身ではない**ので外して数える（2026-10-11 国分ネット卸「蒟蒻ゼリー 130gx8」最小ロット8・
    単価は1袋あたり。人の確認7行がこの型。読み違えると原価を 1/8 に見る）。
    """
    if wholesale_title is None:
        return None
    t = _normalize(wholesale_title)
    lot = int(wholesale_lot or 0)
    if lot > 1:
        # 末尾の「x8」がロットと同じ数なら入数（ロット）なので外して残りを数える。
        # 「130gx8」→「130g」＝1点は1袋／「20gx12x12」→「20gx12」＝1点は12個入の袋。
        # 「50枚入」（ロット50）は x 形でないので外さない（マスク1箱＝1点・人の確認は 1）
        t2 = re.sub(rf"\s*[×xX]\s*{lot}\s*(?:{_UNIT})?\s*$", "", t)
        if t2 != t:
            ns = _numbers(t2, EXPLICIT_PATTERNS + (PAREN_RE,)) | _pack_numbers(t2)
            ns |= {int(m.group(1)) for m in CONTENT_X_RE.finditer(t2)}
            if not ns:
                return 1
            return ns.pop() if len(ns) == 1 else None
    ns = _numbers(t, EXPLICIT_PATTERNS + (PAREN_RE,)) | _pack_numbers(t)
    if not ns:
        return 1 if ONE_RE.search(t) else None
    return ns.pop() if len(ns) == 1 else None


def parse_amazon_set_count(title: str | None, wholesale_title: str | None = None,
                           wholesale_lot: int | None = None) -> int | None:
    """商品タイトルから「Amazon の1個 ＝ 卸の何点か」を読む。

    `wholesale_title` … 突き合わせる卸の商品名（NETSEA の product_name 等）。
    `wholesale_lot`   … 卸の最小ロット（点）。商品名の数がロットと同じなら入数とみなす（wholesale_count）。
    「12個入」型の表記は、**卸の商品名にも同じ数があれば 1**、卸に数が無ければ N、
    卸の商品名が無ければ None（UNKNOWN）にする。

    戻り値:
      1     … 単品
      N     … N点セット
      None  … 決められない → **UNKNOWN にすること**（人が卸と Amazon の両方を見る）
    """
    if not title:
        return None
    t = _normalize(title)

    cases = [int(m.group(1)) for m in CASE_RE.finditer(t)]
    if cases:
        if len(cases) > 1 or not 1 <= cases[0] <= MAX_EXPLICIT:
            return None
        inner = parse_amazon_set_count(CASE_RE.sub(" ", t), wholesale_title, wholesale_lot)
        return None if inner is None else cases[0] * inner

    # 中身の規格（20g×12個）を先に PACK として取り出し、束ね表記の検索から外す
    t = CONTENT_X_RE.sub(lambda m: f" {m.group(1)}個入 ", t)
    explicit = _numbers(t, EXPLICIT_PATTERNS, MAX_EXPLICIT)
    # 「×2点セット」の「2点セット」部分が PACK にも当たるので、EXPLICIT の箇所を消してから数える
    rest = t
    for pat in EXPLICIT_PATTERNS:
        rest = pat.sub(" ", rest)
    paren = _numbers(rest, (PAREN_RE,))
    rest = PAREN_RE.sub(" ", rest)
    pack = _pack_numbers(rest)
    if paren:
        if len(paren) > 1 or explicit:
            return None
        q = next(iter(paren))
        if not pack:
            explicit = paren                # 「4L (4個)」＝束ね
        else:
            # 「18枚入 (4個)」＝18枚入を4箱 or 「2袋（4本）」＝中身の言い直し。卸と比べて決める
            if len(pack) > 1:
                return None
            w = wholesale_count(wholesale_title, wholesale_lot)
            p = next(iter(pack))
            return q if w == p else None

    if len(explicit) > 1:
        return None                     # 「×2点…×3点」は読み違えの疑い
    if explicit:
        n = next(iter(explicit))
        # 【2点セット】…×2点セット は同じ数。食い違う「N点セット」が残っていれば疑う。
        set_like = _numbers(rest, (re.compile(rf"(\d+)\s*{_UNIT}\s*セット"),))
        if set_like - {n}:
            return None
        # 卸の商品名があり、卸の側にも数が書かれていれば割る（卸も同じ束ねなら 1）。
        # 卸に数が無い／商品名が無いときは、束ね表記の n をそのまま使う（B0DJNX12KZ の型）
        w = wholesale_count(wholesale_title, wholesale_lot)
        if w is None:
            # 卸の商品名が「タオルセット」のようにセットを名乗っているのに数が無い＝卸も箱1点の疑い
            if wholesale_title and SETWORD_RE.search(_normalize(wholesale_title)):
                return None
            return n
        return n // w if n % w == 0 else None

    if pack:
        if len(pack) > 1:
            return None
        p = next(iter(pack))
        w = wholesale_count(wholesale_title, wholesale_lot)
        if w is None:
            return None                 # 卸の商品名が無い／読めない → 人が見る
        return p // w if p % w == 0 else None

    # 個数は読めなかった。セットを匂わせる語があるなら 1 と決め打たない。
    if SETWORD_RE.search(t):
        return None
    # Amazon に数が無いのに卸の1点が「30枚入」なら、Amazon の1個が卸の何点かは分からない
    # （2026-10-11 マスク：Amazon 商品名に数なし・卸は30枚入・人の確認は 3〜50）
    if wholesale_title is not None and _pack_numbers(_normalize(wholesale_title)):
        return None
    return 1


def cost_multiplier(title: str | None, wholesale_title: str | None = None
                    ) -> tuple[int | None, str]:
    """(原価の倍率, 人が読める理由) を返す。倍率が None なら UNKNOWN。"""
    n = parse_amazon_set_count(title, wholesale_title)
    if n is None:
        return (None,
                "商品名から「Amazon の1個 ＝ 卸の何点か」が確定できません"
                "（『12個入』『18食入り』型は中身の数とも束ねた数とも読めます）。原価の倍率が"
                "決まらないので**卸サイトと Amazon の両方を人が見てください。**")
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
