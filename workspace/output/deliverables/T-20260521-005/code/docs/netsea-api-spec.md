# NETSEA Buyer API 仕様まとめ（確定）

出典（OpenAPI 仕様本体を直接取得して解析）:
- spec ルート: https://api.netsea.jp/docs/buyer/openapi.json
- paths: https://api.netsea.jp/docs/buyer/paths/index.json
- 各スキーマ: https://api.netsea.jp/docs/buyer/schemas/*.json / request/*.json
- 公式マニュアル: https://www.netsea.jp/help/manual/api.html / Redoc: https://api.netsea.jp/docs/buyer/

取得日: 2026-06-06（タカシ）／運営: 株式会社SynaBiz（NETSEA = https://www.netsea.jp）

> ⚠️ JSページ（Redoc）はHTML直読み不可。上記の OpenAPI JSON を curl で取得して確定した。
> 推測ではなく仕様ファイルの実値。**不明な項目は「不明」と明記**している（でっち上げ無し）。

## ベースURL・認証
- ベースURL: `https://api.netsea.jp/buyer/v1/`
- 認証: リクエストヘッダ `Authorization: Bearer <アクセストークン>`
  - トークン発行: NETSEAマイページ https://www.netsea.jp/account/ のAPI設定画面
  - 有効期限: **180日**（再認証で半年延長／不要なトークンは削除）
  - 取得できるのは**承認済みサプライヤー**の商品・在庫・送料のみ
- エラー時フォーマット: `{"error": {"code", "subcode", "message"}}`
  - code: 0=不明 / 1=認証 / 2=パラメータ / 3=API内部 / 4=アクセス
  - HTTP: 400 Bad Request（入力不正・アクセス不可データ含む） / 401 Unauthorized（認証）

## エンドポイント一覧
| メソッド | パス | 用途 | 件数 |
|---|---|---|---|
| POST | `/items` | 商品一覧 | 1回100件（ソート=ダイレクト商品ID昇順） |
| GET | `/items/stock` | 在庫情報（direct_item_id 指定） | 1件 |
| GET | `/categories` | 商品カテゴリ一覧 | — |
| GET | `/suppliers` | 取引可能サプライヤー一覧 | — |
| GET | `/tariffs` | 送料一覧（サプライヤー別・都道府県別） | — |

## POST /items リクエスト（application/x-www-form-urlencoded）
- **必須**: `direct_item_ids` もしくは `supplier_ids` の**いずれか**（カンマ区切り・各最大10件）
- 任意フィルタ: `jan_code`(integer), `category_id`, `product_id`, `branch_code`, `label`,
  `price_range_from` / `price_range_to`（卸価格税抜の範囲）, `set_num`,
  `create_date_from/to`, `update_date_from/to`,
  `sold_out_flag`(Y=品切れ/N=在庫有), `deal_net_shop_flag`(ネット販売可否),
  `deal_net_auction_flag`, `net_bluk_order_flag`
- ページング: `next_direct_item_id`（100件超過時のみレスポンスに付与。次回リクエストに渡す）
- ⚠️ **フリーテキスト（キーワード）検索パラメータは存在しない**（不明＝無い）。
  検索起点は JAN / カテゴリ / サプライヤー / 商品ID。

## POST /items レスポンス商品フィールド（最重要）
トップレベル（`data[]` の各要素）:
`supplier_id, product_id, product_url, product_name, shop_name, create_date, update_date,
description, spec_size, jan_code, category_id, reference_price_type(O/M/C/H),
discount_rate, item_discount_rate, shop_discount_rate, delivery_terms,
ship_fee_type(Y/N), ship_fee, image_url_1..10, image_copy_flag,
deal_net_shop_flag, deal_net_auction_flag, direct_send_flag, net_bulk_order_flag, set[]`

`set[]`（規格/枝番ごと。**価格・在庫はここ**）:
`direct_item_id, branch_code, jan_code, label,
reference_price（上代＝希望小売 税抜）, price（卸価格単価 税抜）, set_num,
set_price（セット卸額 税込）, set_price_without_tax（セット卸額 税抜）, set_price_tax,
consumption_tax_class(0=標準/1=軽減8%/99=非課税), sold_out_flag(Y=品切れ/N=在庫あり)`

`reference_price_type`: O=オープンプライス / M=メーカー希望小売 / C=カタログ / H=販売企業設定

### タスクで求められた商品フィールドの有無（最重要回答）
| 項目 | 有無 | フィールド |
|---|---|---|
| JANコード | ✅あり | トップ `jan_code` ＋ `set[].jan_code` |
| 卸価格 | ✅あり | `set[].price`（税抜）/ `set[].set_price`（税込） |
| 希望小売価格 | ✅あり | `set[].reference_price`（上代税抜）＋ `reference_price_type` |
| 在庫 | ✅あり | `set[].sold_out_flag`（N=在庫あり）/ `GET /items/stock` |
| 送料 | ✅あり | `ship_fee` + `GET /tariffs`（都道府県別・段階設定対応） |
| 商品名 | ✅あり | `product_name` |
| 画像 | ✅あり | `image_url_1..10` |
| 商品URL | ✅あり | `product_url` |

## レート制限
- **不明**: OpenAPI 仕様に明記なし。規約第3条で「当社がアクセス回数・時間等を制約しうる」と規定。
  → 実装側は保守的に呼び出し間隔を置き、429/4xx は黙らず last_error に残す。

## 実装での扱い（adapters/netsea.py）
- 正規化型は Yahoo/楽天と共通の `YahooItem`。`source="NETSEA"`、`price` は**卸価格（税抜・set[].price）**。
- 1商品に複数 `set[]` がある → 「在庫あり×卸価格最安」の規格を採用して1件に集約。
  全規格品切れは `price=0`（突合対象外）。
- `jan_code` 指定時のみ本番 POST /items を叩く。JAN無しキーワードはサンプル粗集め
  （/items にフリーワード検索が無いため。フリーワードの網は Yahoo/楽天が担当）。
- トークン未設定・401・error フォーマット・通信失敗時はサンプルへフォールバックし
  `last_error` に理由を残す（社長次アクション付き）。
