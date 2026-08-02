"""Keepa Product Finder「SHOW API QUERY」の URL / 生 selection JSON パーサ（上級者向け）。

なぜ要るか（タカシ・差分2）:
  本アプリの基本動線は「アプリ側スライダーで5条件を組む」（社長はKeepaサイトを触らない）。
  ただし Keepa の Product Finder 画面で細かく条件を作り込んだ上級者向けに、
  そこで吐かれる「SHOW API QUERY」のURL（または生の selection JSON）を貼り付けるだけで
  同じ条件を find_products に流せるようにする。これは任意機能（折りたたみオプション）。

受け付ける入力（どれでもOK）:
  1) 完全なURL:  https://api.keepa.com/query?key=...&domain=5&selection=<JSON or urlencoded>
  2) selection= 以降だけ:  selection={"current_SALES_gte":1000,...}
  3) 生の selection JSON:  {"current_SALES_gte":1000, "categories_include":[3828871], ...}

設計方針:
  - 純関数・標準ライブラリのみ（urllib / json）。外部依存なし（YAGNI）。
  - find_products(selection, ...) にそのまま渡せる dict を返す。
  - パース失敗は KeepaQueryParseError で「何がダメか」を日本語で明示（UIでそのまま見せる）。
  - Keepa が要求する最小要件（selection は dict・perPage>=50・page など）を緩く補完する。
"""

import json
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse


class KeepaQueryParseError(ValueError):
    """Keepa の検索URL/JSON のパースに失敗したことを表す明確な例外（UI表示用）。"""


def _extract_selection_text(raw: str) -> str:
    """入力文字列から selection 部分（JSON文字列）を取り出す。

    URL なら query の selection= を取り出して urldecode。
    `selection=...` だけ・生JSON だけの場合はそれぞれ適切に扱う。
    """
    text = (raw or "").strip()
    if not text:
        raise KeepaQueryParseError("空です。Keepaの検索URL、または selection の JSON を貼り付けてください。")

    # 1) 生 JSON（先頭が { ）ならそのまま返す。
    if text.startswith("{"):
        return text

    # 2) URL（スキーム付き or api.keepa.com を含む）なら query から selection を抜く。
    if text.startswith("http://") or text.startswith("https://") or "keepa.com" in text:
        parsed = urlparse(text if "://" in text else "https://" + text)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if "selection" not in qs or not qs["selection"]:
            raise KeepaQueryParseError(
                "URL に selection= が見つかりません。Keepaの Product Finder で "
                "『SHOW API QUERY』が吐く、selection を含むURLを貼り付けてください。"
            )
        # parse_qs は + を半角空白に変換済み。selection は JSON なので二重デコードは不要。
        return qs["selection"][0]

    # 3) `selection=...` 形式（key=value の断片）。
    if text.startswith("selection="):
        val = text[len("selection="):]
        return unquote(val)

    # 4) どれにも当てはまらない → 生JSONとして最後に試す（unquote してから）。
    return unquote(text)


def parse_keepa_query(raw: str) -> dict:
    """Keepa の検索URL/JSON を find_products に渡せる selection(dict) へパースする。

    返り値: selection(dict)。perPage / page を最小要件で補完する。
    失敗時: KeepaQueryParseError（日本語メッセージ）。
    """
    sel_text = _extract_selection_text(raw)
    try:
        selection = json.loads(sel_text)
    except json.JSONDecodeError as e:
        raise KeepaQueryParseError(
            f"selection の JSON を解釈できませんでした（{e.msg}）。"
            "Keepaの『SHOW API QUERY』のURL全体、または selection の JSON をそのまま貼り付けてください。"
        ) from e

    if not isinstance(selection, dict):
        raise KeepaQueryParseError(
            "selection が JSON オブジェクト（{ }）ではありません。"
            "Keepaの『SHOW API QUERY』が吐く selection を貼り付けてください。"
        )

    # Keepa の最小要件をベストエフォートで補完（無いと query が弾くことがある）。
    selection.setdefault("perPage", 50)
    if isinstance(selection.get("perPage"), (int, float)) and selection["perPage"] < 50:
        selection["perPage"] = 50  # Keepa の最小 perPage 要件
    selection.setdefault("page", 0)
    return selection


def describe_selection(selection: dict) -> str:
    """パース結果を社長が読める1行サマリにする（貼り付けた条件の確認表示用）。"""
    parts = []

    def rng(label, gte, lte, unit=""):
        lo = selection.get(gte)
        hi = selection.get(lte)
        if lo is not None or hi is not None:
            parts.append(f"{label} {('' if lo is None else lo)}〜{('' if hi is None else hi)}{unit}")

    rng("ランク", "current_SALES_gte", "current_SALES_lte", "位")
    rng("出品者数", "current_COUNT_NEW_gte", "current_COUNT_NEW_lte", "人")
    rng("価格", "current_NEW_gte", "current_NEW_lte", "円")
    cats = selection.get("categories_include")
    if cats:
        parts.append(f"カテゴリ{len(cats)}件")
    if selection.get("current_AMAZON_lte") == -1:
        parts.append("Amazon本体=在庫切れ")
    return " / ".join(parts) if parts else "（条件の主要フィールドを検出できませんでした）"
