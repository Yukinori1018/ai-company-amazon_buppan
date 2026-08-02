# メーカー仕入れ候補 抽出ハーネス（T-20260705-002）

狙いの商品 → その裏のメーカー（ブランド/manufacturer）を炙り出し、
「問い合わせ先メーカー一覧（メーカー台帳）」の種を作る。EC STARs流メーカー仕入れの入口。

## 成果物

| ファイル | 内容 |
|---|---|
| `maker_candidates.csv` | メーカー台帳（本成果物）。13列・実データ12行（2026-07-05 実走） |
| `extract_maker_candidates.py` | 抽出スクリプト（既存 Keepa 資産を再利用） |
| `selection.json` | Keepa Product Finder の検索条件（そのまま流せる） |

## 実行結果（2026-07-05 実走・本物のKeepaデータ）

- Product Finder 該当 **50件** → 詳細取得 **15件**（トークン厳格キャップ）
- 規制/対象外（成人向けDVD・音楽CD）3件を後処理で除外 → **12行**
- 消費トークン **約26**（110→84）。ユニークメーカー **10社**

## selection.json のフィールド（Keepa Product Finder / domain=5=co.jp）

| フィールド | 値 | 意味 |
|---|---|---|
| `current_SALES_gte/_lte` | 1 / 50000 | 売れ筋ランク 1〜50,000位（gte=下限＝トップ、lte=上限＝売れ行き足切り） |
| `current_COUNT_NEW_gte` | 2 | **FBA/新品出品者数 2以上**（メーカー仕入れ3基準の1つ。上限は付けず薄い順にsortで拾う） |
| `current_AMAZON_gte/_lte` | -1 / -1 | **Amazon本体が在庫切れ**（Keepaは -1=在庫なし。gte=lte=-1 で本体不在に限定） |
| `current_NEW_gte` | 1000 | 新品価格 1,000円以上 |
| `categories_exclude` | [160384011, 52374051, 57239051] | ドラッグストア/ビューティー/食品ルートノードを除外（薬機法・化粧品・酒・食品対策） |
| `sort` | [["current_COUNT_NEW","asc"]] | 出品者が最も薄い順（相乗り少＝独占しやすい原石を上に） |
| `perPage` | 50 | Finder取得件数（詳細取得は別途15件にキャップ） |

> ⚠️ **正確な指定方法の注記**：
> - **Amazon本体除外**は `current_AMAZON_gte=-1 & current_AMAZON_lte=-1`（本体在庫切れ）。BuyBox主でなく本体在庫の有無で判定。
> - **出品者数**は Keepa では `current_COUNT_NEW`（新品オファー数）。`gte=2` が「2以上」。
> - `categories_exclude` は今回の実走で有効に機能した（規制カテゴリ由来のヒットは無かった）。ただし取りこぼし対策として下記キーワード後処理を二段で必ずかける。

## 規制・対象外の二段ガード（捏造せず正直に除外）

1. `categories_exclude`（selection）でドラッグストア/ビューティー/食品ルートを除外。
2. スクリプト内 `BLOCK_WORDS`/`BLOCK_CATEGORY_WORDS` でタイトル・categoryTree を後処理除外
   （薬機法/PSE/酒/医療/化粧品/サプリ/食品＋メディア・成人向けDVD/CD）。

## 再実行手順（次のローカル回でそのまま動く）

```bash
cd workspace/output/deliverables/T-20260705-002/research

# 1) トークン残高だけ確認（無料の /token エンドポイント・0トークン）
python3 extract_maker_candidates.py --dry

# 2) 実走（残トークン >= 35 目安が必要。足りなければ自動でSTOP）
MAX_DETAIL=15 python3 extract_maker_candidates.py

# 3) トークンを一切使わず、保存済み raw JSON からCSVだけ再生成（フィルタ調整用）
python3 extract_maker_candidates.py --from-raw
```

- APIキーは `agent_output/T-20260521-005/code/.env` の `KEEPA_API_KEY` を自動ロード（deliverables側の `code/.env` は存在しない点に注意）。
- 詳細取得ASINは `MAX_DETAIL`（既定15・上限20）で厳格キャップ。
- raw な Keepa product は `agent_output/T-20260705-002/keepa_raw_products.json` に保存済み。

## 制約・注意（判明事項）

- **Keepa残トークンが僅少**（本日22:xx時点で70→補充で110。refill=20/分）。1バッチ15件で約26消費。連続実走は数分待ちが必要。
- **既存 `_product_to_amazon()` は brand/manufacturer を捨てる**（AmazonProduct に列が無い）。本スクリプトは raw product dict から `brand`→`manufacturer` を直接読む（追加トークン0）。将来、恒久化するなら AmazonProduct に `brand`/`manufacturer` 列を足すのが筋。
- 海外ブランド（BAUERFEIND/IK Multimedia/DigiTech）は**国内正規輸入代理店経由**が窓口。メーカー仕入れの本命は国内自社ブランド（FIELDOOR）や独立HPを持たない小規模販売元（SEAWIND）。
- `公式HP`/`問い合わせ手段`/`中小メーカー判定`の一部はWeb1次調査で補完（出典は下記）。Amazon専売の無名輸入ブランドは「不明」と正直に記載（捏造しない）。

## 1次調査の出典（2026-07-05取得）

- FIELDOOR: fieldoor.com、株式会社クローバー会社概要（PRTimes/各まとめ）※運営会社名に情報揺れあり要確認
- BAUERFEIND: bauerfeind.p-supply.co.jp（正規輸入代理店パシフィックサプライ株式会社）
- IK Multimedia: focal.co.jp（正規代理店フォーカルポイント株式会社）
- DigiTech: kandashokai.co.jp（正規輸入代理店 株式会社神田商会）
- SEAWIND: 楽天/Amazon「自然の恵みセレクト」ストア（独立コーポレートHP未確認）
