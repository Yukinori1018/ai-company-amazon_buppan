# Sato-Scope Discovery を PoiPoiポケットに寄せた改修（T-20260521-005 / 2026-06-09）

社長提供動画『PoiPoiポケットを活用した自動化せどり戦略』に合わせてツールを改修した時の学び。

## 設計判断
- **PoiPoiのURL貼り付けは技術的に必須でない**。本アプリは既に Keepa `/query` の selection を内部で
  組み立てている（FinderPreset.to_selection）。よって「アプリ側スライダーで条件を組む」を主役にし、
  URL貼り付けは上級者向け expander の任意機能にした（社長は Keepa サイトを触らず完結できる）。
- レイアウトはサイドバーradio方式を廃止し **3フェーズ縦並び**（① 抽出条件 → ② 実行 → ③ 絞り込み&最終判断）。
  既存4モード（キーワード/カテゴリ自動/NETSEA卸/売れ筋）は Phase1 の「抽出方法」に統合。

## Keepa API メモ（実装で確定した非自明な点）
- **Amazon本体在庫=アウトオブストック**を Product Finder selection で表すには
  `current_AMAZON_gte=-1` & `current_AMAZON_lte=-1`（Keepa は -1=在庫なし）。
  presets.py の FinderPreset に `require_amazon_oos` フラグを足し、to_selection で付与する。
- 過去価格推移は **フル csv（history=1）を要求するとトークンが重い**。stats=90 で既に返る
  `min90/avg90/avg30 + current(BuyBox→New)` から代表点系列を組むだけで「最悪相場（過去最安）」判定には十分。
  → adapters/amazon_data.py の `_extract_price_history()`。

## 委譲の鉄則（崩さない）
- 後段フィルタ（Phase3）も最悪相場シミュレーションも **calc/profit.py に再計算を委譲**。
  UI 側は計算済みの値の比較・表示だけ。`pipeline.simulate_worst_case()` が profit.calculate を呼ぶ。

## 追加/変更ファイル
- discovery/keepa_query_url.py（URL/JSONパーサ・新規）＋ test_keepa_query_url.py
- discovery/presets.py（FinderPreset に require_amazon_oos / 「PoiPoi標準」プリセット追加）
- adapters/amazon_data.py（AmazonProduct.price_history / _extract_price_history / Sample擬似履歴）
- discovery/pipeline.py（DiscoveryRow に price_history/category_key/size_key、simulate_worst_case、
  discover_by_finder の override_selection）
- app_discovery.py（3フェーズUIに全面改修）
- discovery/test_poipoi.py（新規）

テストは 178 passed（全パス・既存壊さず）。
