# -*- coding: utf-8 -*-
"""連絡先エンリッチメントの共通スキーマ。

このモジュールに「1社ぶんのデータの形」を集約する。
resolver も store も CSV 出力もすべてここを参照するので、
列を足したいときはここだけ直せばよい。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

# --- 確度（3値。これ以外の値は使わない） -----------------------------------
CONF_CONFIRMED = "確定"  # 公式サイト or 公的DBで実物を確認した
CONF_CANDIDATE = "候補"  # それらしいが同名企業の可能性が残る
CONF_UNKNOWN = "不明"    # 取れなかった／判定できない

CONFIDENCE_ORDER = {CONF_CONFIRMED: 0, CONF_CANDIDATE: 1, CONF_UNKNOWN: 2}


def worst_confidence(values):
    """複数ソースの確度を束ねるときは「一番弱いもの」に合わせる（安全側）。"""
    vals = [v for v in values if v in CONFIDENCE_ORDER]
    if not vals:
        return CONF_UNKNOWN
    return max(vals, key=lambda v: CONFIDENCE_ORDER[v])


# --- 分類（ソースの効き方がここで変わる。事実ではなくルーティング用のヒント）
CLS_JP_CORP = "和名法人らしき"
CLS_EN_BRAND = "英字ブランド"
CLS_NOBRAND = "ノーブランド・個人らしき"
CLS_FOREIGN = "海外法人"
ALL_CLASSES = (CLS_JP_CORP, CLS_EN_BRAND, CLS_NOBRAND, CLS_FOREIGN)


@dataclass
class MakerRow:
    """入力1行（Amazon のブランド文字列＋名寄せ結果）。resolver への引数。"""

    raw_name: str                      # 元CSVそのまま。最終CSVの結合キー
    normalized_name: str               # 表示用の正規化名
    core_name: str                     # 法人格・記号を落とした照合用の芯
    aliases: List[str] = field(default_factory=list)   # 括弧内表記・和英別名など
    match_keys: List[str] = field(default_factory=list)  # 照合キー（casefold済）
    category: str = CLS_EN_BRAND       # 分類フラグ
    source_row: Dict[str, str] = field(default_factory=dict)  # 元CSVの全列

    def to_dict(self):
        return asdict(self)


@dataclass
class ContactFields:
    """1つの resolver が返す連絡先。**推測で埋めない。**

    取れなかった項目は空文字のまま返し、理由を note に書く。
    """

    official_name: str = ""     # 正式商号
    corporate_number: str = ""  # 法人番号（13桁）
    address: str = ""           # 所在地
    website: str = ""           # 公式HP
    tel: str = ""               # 電話
    contact_form: str = ""      # 問い合わせフォームURL
    email: str = ""             # メール
    source: str = ""            # 取得手段（resolver 名）
    source_url: str = ""        # 出典URL
    confidence: str = CONF_UNKNOWN
    note: str = ""              # 備考（取れなかった理由はここ）

    #: マージ対象になる「値」の列。source/confidence/note は別扱い。
    VALUE_FIELDS = (
        "official_name",
        "corporate_number",
        "address",
        "website",
        "tel",
        "contact_form",
        "email",
    )

    def is_empty(self) -> bool:
        return not any(getattr(self, f) for f in self.VALUE_FIELDS)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, str]) -> "ContactFields":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


# --- 最終CSVの列（この順で出す） -------------------------------------------
CSV_COLUMNS = [
    "メーカー名",
    "正規化名",
    "分類",
    "正式商号",
    "法人番号",
    "所在地",
    "公式HP",
    "電話",
    "問い合わせフォームURL",
    "メール",
    "取得手段",
    "出典URL",
    "確度",
    "備考",
    "別名",  # 照合に使った和英別名。Googleシート反映時は落としてよい
]

#: 「埋まった」を数えるときに見る列（連絡先の実体があるか）
FILL_FIELDS = ("公式HP", "電話", "問い合わせフォームURL", "メール")


def to_csv_row(row: MakerRow, contact: ContactFields) -> Dict[str, str]:
    """MakerRow + ContactFields を最終CSVの1行に平坦化する。"""
    return {
        "メーカー名": row.raw_name,
        "正規化名": row.normalized_name,
        "分類": row.category,
        "正式商号": contact.official_name,
        "法人番号": contact.corporate_number,
        "所在地": contact.address,
        "公式HP": contact.website,
        "電話": contact.tel,
        "問い合わせフォームURL": contact.contact_form,
        "メール": contact.email,
        "取得手段": contact.source,
        "出典URL": contact.source_url,
        "確度": contact.confidence,
        "備考": contact.note,
        "別名": " | ".join(row.aliases),
    }
