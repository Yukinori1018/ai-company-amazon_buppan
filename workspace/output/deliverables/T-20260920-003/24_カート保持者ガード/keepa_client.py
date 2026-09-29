#!/usr/bin/env python3
"""Keepa API ラッパー。判定ロジック（verdict.py）から Keepa を隠すための1枚。

なぜラッパーにするか: いずれ SP-API の `GetItemOffers` に替えたくなります（本体の有無は
SP-API でも取れる）。そのとき書き換えるのはこのファイルだけで済むようにしておきます。

シークレット: `KEEPA_API_KEY` 環境変数 → 無ければ `~/.config/ai-company-amazon-buppan/keepa.env`。
**リポジトリには絶対に置きません**（このリポは PUBLIC です）。
"""

from __future__ import annotations

import gzip
import json
import os
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

KEEPA_DOMAIN_JP = 5
DEFAULT_KEY_FILE = Path("~/.config/ai-company-amazon-buppan/keepa.env").expanduser()

# 1リクエストで投げられる ASIN 数の上限（Keepa の仕様）。
BATCH_SIZE = 100


class KeepaError(RuntimeError):
    pass


def load_api_key(key_file: Path = DEFAULT_KEY_FILE) -> str:
    key = os.environ.get("KEEPA_API_KEY")
    if key:
        return key.strip()
    if not key_file.exists():
        raise KeepaError(
            f"APIキーが見つかりません。環境変数 KEEPA_API_KEY か {key_file} を用意してください。")
    for line in key_file.read_text().splitlines():
        if line.startswith("KEEPA_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise KeepaError(f"{key_file} に KEEPA_API_KEY の行がありません。")


@dataclass
class FetchResult:
    products: list[dict]
    tokens_consumed: int
    tokens_left: int | None
    offers_requested: int


class KeepaClient:
    """商品取得だけを行う最小クライアント。書き込み系の API は一切呼びません。"""

    def __init__(self, api_key: str | None = None, domain: int = KEEPA_DOMAIN_JP,
                 timeout: int = 600):
        self.api_key = api_key or load_api_key()
        self.domain = domain
        self.timeout = timeout

    def _get(self, url: str) -> dict:
        raw = urllib.request.urlopen(url, timeout=self.timeout).read()
        if raw[:2] == b"\x1f\x8b":          # Keepa は gzip で返すことがある
            raw = gzip.decompress(raw)
        return json.loads(raw.decode())

    def fetch_for_cart_check(self, asins: list[str], offers: int = 20,
                             sleep: float = 1.0) -> FetchResult:
        """§3.3 の3点チェックに必要な項目を1回で取る。

        付けているパラメータと、その理由:
          - `stats=365` : outOfStockPercentage365 / buyBoxStats（チェック2・1）
          - `history=1` : buyBoxSellerIdHistory（チェック1の根拠C）
          - `buybox=1`  : buyBoxSellerId / buyBoxIsAmazon（チェック1の根拠A・B）
          - `offers=N`  : ライブの新品オファー一覧（チェック3）
        """
        products: list[dict] = []
        consumed, left = 0, None
        for i in range(0, len(asins), BATCH_SIZE):
            chunk = asins[i:i + BATCH_SIZE]
            url = (f"https://api.keepa.com/product?key={self.api_key}&domain={self.domain}"
                   f"&asin={','.join(chunk)}&stats=365&history=1&buybox=1&offers={offers}")
            data = self._get(url)
            if data.get("error"):
                raise KeepaError(str(data["error"]))
            products.extend(data.get("products") or [])
            consumed += data.get("tokensConsumed") or 0
            left = data.get("tokensLeft", left)
            if i + BATCH_SIZE < len(asins):
                time.sleep(sleep)
        return FetchResult(products, consumed, left, offers)


def estimate_tokens(asin_count: int, offers: int = 20) -> int:
    """トークン消費の見積り。実測 6 トークン / ASIN（2026-09-30・offers=20）。

    内訳（Keepa 公式の課金表より）: 商品1 + offers 6 相当 ... のはずが実測は合計6でした。
    **実測を正とします**（README §トークン消費）。offers を外せば 1〜2 まで落ちますが、
    チェック3が UNKNOWN になるので §3.3 の用途では外せません。
    """
    return asin_count * (6 if offers else 2)
