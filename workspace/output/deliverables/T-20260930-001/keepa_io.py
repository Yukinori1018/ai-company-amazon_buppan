"""Keepa への入出力だけを持つ薄いラッパー（T-20260930-001）。

- 判定ロジック（maker_rules.py）から Keepa を隠す。SP-API 等へ差し替えるときはここだけ直す。
- 生レスポンスは **agent_output/T-20260930-001/raw/** に gzip で保存する（PUBLIC リポに出さない＝Keepa 規約）。
  同じ呼び出しは保存済みファイルから読むので、再実行は0トークン。
- API キーは `KEEPA_API_KEY` 環境変数 → `~/.config/ai-company-amazon-buppan/keepa.env`。リポには置かない。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
RAW = REPO / "workspace/output/agent_output/T-20260930-001/raw"
KEY_FILE = Path("~/.config/ai-company-amazon-buppan/keepa.env").expanduser()
DOMAIN_JP = 5


def api_key() -> str:
    if os.environ.get("KEEPA_API_KEY"):
        return os.environ["KEEPA_API_KEY"].strip()
    for line in KEY_FILE.read_text().splitlines():
        if line.startswith("KEEPA_API_KEY"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"KEEPA_API_KEY が {KEY_FILE} にありません")


def _get(path: str, params: dict, timeout: int = 300) -> dict:
    q = urllib.parse.urlencode({"key": api_key(), **params})
    b = urllib.request.urlopen(f"https://api.keepa.com/{path}?{q}", timeout=timeout).read()
    if b[:2] == b"\x1f\x8b":  # Content-Encoding が付かない gzip がある（memory: keepa_api_gotchas）
        b = gzip.decompress(b)
    return json.loads(b)


def tokens_left() -> int:
    return _get("token", {}).get("tokensLeft", 0)


def wait_for(n: int, log=print) -> None:
    """残高が n 以上になるまで待つ（補充は 20/分）。"""
    while True:
        left = tokens_left()
        if left >= n:
            return
        log(f"  token 待ち: 残 {left} / 必要 {n}")
        time.sleep(min(600, max(60, (n - left) * 3)))


def _cache(name: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    return RAW / name


def _load(p: Path):
    return json.loads(gzip.decompress(p.read_bytes()))


def _save(p: Path, obj) -> None:
    p.write_bytes(gzip.compress(json.dumps(obj, ensure_ascii=False).encode()))


def finder(selection: dict, tag: str, offline: bool = False) -> dict:
    """Product Finder。selection のハッシュでキャッシュ。戻り値は Keepa のレスポンス dict。"""
    h = hashlib.sha1(json.dumps(selection, sort_keys=True).encode()).hexdigest()[:10]
    p = _cache(f"finder_{tag}_{h}.json.gz")
    if p.exists():
        return _load(p)["resp"]
    if offline:
        raise FileNotFoundError(p)
    per = int(selection.get("perPage", 50))
    wait_for(10 + per // 100 + 5)
    d = _get("query", {"domain": DOMAIN_JP, "selection": json.dumps(selection)})
    if d.get("error"):
        raise RuntimeError(f"Finder error: {d['error']}")
    _save(p, {"selection": selection, "resp": d})
    return d


def products(asins: list[str], tag: str, offline: bool = False, log=print) -> list[dict]:
    """product を 100件ずつ取得（stats=365・history=0・offers なし＝1 token/ASIN）。
    キャッシュ済みのバッチは読むだけ。"""
    out: list[dict] = []
    for i in range(0, len(asins), 100):
        chunk = asins[i:i + 100]
        p = _cache(f"prod_{tag}_{i // 100:04d}.json.gz")
        if p.exists():
            d = _load(p)
        else:
            if offline:
                continue
            wait_for(len(chunk) + 5, log)
            d = _get("product", {"domain": DOMAIN_JP, "asin": ",".join(chunk),
                                 "stats": 365, "history": 0, "buybox": 1})
            if d.get("error"):
                raise RuntimeError(f"product error: {d['error']}")
            _save(p, d)
            log(f"  prod batch {i // 100:04d}: {len(d.get('products') or [])}件 "
                f"consumed {d.get('tokensConsumed')} left {d.get('tokensLeft')}")
        out.extend(d.get("products") or [])
    return out


def sellers(ids: list[str], offline: bool = False, log=print) -> dict[str, str]:
    """セラーID → 表示名。キャッシュ（raw/seller_names.json）優先。1 token/セラー。"""
    cp = RAW / "seller_names.json"
    cache = json.loads(cp.read_text()) if cp.exists() else {}
    need = [s for s in dict.fromkeys(ids) if s and s not in cache]
    for i in range(0, 0 if offline else len(need), 100):
        chunk = need[i:i + 100]
        wait_for(len(chunk) + 5, log)
        d = _get("seller", {"domain": DOMAIN_JP, "seller": ",".join(chunk)})
        for sid, v in (d.get("sellers") or {}).items():
            cache[sid] = (v or {}).get("sellerName") or ""
        for sid in chunk:
            cache.setdefault(sid, "")
        cp.write_text(json.dumps(cache, ensure_ascii=False))
        log(f"  sellers {len(chunk)}件 consumed {d.get('tokensConsumed')}")
    return cache
