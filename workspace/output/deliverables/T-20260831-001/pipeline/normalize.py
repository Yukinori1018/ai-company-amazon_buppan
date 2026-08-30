# -*- coding: utf-8 -*-
"""メーカー名の正規化・別名抽出・分類。

ルールは「822行の実データを読んで確認した汚れ方」から起こしている。
実際に確認した汚れ（v14/03_メーカー名寄せ.csv）:

  不可視文字      '\\u200eバーベイタム(Verbatim)'
  全角英数        'ＡＮＤＥＲＹ' / 'ＹＡＺＡＫＩ' / 'ＭＥＮＧＬＩ盟励'
  法人格の略記    '矢崎エナジーシステム㈱'
  法人格の位置    '株式会社マーベラス' / 'イースター株式会社' / '株式会社 山本人形'
  括弧の和英併記  'パナソニック(Panasonic)' / 'CASIO(カシオ)' / 'Eufy (ユーフィ)'
  括弧が訳でない  'NBCユニバーサル・エンターテイメントジャパン(LAQ)'
  スラッシュ複数  'OM SYSTEM/オリンパス' / 'Ligare / ノーブランド品'
  中黒の異体字    'ジャニーズ･エンタテイメント' vs 'ジャニーズ・エンタテイメント'
  紛れ込んだ空白  'ワー ナー・ブ ラザース・ホームエ ンターテイ メント'
  海外法人格      'ZHONGSHAN TURBOS TECHNOLOGY CO.,LTD'
  実体なし        'ノーブランド品' / '株式会社'（社名が入っていない）

分類（category）は**事実ではなくルーティング用のヒント**。
どのソースを当てるかを決めるためのもので、間違っていても連絡先の正しさには影響しない。
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

from .schema import (
    MakerRow,
    CLS_JP_CORP,
    CLS_EN_BRAND,
    CLS_NOBRAND,
    CLS_FOREIGN,
)

# 不可視文字（LTR/RTL マーク・ゼロ幅・BOM・NBSP）
_INVISIBLE = re.compile("[​‌‍‎‏﻿ ]")

# 括弧（半角・全角・隅付き）
_PAREN = re.compile(r"[（(\[【]\s*(.+?)\s*[)）\]】]")

# 日本語（ひらがな・カタカナ・漢字・長音）
_JA_CHARS = r"぀-ヿ㐀-䶿一-鿿ｦ-ﾟ"
_HAS_JA = re.compile("[" + _JA_CHARS + "]")
_HAS_LATIN = re.compile(r"[A-Za-z]")

# 日本の法人格
_JP_LEGAL_FORMS = (
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "一般社団法人", "公益社団法人", "一般財団法人", "公益財団法人",
    "特定非営利活動法人", "協同組合", "農業協同組合",
)
_JP_LEGAL_RE = re.compile("|".join(_JP_LEGAL_FORMS))

# 略記 → 正式表記（NFKC 後の形で拾う。㈱ は NFKC で "(株)" になる）
_LEGAL_ABBREV = [
    (re.compile(r"\(株\)"), "株式会社"),
    (re.compile(r"\(有\)"), "有限会社"),
    (re.compile(r"\(合\)"), "合同会社"),
    (re.compile(r"\(社\)"), "社団法人"),
    (re.compile(r"\(財\)"), "財団法人"),
]

# 海外法人格（英字）。語境界で見る
_FOREIGN_LEGAL_RE = re.compile(
    r"(?:^|[\s.,&])(?:CO\.?\s*,?\s*LTD|CO\b|LTD|LIMITED|INC|CORP(?:ORATION)?|LLC|LLP|"
    r"GMBH|S\.?A\.?S?|B\.?V\.?|PTE|PTY|SDN\s+BHD|N\.?V\.?|A/S|AB|OY|SRL|S\.?P\.?A)\b",
    re.IGNORECASE,
)

# 実体のないメーカー名
_NOBRAND_RE = re.compile(
    r"ノーブランド|ノーネーム|no\s*brand|nobrand|generic|不明|その他|無印刻印なし",
    re.IGNORECASE,
)

# 照合キーから落とす記号（中黒の異体字・各種ダッシュ・アポストロフィ等）
_KEY_STRIP = re.compile(r"[\s・･·‧∙\-–—―_,.。、'’\"“”/／\\|+&()（）\[\]【】!！?？:：;；*]")


def strip_invisible(text: str) -> str:
    """不可視文字を落として NFKC 正規化し、連続空白を1つに畳む。

    NFKC が同時に片づけてくれるもの: 全角英数→半角、㈱→(株)、半角カナ→全角カナ。
    """
    if text is None:
        return ""
    s = _INVISIBLE.sub("", text)
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def canonicalize_legal_form(text: str) -> str:
    """(株) / ㈱ のような略記を「株式会社」に開く。位置（前株・後株）は動かさない。"""
    s = text
    for pattern, full in _LEGAL_ABBREV:
        s = pattern.sub(full, s)
    # 「株式会社 山本人形」→「株式会社山本人形」（法人格の直後の空白だけ詰める）
    s = re.sub("(" + "|".join(_JP_LEGAL_FORMS) + r")\s+", r"\1", s)
    s = re.sub(r"\s+(" + "|".join(_JP_LEGAL_FORMS) + ")", r"\1", s)
    return s.strip()


def strip_legal_form(text: str) -> str:
    """法人格を落とす。照合の芯（core_name）を作るのに使う。"""
    s = _JP_LEGAL_RE.sub("", text)
    s = _FOREIGN_LEGAL_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip(" .,")


def split_scripts(text: str) -> List[str]:
    """和英が空白で併記された文字列を「和名」「英名」に割る。

    'アストロプロダクツ Astro Products' -> ['アストロプロダクツ', 'Astro Products']

    単語単位で割らないのが肝。単語で割ると 'Astro Products' の 'Products' が
    'P&S Detailing Products' に誤マッチする（実データで踏んだ）。
    """
    if not (_HAS_JA.search(text) and _HAS_LATIN.search(text)):
        return []
    ja = " ".join(re.findall("[" + _JA_CHARS + r"0-9０-９]+", text)).strip()
    latin = " ".join(re.findall(r"[A-Za-z0-9&.'\-]+", text)).strip()
    return [x for x in (ja, latin) if len(x) >= 2]


def extract_variants(text: str) -> Tuple[str, List[str]]:
    """正規化済み文字列から (主表記, 別名リスト) を取り出す。

    主表記は「スラッシュ区切りの先頭」「括弧の外側」。
    括弧の中身・和英併記の相方・スラッシュの2つ目以降はすべて別名。
    """
    s = strip_invisible(text)
    chunks = [c.strip() for c in re.split(r"[/／]", s) if c.strip()]
    if not chunks:
        return "", []

    primary = ""
    variants: List[str] = []
    for i, chunk in enumerate(chunks):
        inner = _PAREN.findall(chunk)
        outer = _PAREN.sub(" ", chunk)
        outer = re.sub(r"\s+", " ", outer).strip()
        pieces = [canonicalize_legal_form(p) for p in [outer] + inner if p]
        for j, piece in enumerate(pieces):
            if i == 0 and j == 0 and not primary:
                primary = piece
            else:
                variants.append(piece)
            variants.extend(split_scripts(piece))

    if not primary:
        primary = canonicalize_legal_form(s)

    # 主表記と重複するもの・短すぎるものを落として順序を保つ
    seen = {match_key(primary)}
    uniq = []
    for v in variants:
        k = match_key(v)
        if not k or len(k) < 2 or k in seen:
            continue
        seen.add(k)
        uniq.append(v)
    return primary, uniq


def match_key(text: str) -> str:
    """照合キー。記号・法人格・大小文字の差を消す。表示には使わない。"""
    s = strip_invisible(text)
    s = canonicalize_legal_form(s)
    s = strip_legal_form(s)
    s = _KEY_STRIP.sub("", s)
    return s.casefold()


def classify(primary: str, aliases: List[str]) -> str:
    """分類フラグを1つ返す。判定順に意味がある。

    1. 実体なし（ノーブランド）      → 何をやっても引けないので最初に弾く
    2. 海外法人格が明示されている    → 日本の公的DBは効かない
    3. 和名（かな・漢字）が含まれる  → 日本の公的DB・和名検索が効く
    4. それ以外（英字のみ）          → ブランド名。法人特定に一段階要る
    """
    joined = " ".join([primary] + aliases)
    core = strip_legal_form(strip_invisible(primary))

    if _NOBRAND_RE.search(joined) or len(core) == 0:
        return CLS_NOBRAND
    if _FOREIGN_LEGAL_RE.search(joined):
        return CLS_FOREIGN
    if _HAS_JA.search(joined):
        return CLS_JP_CORP
    return CLS_EN_BRAND


def normalize_row(raw_name: str, source_row=None) -> MakerRow:
    """入力1行を MakerRow に正規化する。これがパイプラインの入口。"""
    primary, aliases = extract_variants(raw_name)
    keys = []
    for text in [primary] + aliases:
        k = match_key(text)
        if k and len(k) >= 2 and k not in keys:
            keys.append(k)
    return MakerRow(
        raw_name=raw_name,
        normalized_name=primary,
        core_name=strip_legal_form(primary),
        aliases=aliases,
        match_keys=keys,
        category=classify(primary, aliases),
        source_row=dict(source_row or {}),
    )


def duplicate_groups(rows):
    """正規化後に同一とみなせる行のグループを返す。

    822行は「名寄せ済み」とされているが、実際には
    'LEGO(レゴ)' と 'レゴ(LEGO)' のような取りこぼしが残っている。
    **行は畳まない**（元シートと1:1で結合できなくなるため）。数を報告するだけ。
    """
    buckets = {}
    for row in rows:
        for key in row.match_keys:
            buckets.setdefault(key, [])
            if row.raw_name not in buckets[key]:
                buckets[key].append(row.raw_name)
    groups = []
    seen = set()
    for names in buckets.values():
        if len(names) < 2:
            continue
        signature = tuple(sorted(names))
        if signature in seen:
            continue
        seen.add(signature)
        groups.append(list(names))
    return groups
