#!/usr/bin/env python3
"""SD に「何を・どの順で」投げるかを決める（通信しない・純粋関数だけ）。

なぜ作ったか（2026-10-12・T-20261012-001）
-----------------------------------------
JAN 4550624199285（サンリオ ぬいぐるみおせわセット（ベビー）クロミ 199281）を SD で
JAN 検索すると**0件**だった。ところが実際には SD の1ページに、キティ／シナモロール／
クロミを S1〜S3 の内訳にした**1ページ**として出品されていた。内訳にはメーカー品番 199281 が
書いてあるが、**JAN は載っていない**。

つまり `?word=<JAN>` の0件は「SD に無い」ではなく、次のどれかでもありうる。

1. 出展企業が JAN を載せていない（任意項目）
2. 内訳型（1ページに色・キャラ違いを S1〜Sn で並べる）で、内訳に JAN が無い
3. JAN は載っているが別の JAN（セット品・旧 JAN）

だから照合は3段にする（CLAUDE.md §3.3-11「0件を結論にする前に検算する」）。

    ① JAN  →  0件なら  ② メーカー品番  →  0件なら  ③ 商品名の主要語（ブランド＋種類＋キャラ名）

②③で当たったものは**JAN で裏が取れていない**。商品ページを開き、内訳のメーカー品番
（例：S3 = 199281）と Amazon 側の型番が一致するかを人が確かめるまでは「候補」扱い。

この module は SD を一切叩かない。叩くのは `sd_jan_lookup.py`（1日30回・間隔10秒・
在席必須）と、秘書のブラウザだけ。
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse

SEARCH_BASE = "https://www.superdelivery.com/p/do/psl/?word="

# 単位つきの数字は品番ではない（容量・寸法・個数）。英字だけの単位を並べる
_UNIT_RE = re.compile(
    r"(?i)^\d+(?:\.\d+)?(?:ml|l|g|kg|mg|cm|mm|m|cc|w|v|a|mah|wh|pcs|pc|p|gb|tb|mb|hz|khz|"
    r"k|x|h|d|in|inch|oz|lb|ft|y|yr|cal|kcal|min|sec|s)$")
# 「品番っぽい英数字」の素材。ハイフン込みで拾い、前後のハイフンは落とす
_ALNUM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]{2,24}")
# 規格・仕様の語（英数字混じりでも品番ではない）。2026-10-12 に一覧1.5万行の頻出上位から拾った
_SPEC_RE = re.compile(
    r"(?i)^(?:usb\d.*|type-?c|obd2|ipx?\d+|spf\d+|upf\d+|uv\d+|bluetooth\d.*|wi-?fi\d*|gen\d+"
    r"|\d+(?:way|in\d|day|ghz|mhz|ms|hz)|pd\d+w|spo2|5g|4g|h26\d|hdmi\d.*"
    r"|x00[0-9a-z]{7}|b0[0-9a-z]{8}"                 # FNSKU・ASIN
    r"|\d+(?:gb|tb|mb|ml|mm|cm|kg|mah)[a-z].*)$")   # 32GBmicroSD のような「容量＋語」
# 型番に見えても品番ではない語
_NOT_PART = {"ver", "box", "led", "usb", "type", "mini", "max", "pro", "plus"}

# 名前検索から外す語（SD の商品名に出ない・検索を狭めるだけの語）
_NOISE_WORDS = {
    "グッズ", "公式", "正規品", "日本正規品", "送料無料", "新品", "日本製", "国産", "人気",
    "かわいい", "可愛い", "おしゃれ", "子供", "子ども", "子供用", "キッズ", "女の子", "男の子",
    "プレゼント", "ギフト", "食玩", "限定", "セット", "まとめ買い", "単品", "対象年齢",
    "推し活", "ver", "ver.", "box", "BOX", "大人", "女性", "男性", "収納", "おすすめ",
    # IP の総称は「種類」ではない。これを種類に採ると検索が広がりすぎる
    "サンリオキャラクターズ", "sanrio", "characters", "サンリオ", "キャラクター",
}
_NOISE_RE = re.compile(r"対象年齢|才以上|歳以上|^\d+(?:\.\d+)?\D{0,3}$|^約?\d|^※")
_CORP_RE = re.compile(r"株式会社|有限会社|\(株\)|\(有\)|㈱|㈲")
# 商品名の先頭の「日本語ブランド(英語ブランド)」。例：'[バンダイ(BANDAI)] ...'、'サンリオ(SANRIO) ...'
_TITLE_BRAND_RE = re.compile(r"^\[?\s*([^\s(\[\]]+)\s*\(([^)]+)\)")

# キャラクター名。名前検索で「種類＋キャラ名」を組むために使う（足りなければ足す）
CHARACTER_WORDS = (
    "ハローキティ", "キティ", "マイメロディ", "マイメロ", "クロミ", "シナモロール", "シナモン",
    "ポムポムプリン", "POMPOMPURIN", "ポチャッコ", "けろけろけろっぴ", "けろっぴ", "ハンギョドン",
    "ウサハナ", "リトルツインスターズ", "キキララ", "タキシードサム", "バッドばつ丸", "ばつ丸",
    "こぎみゅん", "ぐでたま", "あひるのペックル", "マイスウィートピアノ", "しろうさ",
    "ちいかわ", "ハチワレ", "うさぎ", "すみっコぐらし", "リラックマ", "コリラックマ",
    "ミッフィー", "スヌーピー", "ドラえもん", "ポケモン", "ピカチュウ", "カービィ",
)


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").strip()


def brand_short(brand: str) -> str:
    """'サンリオ(SANRIO)' → 'サンリオ'、'[バンダイ(BANDAI)]' → 'バンダイ'。

    SD の商品名は日本語ブランド表記が多いので、括弧の外（＝日本語側）を採る。
    """
    b = _CORP_RE.sub("", _nfkc(brand)).strip("[]【】 ")
    head = re.split(r"[(\[【]", b, maxsplit=1)[0].strip()
    return (head or b).split(" ")[0] if (head or b) else ""


def part_numbers(title: str, model: str = "", jan: str = "") -> list[str]:
    """メーカー品番の候補を、当たりやすい順に返す（Keepa の model → 商品名の中の型番）。

    拾うもの：
    - 英字と数字が混ざった4文字以上の語（S8815062、KST-2012-R、EM-103、ZDR018）
    - 5〜7桁の数字だけの語（サンリオの 199281、JEJ の 9504289、[503462]）
    拾わないもの：単位つきの数字（470ml・22cm）、8桁/13桁（JAN と紛れる）、年号の4桁。
    """
    out: list[str] = []
    for src in (_nfkc(model), _nfkc(title)):
        # 括弧の中も見る（[503462] のように品番が括弧に入っていることがある）
        for tok in _ALNUM_RE.findall(src):
            tok = tok.strip("-")
            if (len(tok) < 4 or _UNIT_RE.match(tok) or _SPEC_RE.match(tok)
                    or tok.lower() in _NOT_PART):
                continue
            has_d = any(c.isdigit() for c in tok)
            has_a = any(c.isalpha() for c in tok)
            if has_d and has_a:
                out.append(tok)
            elif tok.isdigit() and 5 <= len(tok) <= 7:
                # JAN の一部と同じ数字でも捨てない（カミオ 069816・クラックス 131785 は
                # JAN の中に品番が埋まっている。捨てると一番当たる語を失う）
                out.append(tok)
    return list(dict.fromkeys(out))


def _title_words(title: str, brand: str, parts: list[str]) -> list[str]:
    t = _nfkc(title)
    t = re.sub(r"【[^】]*】|\[[^\]]*\]|\([^)]*\)", " ", t)   # 括弧の中は煽り・型番・英名が多い
    for p in parts:
        t = t.replace(p, " ")
    drop = {w.lower() for w in re.split(r"[\s()\[\]]+", _nfkc(brand)) if w}
    words = []
    for w in re.split(r"[\s/・,、|+＋&＆:：!！?？]+", t):
        w = w.strip("-.")
        if len(w) < 2 or w in _NOISE_WORDS or w.lower() in _NOISE_WORDS:
            continue
        if w.lower() in drop or _NOISE_RE.search(w):
            continue
        words.append(w)
    return list(dict.fromkeys(words))


def name_queries(title: str, brand: str = "", model: str = "") -> list[str]:
    """名前で引く検索語を2本返す：[ブランド＋種類＋キャラ名, ブランド＋種類]。

    SD の検索は語の AND なので、語を足すほど狭くなる。内訳型の出品では
    ページ名にキャラ名が無い（内訳にだけある）ことがあるので、広い方も必ず出す。
    """
    b = brand_short(brand)
    m = _TITLE_BRAND_RE.match(_nfkc(title))
    if m and (m.group(2).lower() in _nfkc(brand).lower() or b.lower() in m.group(2).lower()
              or m.group(1) in _nfkc(brand)):
        # 商品名の先頭が「バンダイ(BANDAI)」なら日本語側をブランドとして使い、本文からは外す
        b = m.group(1).strip("[]【】")
        brand = f"{brand} {m.group(1)}"
    words = _title_words(title, brand, part_numbers(title, model))
    chara = next((w for w in words if any(c in w for c in CHARACTER_WORDS)), "")
    kind = next((w for w in words if w != chara and w != b
                 and not any(c == w for c in CHARACTER_WORDS)), "")
    narrow = [x for x in (b, kind, chara) if x]
    wide = [x for x in (b, kind) if x]
    if not kind:                       # 種類が取れないときは先頭2語で代用
        narrow = [x for x in [b] + words[:2] if x]
        wide = [x for x in [b] + words[:1] if x]
    qs = [" ".join(dict.fromkeys(narrow)), " ".join(dict.fromkeys(wide))]
    return [q for q in dict.fromkeys(qs) if q and q != b]


def search_url(word: str) -> str:
    """SD の検索 URL。robots.txt で `*` 宛に許可されている `/p/do/psl/?word=`。"""
    return SEARCH_BASE + urllib.parse.quote(word, safe="")


def plan(jan: str, title: str = "", brand: str = "", model: str = "") -> list[tuple[str, str]]:
    """[(段, 検索語)] を照会順に返す。段は 'jan' / 'partno' / 'name'。"""
    steps: list[tuple[str, str]] = []
    if jan:
        steps.append(("jan", jan))
    steps += [("partno", p) for p in part_numbers(title, model, jan)]
    steps += [("name", q) for q in name_queries(title, brand, model)]
    return steps
