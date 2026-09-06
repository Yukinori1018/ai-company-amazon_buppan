#!/usr/bin/env python3
"""Keepa の stats を ASIN 単位で取り、ドロップ数と裏取り指標を JSON へ落とす。

使い方:
    python3 fetch_keepa.py B0015L0RGK B001MS8HRW B0G5DGWVGM > out.json

設計メモ:
- offers を付けないと BuyBox / オファー数 / RATING / COUNT_REVIEWS が更新されない
  （memory: reference_keepa_official_docs）。裏取り指標を見るので必ず付ける。
- 1リクエストで最大100 ASIN。トークン節約のためまとめて投げる。
- 生レスポンスはリポに残さない（PUBLIC リポ・Keepa T&C §11(1)）。
  呼び出し側で必要な集計だけ取り出すこと。
"""
import gzip, io, json, os, sys, urllib.parse, urllib.request

ENV = os.path.expanduser(
    "~/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260521-005/code/.env")


def api_key() -> str:
    k = os.environ.get("KEEPA_API_KEY")
    if k:
        return k
    with open(ENV) as f:
        for line in f:
            if line.startswith("KEEPA_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("KEEPA_API_KEY が見つかりません")


# stats オブジェクトから取り出す「Keepa 固有の加工値ではない」メタと、加工値。
# 加工値は成果物に書かない。分析スクリプトの中だけで使う。
def fetch(asins, domain=5, days=365, offers=20):
    q = urllib.parse.urlencode({
        "key": api_key(), "domain": domain, "asin": ",".join(asins),
        "stats": days, "offers": offers, "history": 0, "rating": 1,
    })
    req = urllib.request.Request(f"https://api.keepa.com/product?{q}",
                                 headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    # Keepa は Content-Encoding ヘッダを付けずに gzip を返すことがある。マジックで判定する。
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return json.loads(body.decode("utf-8"))


if __name__ == "__main__":
    print(json.dumps(fetch(sys.argv[1:]), ensure_ascii=False))
