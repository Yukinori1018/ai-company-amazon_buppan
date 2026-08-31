"""Amazon ブランド名 → gBizINFO 商号 の照合ロジック（T-20260831-004 / タカシ）.

UI にも API 呼び出しにも依存しない純関数だけを置く。ここが単体でテストできる。

設計の前提（agents/it_engineer/memory/knowledge_maker_name_normalization.md）:
  Amazon の `manufacturer` は「商号」ではなく「ブランド表記」。
  したがって **引けないのが普通** であり、引けなかったことを
  「実在しない」「落とす理由」に読み替えてはいけない。
"""

from __future__ import annotations

import re
import unicodedata

#: NFKC でも消えない不可視文字。実データに存在した（LRM 付きの "‎バーベイタム"）。
INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏﻿ "), None)

#: 日本の法人格。照合キーからは落とすが、元の表記は動かさない。
CORP_FORMS = [
    "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
    "特定非営利活動法人", "社会福祉法人", "医療法人", "学校法人",
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
]

#: 英文の法人格。"KEIYO ENGINEERING CO.,LTD." のような行が実在する。
CORP_FORMS_EN = [
    "co.,ltd.", "co., ltd.", "co.ltd", "co ltd", "coltd",
    "corporation", "corp.", "inc.", "ltd.", "llc", "k.k.", "kk",
]

#: 商号ではない飾り。実データから拾ったものだけを列挙する。
DECORATIONS = [
    "【日本製】", "【正規品】", "【国内正規品】", "日本製", "正規品",
    "ノーブランド品",
]


def clean(s: str) -> str:
    """不可視文字を除去して NFKC 正規化する。表記そのものは壊さない。"""
    return unicodedata.normalize("NFKC", (s or "").translate(INVISIBLE)).strip()


def split_aliases(raw: str) -> list[str]:
    """`ワコーズ(Wako's)` のような和英併記を「主表記 + 別名」へ分ける。

    括弧の内と外のどちらが主かは実データで両方あるので、順序は付けるが
    どちらも検索候補として残す。スラッシュ区切りも同様に割る。
    """
    s = clean(raw)
    for d in DECORATIONS:
        s = s.replace(d, " ")
    inner = re.findall(r"[（(\[【]([^）)\]】]{1,40})[）)\]】]", s)
    outer = re.sub(r"[（(\[【][^）)\]】]*[）)\]】]", " ", s)
    out: list[str] = []
    for chunk in [outer, *inner]:
        for part in re.split(r"[/／|｜]", chunk):
            part = part.strip(" 　,、・-–—")
            if part:
                out.append(part)
    # 重複除去（順序保持）
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def split_scripts(s: str) -> list[str]:
    """文字種の境界で割る。**単語では割らない**（過去に誤マッチを出した）。

    `アストロプロダクツ Astro Products` を空白で割って `Products` を別名にすると
    `P&S Detailing Products` に誤マッチした。和名の塊とラテン文字の塊の2つだけ作る。
    """
    jp = "".join(re.findall(r"[ぁ-んァ-ヴー一-龥々〆ヵヶ]+", s))
    latin = " ".join(re.findall(r"[A-Za-z0-9&'\.\-]+", s)).strip()
    out = [x for x in (jp, latin) if len(x) >= 2]
    return [x for x in out if x != s]


def strip_corp_form(s: str) -> str:
    """法人格を落とす。照合キー生成用で、表示名には使わない。"""
    t = clean(s)
    for f in CORP_FORMS:
        t = t.replace(f, "")
    low = t.lower()
    for f in CORP_FORMS_EN:
        low = low.replace(f, " ")
    # 元の大文字小文字を残したいので、英法人格の除去は lower 側の結果長で判断せず
    # 単純に再構築する（照合キーはどうせ小文字化するため実害なし）
    return low.strip(" 　,、・")


def match_key(s: str) -> str:
    """照合用のキー。記号・空白を全部落として小文字化する。

    実データに `ジャニーズ･…`（半角中黒）や `ワー ナー・ブ ラザース`（紛れ込んだ空白）
    があったため、記号と空白は照合キーから完全に除去する。
    """
    t = strip_corp_form(s)
    t = unicodedata.normalize("NFKC", t).lower()
    t = re.sub(r"[^0-9a-zぁ-んァ-ヴー一-龥々〆ヵヶ]", "", t)
    return t


def query_variants(raw: str, max_variants: int = 3) -> list[str]:
    """検索に投げる文字列を優先順に返す。API 回数を抑えるため上限を切る。"""
    out: list[str] = []
    for alias in split_aliases(raw):
        for cand in [alias, *split_scripts(alias)]:
            cand = cand.strip()
            # 1文字・記号のみは検索してもノイズしか返らない
            if len(match_key(cand)) < 2:
                continue
            if cand not in out:
                out.append(cand)
    return out[:max_variants]


def pick_exact(candidates: list[dict], query: str) -> list[dict]:
    """検索結果から「商号が完全一致」する現存法人だけを抜く。

    部分一致で返ってくるノイズ（`Hamee` → `Ｈａｍｅｅｄ　Ｔｒａｄｉｎｇ合同会社`）を
    ここで捨てる。**複数残ったら推測で1社に決めず、そのまま複数を返す。**
    """
    key = match_key(query)
    if not key:
        return []
    return [
        c
        for c in candidates
        if c.get("status") != "閉鎖" and match_key(c.get("name", "")) == key
    ]
