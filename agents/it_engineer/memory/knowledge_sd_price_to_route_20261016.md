# SD 実画面の卸値（JAN キー）→ 台帳 SD 経路への合流の型（2026-10-16・T-20260920-003）

## 何をしたか
カネイシ（SD）× ユニマットリケン 61 JAN（秘書の実画面・通常単価・税抜）を台帳へ。
10/15 のカネイシ10 JAN は手で変換していたので `26_候補提案パイプライン/sd_price_to_route.py` に1本化した。

    python3 sd_price_to_route.py <価格CSV> --supplier カネイシ --buyer-name "…" --tag <日付_名前> --tokens N --buybox-tokens M
    python3 ledger_refresh.py --dry-run → 本番 → --dry-run（差分0を確認）

出力は sd_buylist20261009/sd_route_override_<tag>.csv（ledger_refresh の glob `2026101[2-9]*` で読まれる）と
unknown_queue/keepa_stage_<tag>.jsonl（台帳外 ASIN の採点用の商品データ）。

## トークンの実測
- `code` 逆引き：61 JAN → 237 ASIN・**237トークン（1 JAN 平均3.9）**。ユニマットリケンはセット出品が多く、
  supplier_screen の初期レート 2.0/JAN は過小（予算250で偶然収まった）。メーカー単位で入れるときは **JAN×4** を見込む
- buybox 取り直し 3/ASIN × 237＝711。合計 約950（残高1200から）

## 罠
- `code` 逆引きの商品にも stats に `buyBoxSellerId` キーが入る（値は None が多い）→ `_has_bb()` は真になる。
  「buybox 取得済み」の判定にキーの有無を使わない。値が入っているか、取得の経路で見る
- セラー名は keepa_sellers.SellerNames で解決（1セラー1トークン・キャッシュあり）。メーカー公式カートの検査はこの名前で見る

## 結果（237 ASIN）
GO 0／実績枠 0／UNKNOWN 99／NO-GO 138。カート本体 29・メーカー本人のカート 0。
中央値で手残り0円以上は4件だけ（うち2件は本体カート）。ユニマットリケンの棚は「本体か、セット組みの転売屋」で、
卸の通常単価では単品は赤字（C）が主。セット出品の多くはランクなし＝売れていない。
