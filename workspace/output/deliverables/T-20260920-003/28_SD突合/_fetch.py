"""SD から1ページ取る共通関数。**必ず curl を使う。**

🔴 2026-09-30 の発見：**python の urllib は 429 で全部弾かれる。curl は 200 を返す。**
同じ URL・同じ User-Agent・同じヘッダでも結果が違った（urllib=429 / curl=200 を3回連続で再現）。
原因は TLS フィンガープリント（JA3）による判定と推測（確度：中）。requests / httpx も
同じ TLS スタックなので同様に弾かれる見込み。**「レート制限だ」と読み違えないこと**（半日を失った）。

→ HTTP クライアントは `curl` をサブプロセスで呼ぶ。`--compressed` で gzip も任せる。
"""
from __future__ import annotations
import subprocess, time

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


class Blocked(RuntimeError):
    """Cloudflare チャレンジに落ちた。"""


class Failed(RuntimeError):
    """HTTP ステータスが 200 以外で、リトライしても回復しなかった。"""


def fetch(url: str, *, timeout: int = 40, retries: int = 4) -> str:
    """URL を取って本文を返す。429/503 は指数バックオフ。"""
    wait = 8.0
    last = ""
    for attempt in range(retries + 1):
        proc = subprocess.run(
            ["curl", "-sL", "--compressed", "--max-time", str(timeout),
             "-A", UA, "-H", "Accept-Language: ja",
             "-w", "\n__HTTP_%{http_code}__", url],
            capture_output=True, text=True,
        )
        body = proc.stdout
        code = ""
        if "__HTTP_" in body:
            body, _, tail = body.rpartition("\n__HTTP_")
            code = tail.strip("_")
        last = code or f"curl-exit-{proc.returncode}"
        if code == "200":
            if "Just a moment" in body or "cf-challenge" in body:
                raise Blocked(url)
            return body
        if code in ("429", "503") and attempt < retries:
            print(f"    {code} → {wait:.0f}秒待って再試行 ({attempt + 1}/{retries})", flush=True)
            time.sleep(wait)
            wait *= 2
            continue
        if attempt < retries and not code:
            time.sleep(wait)
            wait *= 2
            continue
        break
    raise Failed(f"{last}: {url}")
