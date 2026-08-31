"""gBizINFO API アダプタ（T-20260831-004 / タカシ）.

経済産業省 gBizINFO の法人基本情報を引くための薄いラッパー。
差し替え可能性のため、HTTP の詳細をここだけに閉じ込める。

規約遵守（社長がトークン申請時に申告した利用目的）:
  「約1,300社の企業名リストに法人番号・従業員数・資本金・所在地を照合し、
    取引先候補を規模で絞り込む社内分析。再配布・外部公開なし。
    API は1秒1リクエスト以下。」
→ MIN_INTERVAL_SEC で必ずスロットリングする。キャッシュは再実行時の
  無駄なアクセスを避けるためのもので、規約遵守の一部。

トークンは Git に置かない。~/.config/ai-company-amazon-buppan/gbizinfo.env の
GBIZINFO_TOKEN を読む（chmod 600・リポ外）。

実測メモ（2026-08-31）:
  * 検索 /hojin?name=... は **部分一致**。完全一致で返ってくる保証はない。
    limit は 100 が上限で、100件返ったら「打ち切り」の可能性を疑う必要がある。
  * 検索レスポンスに employee_number は入らない。**必ず詳細を引き直す。**
  * 詳細 /hojin/{法人番号} が返すのは
    corporate_number / postal_code / location / name / kana / status /
    employee_number / business_summary / company_url / update_date。
    capital_stock と date_of_establishment は **返ってこない行が大半**
    （持っていれば入るが、実測した範囲では常に欠測）。
  * 商号は全角で格納されている（"Ｈａｍｅｅ株式会社"）。照合前に NFKC が要る。
  * status は "-"（現存）と "閉鎖" がある。閉鎖は候補から外す。
  * 一括ダウンロード（/hojin/Download, downfile=Kihonjoho）は
    2026-08-31 に2通りの投げ方で試して**両方サーバーエラー**。API を採用した。
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE = "https://info.gbiz.go.jp/hojin/v1/hojin"
ENV_PATH = Path.home() / ".config" / "ai-company-amazon-buppan" / "gbizinfo.env"

#: 申告した「1秒1リクエスト以下」を必ず下回るための最小間隔（秒）。
MIN_INTERVAL_SEC = 1.15

#: 検索の limit 上限（実測）。ここに張り付いたら結果が打ち切られている。
SEARCH_LIMIT = 100


def load_token() -> str:
    """~/.config/... の env ファイルから GBIZINFO_TOKEN を読む。"""
    if not ENV_PATH.exists():
        raise RuntimeError(f"トークンファイルがありません: {ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("GBIZINFO_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"GBIZINFO_TOKEN が見つかりません: {ENV_PATH}")


class GBizInfo:
    """スロットリングとディスクキャッシュ付きの gBizINFO クライアント。

    キャッシュキーはリクエスト URL。同じ問い合わせを2回投げない。
    """

    def __init__(self, cache_dir: Path, token: str | None = None) -> None:
        self.token = token or load_token()
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.cache_dir / "gbiz_cache.json"
        self._cache: dict[str, Any] = {}
        if self._cache_file.exists():
            self._cache = json.loads(self._cache_file.read_text(encoding="utf-8"))
        self._last_call = 0.0
        self.live_calls = 0  # 実際にネットワークへ出た回数（規約遵守の実測値）

    # ---- 低レベル ------------------------------------------------------

    def _get(self, url: str) -> dict[str, Any]:
        if url in self._cache:
            return self._cache[url]

        wait = MIN_INTERVAL_SEC - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)

        req = urllib.request.Request(
            url,
            headers={
                "X-hojinInfo-api-token": self.token,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 404 は「その法人番号は無い」。異常ではないので空で返す。
            body = {"_http_error": e.code, "hojin-infos": []}
        except Exception as e:  # ネットワーク断など。呼び出し側で握れるよう記録
            body = {"_error": repr(e), "hojin-infos": []}
        finally:
            self._last_call = time.monotonic()
            self.live_calls += 1

        self._cache[url] = body
        return body

    def flush(self) -> None:
        """キャッシュをディスクへ書き戻す。長時間ジョブでは途中でも呼ぶ。"""
        tmp = self._cache_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._cache, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(self._cache_file)

    # ---- 高レベル ------------------------------------------------------

    def search_by_name(self, name: str, limit: int = SEARCH_LIMIT) -> list[dict]:
        """商号の部分一致検索。employee_number は入らない点に注意。"""
        qs = urllib.parse.urlencode({"name": name, "limit": limit})
        body = self._get(f"{BASE}?{qs}")
        return body.get("hojin-infos") or []

    def fetch_by_number(self, corporate_number: str) -> dict | None:
        """法人番号で基本情報を引く。employee_number はここでしか取れない。"""
        body = self._get(f"{BASE}/{corporate_number}")
        infos = body.get("hojin-infos") or []
        return infos[0] if infos else None
