"""複数仕入れ先をまとめて引く合成クライアント（Yahoo + 楽天 + NETSEA(卸) を1つに見せる）。

狙い（タカシ）:
  原石の歩留まりが低い主因は「仕入れ先が1つ＝突合の母数が小さい」こと。
  Yahoo に加えて楽天・NETSEA(卸)を足すと、同じ JAN に対して仕入元が増え、
  「より安い有効な仕入値」を採用できるため、黒字判定に乗る候補が増える。
  特に NETSEA は卸価格のため同JANで最安になりやすい（黒字化の本丸）。
  クライアント数に依存しない実装（N本でも動く）。トークン未設定の仕入元は各自サンプルへ落ちる。

設計:
  - YahooShoppingClient と同一の .search() インターフェースを持つ（pipeline は無改造で使える）。
  - search() は各仕入元を引いてマージする。
      * JAN直指定検索（jan_code 指定）: 各仕入元から同JANを引き、**最も安い有効仕入値**の
        1件を採用（どの仕入元由来かは item.source に保持）。pipeline の最安採用ロジックの肝。
      * キーワード検索: 各仕入元の結果を素朴に連結（生候補の一覧表示用）。
  - 戻り値は YahooItem（共通正規化型）。下流は source を見れば仕入元が分かる。
  - 1つの仕入元が落ちても（キー無し→サンプル）全体は動く（各クライアントが自前でフォールバック）。
"""

from typing import Optional, Protocol

from adapters.yahoo_shopping import YahooItem


class _SupplierClient(Protocol):
    """仕入元クライアントの最小契約（Yahoo/楽天が満たす）。"""

    def search(
        self,
        query: str = "",
        *,
        results: int = 20,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        jan_code: Optional[str] = None,
    ) -> list[YahooItem]: ...


class MultiSupplierClient:
    """複数の仕入元クライアントを束ねる合成クライアント。

    例:
        supplier = MultiSupplierClient([YahooShoppingClient(), RakutenShoppingClient()])
        items = supplier.search(jan_code="4900000000024")  # → 最安の1件（source付き）
    """

    def __init__(self, clients: list[_SupplierClient]):
        # 空リストは事故のもと。最低1つは要る。
        self.clients = [c for c in clients if c is not None]

    @property
    def is_live(self) -> bool:
        """いずれかの仕入元が本番接続なら True（UIの本番/サンプル表示用）。"""
        return any(getattr(c, "is_live", False) for c in self.clients)

    def live_sources(self) -> list[str]:
        """本番接続している仕入元名の一覧（UI表示用）。"""
        names = []
        for c in self.clients:
            if getattr(c, "is_live", False):
                # source 名はクラス側の定数 or 既定で推定。
                names.append(getattr(c, "SOURCE_NAME", None) or _guess_source(c))
        return names

    def search(
        self,
        query: str = "",
        *,
        results: int = 20,
        price_from: Optional[int] = None,
        price_to: Optional[int] = None,
        jan_code: Optional[str] = None,
    ) -> list[YahooItem]:
        """全仕入元を引いてマージ。JAN指定時は最安1件、キーワード時は連結。"""
        per_source: list[list[YahooItem]] = []
        for c in self.clients:
            try:
                per_source.append(
                    c.search(
                        query, results=results, price_from=price_from,
                        price_to=price_to, jan_code=jan_code,
                    )
                )
            except Exception:
                # 1仕入元の失敗で全体を落とさない（honesty: 黙って空を返すのではなくスキップ）。
                per_source.append([])

        if jan_code:
            return self._cheapest_for_jan(per_source, jan_code)
        # キーワード検索は連結。突合できるのは JAN付きだけなので、
        # **JAN付きを優先**して上位に集める（results で切り詰めても突合母数を減らさない）。
        # 楽天は仕様上 janCode を返さず JAN無しになりがちなため、この優先で Yahoo由来の
        # JAN付き候補が Amazon突合に確実に乗る（mode(い)の0件化を防ぐ肝）。
        merged = [it for items in per_source for it in items]
        merged.sort(key=lambda it: (
            it.jan is None,                       # JAN付き(False=0)を先頭へ
            it.price if it.price > 0 else 10**9,  # 同条件なら安い順
        ))
        return merged[:results] if results else merged

    @staticmethod
    def _cheapest_for_jan(
        per_source: list[list[YahooItem]], jan_code: str
    ) -> list[YahooItem]:
        """各仕入元から同JANの有効候補を集め、最安の1件だけ返す（複数仕入元の最安採用）。

        有効＝ price > 0 かつ jan が一致（または仕入元が JAN直指定で補完済み）。
        全滅なら空リスト（でっち上げない）。
        """
        candidates: list[YahooItem] = []
        for items in per_source:
            for it in items:
                if it.price > 0 and (it.jan == jan_code or it.jan is None):
                    candidates.append(it)
        if not candidates:
            return []
        cheapest = min(candidates, key=lambda it: it.price)
        return [cheapest]


def _guess_source(client) -> str:
    """クライアント名から仕入元ラベルを推定（SOURCE_NAME が無い場合の保険）。"""
    name = type(client).__name__.lower()
    if "rakuten" in name:
        return "楽天"
    if "yahoo" in name:
        return "Yahoo"
    if "netsea" in name:
        return "NETSEA"
    return type(client).__name__
