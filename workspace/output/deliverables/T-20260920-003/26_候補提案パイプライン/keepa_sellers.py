#!/usr/bin/env python3
"""セラーID → セラー表示名。メーカー直販の検出（§3.3 の5番目）に使う1枚。

Keepa の `/product` はセラーID しか返しません。「サンワサプライ直営【サンワダイレクト】」
という**名前**は `/seller` で引きます。名前が無いと 9/30 の見送り事例を機械で拾えません。

トークン: **1セラー 1トークン**（storefront は付けない）。同じセラーは1回しか引かず、
プロセスをまたいでもキャッシュに残します（既定 `agent_output/.../seller_names.json`）。
キャッシュがあるぶんは0トークンです。

差し替え: SP-API の `GetItemOffers` にも `SellerId` はありますが**名前は返りません**。
名前が要るなら Keepa か実画面です。ここを1枚にしておけば、乗り換え先はこのファイルだけ直せば済みます。
"""

from __future__ import annotations

import gzip
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

from keepa_client import KEEPA_DOMAIN_JP, KeepaError, load_api_key  # noqa: E402

# 1リクエストに載せるセラー数（Keepa の上限は100）。
BATCH = 100


class SellerNames:
    """セラー名の解決役。キャッシュ優先・不足分だけ API を叩く。"""

    def __init__(self, cache_path: Path, api_key: str | None = None,
                 domain: int = KEEPA_DOMAIN_JP, timeout: int = 120):
        self.cache_path = cache_path
        self.domain = domain
        self.timeout = timeout
        self._api_key = api_key
        self.tokens_consumed = 0
        self.cache: dict[str, str] = {}
        if cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.cache = {}

    @property
    def api_key(self) -> str:
        if not self._api_key:
            self._api_key = load_api_key()
        return self._api_key

    def _get(self, url: str) -> dict:
        raw = urllib.request.urlopen(url, timeout=self.timeout).read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode())

    def resolve(self, seller_ids: list[str], allow_network: bool = True,
                budget: int | None = None) -> dict[str, str]:
        """{sellerId: sellerName} を返す。取れなかった ID は**入れません**（None 扱い）。

        `budget` はこの呼び出しで使ってよいトークン数の上限。足りなければ引ける分だけ引きます。
        引けなかったぶんは名前なし ＝ メーカー直販判定は UNKNOWN になります（fail-closed）。
        """
        ids = [s for s in dict.fromkeys(seller_ids) if s and not str(s).startswith("-")]
        missing = [s for s in ids if s not in self.cache]
        if missing and allow_network:
            if budget is not None:
                missing = missing[:max(0, budget)]
            for i in range(0, len(missing), BATCH):
                chunk = missing[i:i + BATCH]
                url = ("https://api.keepa.com/seller?"
                       + urllib.parse.urlencode({"key": self.api_key, "domain": self.domain,
                                                 "seller": ",".join(chunk)}))
                try:
                    data = self._get(url)
                except Exception as e:              # noqa: BLE001 - 名前が取れないだけで止めない
                    raise KeepaError(f"/seller の取得に失敗: {e}") from e
                self.tokens_consumed += data.get("tokensConsumed") or 0
                for sid, obj in (data.get("sellers") or {}).items():
                    name = (obj or {}).get("sellerName")
                    if name:
                        self.cache[sid] = name
            self.save()
        return {s: self.cache[s] for s in ids if s in self.cache}

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
