"""サプライヤーの「業態」を、秘書カズヨが管理画面から取った CSV から補う。

なぜ要るか:
    Buyer API のサプライヤーオブジェクトは **`id` / `corp_name` / `trade_name` の3つだけ**で、
    業態（メーカー／卸専業／卸および小売業／その他）を持ちません（公式スキーマで確認済み）。
    社長が見たいのは「**取引できるメーカー**」なので、業態が無いと第1階層が作れません。

    業態は NETSEA の管理画面「取引申請状況」にあり、ログインが要ります。
    2026-08-31 にカズヨが社長のログイン中に取得しました（480社）。

    ⚠️ この CSV は **社長のログインが要る一次情報**です。API では再取得できません。
       取引先が増えたら取り直しが必要で、その時はまたログインの一手が要ります。

突合の方法:
    CSV には **サプライヤーID がありません**（画面に出ないため）。名前で寄せるしかない。
    `corp_name` と `trade_name` の両方を正規化して当てます。
    **当たらなかった社は空欄にします。推測で業態を埋めません。**
"""

import csv
import re
from pathlib import Path
from typing import Optional

# 取引状況。ここに無いものは発注できないので候補から外す。
STATUS_ACTIVE = "取引中"

# 業態の大分類。CSV の値は「メーカー（雑貨）」のように種別＋商材ジャンルが入っている。
CATEGORY_MAKER = "メーカー"

_SUFFIX = re.compile(
    r"(株式会社|有限会社|合同会社|合資会社|\(株\)|（株）|\(有\)|（有）"
    r"|Co\.,?\s*Ltd\.?|CO\.,?\s*LTD\.?|LIMITED|LTD|INC\.?|Corporation)",
    re.IGNORECASE,
)
_NOISE = re.compile(r"[\s　・,，.。「」『』\-—–_／/()（）]")


def normalize_name(name: str) -> str:
    """社名の表記ゆれを潰す。法人格・記号・空白を落として小文字化するだけ。

    凝った正規化はしません。**当たらなければ空欄にする**方針なので、
    無理に寄せて別の会社の業態を貼る方が害が大きいためです。
    """
    s = _SUFFIX.sub("", str(name or ""))
    return _NOISE.sub("", s).lower()


class SupplierProfiles:
    """取引申請状況 CSV を読み、社名から業態・取引状況を引ける形にする。"""

    def __init__(self, rows: list):
        self.rows = rows
        self._by_name: dict = {}
        for r in rows:
            key = normalize_name(r.get("サプライヤー名"))
            if key:
                self._by_name.setdefault(key, r)

    @classmethod
    def load(cls, path) -> "SupplierProfiles":
        path = Path(path)
        if not path.exists():
            return cls([])
        with open(path, encoding="utf-8") as f:
            return cls(list(csv.DictReader(f)))

    def __len__(self) -> int:
        return len(self.rows)

    def lookup(self, *names) -> Optional[dict]:
        """corp_name / trade_name のどれかで当てる。当たらなければ None。"""
        for name in names:
            row = self._by_name.get(normalize_name(name))
            if row:
                return row
        return None

    def business_type(self, *names) -> str:
        """業態の生値（例: 「メーカー（雑貨）」）。不明なら空文字。"""
        row = self.lookup(*names)
        return (row or {}).get("業態", "") or ""

    def trade_status(self, *names) -> str:
        row = self.lookup(*names)
        return (row or {}).get("取引状況", "") or ""

    def is_maker(self, *names) -> bool:
        return self.business_type(*names).startswith(CATEGORY_MAKER)

    def is_orderable(self, *names) -> Optional[bool]:
        """発注できる相手か。**名寄せに失敗したら None**（False にしない）。

        「取引拒否」「保留中再申請」「退会済み」は発注できません。
        ただし *不明* を *駄目* に倒すと、突合ミスで正当な取引先が消えます。
        """
        status = self.trade_status(*names)
        if not status:
            return None
        return status == STATUS_ACTIVE


def sort_key_makers_first(profiles: "SupplierProfiles"):
    """メーカー → 卸専業 → その他 の順に並べるためのキー関数を返す。

    社長の狙いは**メーカー仕入れ**なので、限られた Keepa トークンはメーカーから使います
    （カズヨ指示 2026-08-31）。同じ業態の中は API が返した順（サプライヤーID昇順）のまま。
    """
    order = {"メーカー": 0, "卸専業": 1, "卸および小売業": 2, "その他": 3}

    def key(supplier: dict):
        t = profiles.business_type(supplier.get("name"), supplier.get("corp_name"))
        return order.get(t.split("（")[0].split("(")[0], 9)

    return key
