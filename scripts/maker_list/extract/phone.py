"""日本の電話番号／FAX番号の抽出・正規化・種別判定。

UI にも HTML パーサにも依存しない純関数だけを置く（テスト可能にするため）。
社長が実際にダイヤルする値なので、曖昧なものは「取らない」side に倒す。
郵便番号・年月日・住所の地番を電話番号として拾うのが最悪の事故。
"""

from __future__ import annotations

import re
import unicodedata

# 桁区切りが -, －, ー, (), 全角括弧, 中黒, スペースのいずれかで来る現実に合わせる。
# 3ブロック必須（0XX-XXX-XXXX 形式）。2ブロックの郵便番号 003-0862 はここで落ちる。
_SEP = r"[-－‐‑–—ー―.．\s]"
_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(?:\(|（)?(0\d{1,4})(?:\)|）)?"      # 市外局番（(011) 形式を含む）
    rf"{_SEP}{{0,2}}(\d{{1,4}})"            # 市内局番
    rf"{_SEP}{{1,2}}(\d{{3,4}})"            # 加入者番号
    r"(?![0-9])"
)

# 携帯・PHS・IP 電話の先頭。携帯は「個人の携帯番号」の可能性があるので既定で除外する。
_MOBILE_PREFIXES = ("070", "080", "090")
_IP_PREFIXES = ("050",)
_TOLLFREE_PREFIXES = ("0120", "0800")

# この語が近くにあれば FAX とみなす
_FAX_WORDS = ("fax", "ｆａｘ", "ファクシミリ", "ファックス", "ファクス", "f.", "（f）", "(f)")
_TEL_WORDS = ("tel", "ｔｅｌ", "電話", "phone", "ＴＥＬ", "代表")


def _digits(*groups: str) -> str:
    return "".join(re.sub(r"\D", "", g) for g in groups)


def _label(before: str, after: str) -> str:
    """番号の直前／直後の語から TEL / FAX を判定する。

    『TEL 03-1111-2222 FAX 03-1111-3333』のように2つ並ぶのが普通なので、
    「文脈に fax が含まれるか」では次の項目のラベルを拾ってしまう。
    **番号に一番近いマーカー**を採ること。
    """
    best = ("不明", 10 ** 6)
    for words, name in ((_FAX_WORDS, "FAX"), (_TEL_WORDS, "TEL")):
        for w in words:
            i = before.rfind(w)
            if i >= 0:
                dist = len(before) - (i + len(w))
                if dist < best[1]:
                    best = (name, dist)
    if best[0] != "不明":
        return best[0]
    # 『03-1111-3333（FAX）』のような後置表記だけ、直後の短い窓も見る
    for words, name in ((_FAX_WORDS, "FAX"), (_TEL_WORDS, "TEL")):
        if any(w in after for w in words):
            return name
    return "不明"


def classify(number: str) -> str:
    """正規化済みの番号を種別に分ける。"""
    d = re.sub(r"\D", "", number)
    if d.startswith(_TOLLFREE_PREFIXES):
        return "フリーダイヤル"
    if d.startswith(_MOBILE_PREFIXES):
        return "携帯"
    if d.startswith(_IP_PREFIXES):
        return "IP電話"
    return "固定電話"


def is_valid(digits: str) -> bool:
    """日本の電話番号として成立する桁数か。

    固定・0120 は 10 桁、携帯・0800 は 11 桁。郵便番号（7桁）はここで落ちる。
    """
    if not digits.startswith("0"):
        return False
    if digits.startswith("0120"):
        return len(digits) == 10
    if digits.startswith("0800"):
        return len(digits) == 11
    if digits.startswith(_MOBILE_PREFIXES):
        return len(digits) == 11
    return len(digits) == 10


def normalize(raw: str) -> str | None:
    """『(011)-000-0000』『０３－１２３４－５６７８』→『011-000-0000』。"""
    m = _PATTERN.search(unicodedata.normalize("NFKC", raw))
    if not m:
        return None
    d = _digits(*m.groups())
    if not is_valid(d):
        return None
    return "-".join(re.sub(r"\D", "", g) for g in m.groups())


def find_all(text: str, *, keep_mobile: bool = False) -> list[dict]:
    """テキストから電話番号らしきものを全部拾って、種別と前後文脈を付けて返す。

    keep_mobile=False（既定）のとき 070/080/090 は落とす。
    個人の携帯番号が PUBLIC リポや営業リストに混ざるのを防ぐため。
    """
    t = unicodedata.normalize("NFKC", text)
    out: list[dict] = []
    seen: set[str] = set()
    for m in _PATTERN.finditer(t):
        d = _digits(*m.groups())
        if not is_valid(d):
            continue
        kind = classify(d)
        if kind == "携帯" and not keep_mobile:
            continue
        pretty = "-".join(re.sub(r"\D", "", g) for g in m.groups())
        if pretty in seen:
            continue
        seen.add(pretty)
        before = t[max(0, m.start() - 24): m.start()].lower()
        after = t[m.end(): m.end() + 10].lower()
        label = _label(before, after)
        out.append({"番号": pretty, "種別": kind, "ラベル": label, "文脈": before.strip()[-24:]})
    return out


def pick_tel_and_fax(text: str) -> tuple[str | None, str | None, str | None]:
    """本文から「代表電話」と「FAX」を1つずつ選ぶ。

    戻り値 = (電話番号, 番号の種別, FAX番号)

    選び方（優先順）:
      1. FAX とラベルされたものは電話候補から外す
      2. TEL とラベルされた固定電話 → 最優先（代表番号である確率が高い）
      3. ラベル不明の固定電話
      4. フリーダイヤル（0120 は担当者に繋がらないので最後）
    """
    found = find_all(text)
    faxes = [f for f in found if f["ラベル"] == "FAX"]
    tels = [f for f in found if f["ラベル"] != "FAX"]

    def rank(f: dict) -> tuple[int, int]:
        kind_rank = {"固定電話": 0, "IP電話": 1, "フリーダイヤル": 2}.get(f["種別"], 3)
        label_rank = 0 if f["ラベル"] == "TEL" else 1
        return (kind_rank, label_rank)

    tels.sort(key=rank)
    tel = tels[0] if tels else None
    fax = faxes[0] if faxes else None
    return (tel["番号"] if tel else None,
            tel["種別"] if tel else None,
            fax["番号"] if fax else None)
