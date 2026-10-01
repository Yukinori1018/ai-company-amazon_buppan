"""SD から1ページ取る共通関数。**429/503 はその場で例外にする。再試行しない。**

🔴 2026-10-01 に全面的に書き直した。前の版には次の2つの誤りがあった。

1. **429/503 を内部で指数バックオフして再試行していた。**
   相手が「やめてくれ」と言っているのに、同じプロセスが待って叩き直す実装だった。
   しかも最終的に失敗すると `Failed` になり、呼び出し側では「1件の取得失敗」に見えた。
   → **429/503 は専用の例外 `RateLimited` にして、その場で全体を止める。**
     その日は打ち切り、翌日は間隔を倍にして再開する（`_backoff.py`）。
     CLAUDE.md §3.3-18。

2. **「urllib は 429 で弾かれる／curl は 200 を返す。原因は TLS フィンガープリント」と書いてあった。**
   これは**反証済み**（CLAUDE.md §3.3-13）。順序を入れ替えたら `urllib`=200 / `curl`=429 になった。
   再現していたのはクライアントの違いではなく**実行順序**である。
   → **クライアントを替えることは回避策ではない。**ここでは標準ライブラリの `urllib` を使う。
     サブプロセスを呼ばないぶん単純で、テストしやすい。

🔴 通信の指紋を偽装する手段（`curl-impersonate`・`tls-client`・指紋を真似るヘッドレス
   ブラウザ）は例外なく使わない（CLAUDE.md §3.3-14）。**調整するのはペースだけ。**
"""
from __future__ import annotations

import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

HEADERS = {"User-Agent": UA, "Accept-Language": "ja"}


class Blocked(RuntimeError):
    """Cloudflare チャレンジに落ちた。"""


class Failed(RuntimeError):
    """HTTP ステータスが 200 以外（429/503 を除く）。**1件ぶんの失敗。**"""


class RateLimited(RuntimeError):
    """🔴 SD が 429 / 503 を返した。**相手が「やめてくれ」と言っている状態。**

    `26_候補提案パイプライン/superdelivery.py` の `Fetcher.RateLimited` と同じ契約。
    （2つのディレクトリにまたがる import を増やさないために定義は分けているが、
      意味・扱いは同一。どちらも「1件の失敗ではなく、全体を止める理由」。）

    **自動の再試行はしない。**同日中の再試行もしない。
    `_budget.Budget.note_rate_limited()` を呼んでその日を打ち切り、
    翌日は間隔を1段上げて再開する。
    """


def fetch(url: str, *, timeout: int = 40, opener=None) -> str:
    """URL を取って本文を返す。

    - 200 以外はすべて例外。**黙って空文字を返さない**（「SD に無かった」に化ける）
    - 429 / 503 → `RateLimited`（**再試行しない**）
    - Cloudflare チャレンジ → `Blocked`
    - それ以外 → `Failed`

    `opener` はテスト用。既定は `urllib.request.urlopen`。
    """
    open_url = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        body = open_url(req, timeout=timeout).read()
    except urllib.error.HTTPError as exc:
        if exc.code in (429, 503):
            raise RateLimited(
                f"SD が HTTP {exc.code} を返しました（{url}）。"
                "**自動で再試行しません。**本日はここで打ち切り、"
                "翌日は間隔を1段上げて再開します。") from exc
        raise Failed(f"HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise Failed(f"{exc.reason}: {url}") from exc
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)
    if "Just a moment" in text or "cf-challenge" in text:
        raise Blocked(url)
    return text
