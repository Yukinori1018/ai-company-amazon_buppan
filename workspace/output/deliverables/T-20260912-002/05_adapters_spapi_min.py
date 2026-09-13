"""Amazon SP-API 最小ラッパー — 設計スケッチ（雛形。実行しない・鍵を要求しない）。

配置予定: adapters/spapi_min.py（T-20260521-005/code の adapters/ と同じ流儀）
状態    : 雛形。社長判断「実装 Go」（成立 3 社以上 or SKU 10 件超）まで実装しない。
出典    : workspace/output/deliverables/T-20260912-002/05_SP-API_同意前の最小構成.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⛔ 用途制限 — このモジュールが返すものは Amazon Services API の「Information」です。
   （AUP・DPP。法務ハルオ判定 2026-09-13 / T-20260912-002 §1-7。読まずに使わないこと）

✗ 禁止1: 取得値（出品者数・カート価格・手数料・reasonCode）を PUBLIC リポに置く
        AUP 4.6「Do not disclose Information, individually labelled or aggregated,
        to … any outside parties」。**集計値・平均・派生表も対象**（Keepa と違う）。
✗ 禁止2: 登録時の Roles・Use Case の範囲外の取得（AUP「not necessary for your
        Application's functionality」）。3 エンドポイント以外を足すなら Profile 再提出。
✗ 禁止3: 鍵（client_id / client_secret / refresh_token / access_token）を
        ファイル・環境変数・ログ・例外メッセージに書く。読むのは Keychain だけ。
✗ 禁止4: Amazon の事業に関する洞察を成果物に書く（AUP 4.5）。

○ 許可: 自社の仕入れ判断のために、ASIN 単位で時点値を取り、
        リポ外の専用 SQLite（~/Library/Application Support/satoy-spapi/）に保存する。
○ 許可: deliverables には「可否・件数・当社の決定」だけを書く。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

設計方針（タカシ）:
- netsea.py と同じく `is_live` / `last_error` で状態を正直に出す。例外を握らない。
- 鍵は macOS Keychain（service=satoy-spapi）から `security find-generic-password -w`
  で読む。.env は使わない（memory knowledge_mcp_secret_storage_design）。
- 3 エンドポイントだけ。レート制限はエンドポイントごとのトークンバケット
  （公式 rate/burst: getItemOffers 0.5/1、getListingsRestrictions 5/10、
   getMyFeesEstimateForASIN 1/2。サトル③ S3/S46/S47）。
- TLS 1.2 以上を固定（DPP 1.5）。SigV4 は不要（公式 Connect ページ、2026-09-13）。
- 保存は専用 SQLite。全行 source='SP-API' と fetched_at を持つ（DPP 1.8）。
- purge（DPP 1.7）・expire（Non-PII 18 か月）・rotation-status（DPP 1.4.2）を CLI に持つ。

⚠️ 正直な制約:
- 本ファイルは import しても何もしない。ネットワークにもディスクにも触らない。
- 関数本体は `raise NotImplementedError` か型だけ。実装時に埋める。
"""

from __future__ import annotations

import sqlite3
import ssl
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 定数（公式ドキュメント 2026-09-13 取得）
# ---------------------------------------------------------------------------
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SPAPI_ENDPOINT_FE = "https://sellingpartnerapi-fe.amazon.com"  # 日本は Far East
MARKETPLACE_ID_JP = "A1VC38T7YXB528"
USER_AGENT = "SatoySelect-spapi-min/0.1 (Language=Python; Platform=macOS)"

KEYCHAIN_SERVICE = "satoy-spapi"
KEYCHAIN_ACCOUNTS = ("client_id", "client_secret", "refresh_token")

DB_DIR = Path.home() / "Library" / "Application Support" / "satoy-spapi"  # リポ外
DB_PATH = DB_DIR / "spapi.sqlite"

DATA_PROVENANCE = "SP-API"
NON_PII_RETENTION_DAYS = 18 * 30  # 公式ガイダンス: Non-PII は最大 18 か月
ACCESS_LOG_RETENTION_DAYS = 365   # DPP §3: 契約中＋終了後 12 か月（下限）

# エンドポイントごとの公式レート（rate=毎秒補充, burst=上限）
RATE_LIMITS = {
    "getItemOffers": (0.5, 1),
    "getListingsRestrictions": (5.0, 10),
    "getMyFeesEstimateForASIN": (1.0, 2),
}

# ---------------------------------------------------------------------------
# SQLite スキーマ（専用 DB。他データと混ぜない＝DPP 1.8）
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
  asin TEXT NOT NULL, fetched_at TEXT NOT NULL,
  number_of_offers_json TEXT, buybox_price REAL, lowest_price REAL, sales_rank INTEGER,
  source TEXT NOT NULL DEFAULT 'SP-API',
  PRIMARY KEY (asin, fetched_at));
CREATE TABLE IF NOT EXISTS restrictions (
  asin TEXT NOT NULL, fetched_at TEXT NOT NULL,
  reason_code TEXT, approval_url TEXT,
  source TEXT NOT NULL DEFAULT 'SP-API',
  PRIMARY KEY (asin, fetched_at));
CREATE TABLE IF NOT EXISTS fees (
  asin TEXT NOT NULL, price REAL NOT NULL, is_fba INTEGER NOT NULL, fetched_at TEXT NOT NULL,
  total_fees REAL, fee_detail_json TEXT,
  source TEXT NOT NULL DEFAULT 'SP-API',
  PRIMARY KEY (asin, price, is_fba, fetched_at));
CREATE TABLE IF NOT EXISTS access_log (          -- DPP §3 記録保持。鍵は書かない
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, op TEXT NOT NULL, asin TEXT,
  http_status INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS key_rotation (        -- DPP 1.4.2 年次ローテの記録
  id INTEGER PRIMARY KEY, rotated_at TEXT NOT NULL, what TEXT NOT NULL, by_whom TEXT NOT NULL);
"""


# ---------------------------------------------------------------------------
# 鍵の取り出し（Keychain のみ）
# ---------------------------------------------------------------------------
def read_keychain(account: str) -> Optional[str]:
    """`security find-generic-password -s satoy-spapi -a <account> -w` の stdout を返す。

    無ければ None（例外にしない。is_live が False になるだけ）。
    戻り値をログ・例外・print に流さないこと。
    """
    if account not in KEYCHAIN_ACCOUNTS:
        raise ValueError(f"unknown keychain account: {account}")
    r = subprocess.run(
        ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
        capture_output=True, text=True,
    )
    return r.stdout.strip() or None if r.returncode == 0 else None


# ---------------------------------------------------------------------------
# レート制限（トークンバケット・エンドポイント別）
# ---------------------------------------------------------------------------
@dataclass
class TokenBucket:
    rate: float
    burst: int
    tokens: float = field(init=False)
    last: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens, self.last = float(self.burst), time.monotonic()

    def take(self) -> None:
        """1 トークン取れるまで待つ（同期・単一プロセス前提）。"""
        now = time.monotonic()
        self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens < 1:
            time.sleep((1 - self.tokens) / self.rate)
            self.tokens = 0.0
        else:
            self.tokens -= 1


# ---------------------------------------------------------------------------
# クライアント
# ---------------------------------------------------------------------------
class SpapiMinClient:
    """3 エンドポイントだけの薄いクライアント。

    使い方（実装後）:
        c = SpapiMinClient()             # Keychain を読む。無ければ is_live=False
        c.get_listing_restrictions("B0XXXXXXXX")   # → dict / None（last_error に理由）

    トークン: refresh_token → access_token（1 時間）。期限 5 分前に更新。
    """

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.client_id = read_keychain("client_id")
        self.client_secret = read_keychain("client_secret")
        self.refresh_token = read_keychain("refresh_token")
        self.last_error: Optional[str] = None
        self._access_token: Optional[str] = None
        self._access_expires_at: float = 0.0
        self._buckets = {op: TokenBucket(r, b) for op, (r, b) in RATE_LIMITS.items()}
        self._db_path = db_path
        self._ssl = ssl.create_default_context()
        self._ssl.minimum_version = ssl.TLSVersion.TLSv1_2  # DPP 1.5

    @property
    def is_live(self) -> bool:
        return all((self.client_id, self.client_secret, self.refresh_token))

    def _why_not_live(self) -> str:
        return (
            "SP-API の鍵が Keychain（service=satoy-spapi）にありません。"
            "登録は社長の一手（05_SP-API_同意前の最小構成.md §4）。"
        )

    # --- 認証 -------------------------------------------------------------
    def _access_token_fresh(self) -> str:
        """LWA: grant_type=refresh_token で access_token を得る。期限 5 分前で再取得。"""
        raise NotImplementedError("実装時: POST LWA_TOKEN_URL（TLS1.2+）。鍵をログに出さない")

    def _headers(self) -> dict:
        return {
            "x-amz-access-token": self._access_token_fresh(),
            "user-agent": USER_AGENT,
            "accept": "application/json",
        }

    # --- 3 エンドポイント ----------------------------------------------------
    def get_item_offers(self, asin: str, condition: str = "New") -> Optional[dict]:
        """Product Pricing v0 getItemOffers。出品者数・カート価格の時点値。0.5 rps。"""
        self._buckets["getItemOffers"].take()
        raise NotImplementedError

    def get_listing_restrictions(self, asin: str) -> Optional[dict]:
        """Listings Restrictions getListingsRestrictions。reasonCode でゲート判定。5 rps。"""
        self._buckets["getListingsRestrictions"].take()
        raise NotImplementedError

    def get_fees_estimate(self, asin: str, price: float, is_fba: bool = True) -> Optional[dict]:
        """Product Fees getMyFeesEstimateForASIN。手数料の公式見積。1 rps。"""
        self._buckets["getMyFeesEstimateForASIN"].take()
        raise NotImplementedError

    # --- 保存・削除（DPP 1.7 / 1.8 / §3） ------------------------------------
    def _db(self) -> sqlite3.Connection:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db_path)
        con.executescript(SCHEMA)
        return con

    def _log(self, op: str, asin: Optional[str], status: Optional[int], note: str = "") -> None:
        """access_log に 1 行。鍵・レスポンス本文は書かない。"""
        raise NotImplementedError

    def expire(self, days: int = NON_PII_RETENTION_DAYS) -> int:
        """fetched_at が days より古い行を削除。戻り値は削除行数。"""
        raise NotImplementedError

    def purge(self) -> None:
        """DB ファイル（と -wal/-shm）を削除する。DPP 1.7（30 日以内）。

        ⚠️ 不可逆な削除＝CLAUDE.md §4.1。呼ぶのは社長承認の後。
        """
        raise NotImplementedError

    def rotation_status(self) -> Optional[str]:
        """key_rotation の最終日を返す。12 か月を超えていれば呼び出し側が警告する。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# CLI（実装時）: python -m adapters.spapi_min {restrictions|offers|fees|expire|purge|rotation-status}
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    raise SystemExit("雛形です。実装は社長判断後（05_SP-API_同意前の最小構成.md §3-3）。")
