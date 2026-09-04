# NETSEA `/tariffs` — 送料無料ラインの唯一の一次情報（2026-09-04 / T-20260904-004）

小さな予算（社長の初回は総額5万円）では、**送料が利益より大きい**ことがあります。
卸は「◯円以上で送料無料」が標準なので、5社に分けて買うと送料が5回掛かります。
どこまで積めば送料が変わるかは **商品側の `ship_fee` には出てきません**。
`GET /tariffs` を見るしかありません。

## 公式スキーマ（実取得で確認）

取得先: `https://api.netsea.jp/docs/buyer/schemas/tariffs.json`
（本体 `openapi.json` の `paths` は `{"$ref": "paths/index.json"}` で、
そこから `paths/tariffs.json` → `schemas/tariffs.json` と辿る。
`openapi.json` は生の制御文字を含むので `json.loads(..., strict=False)` が要る）

| フィールド | 意味 |
|---|---|
| `supplier_id` | サプライヤーID |
| `apply_type` | `higher` / `lower`。送料の違う商品を混ぜたときどちらを適用するか |
| `gradual_flag` | 段階設定を使うか（bool） |
| `gradual_border_price` | 段階の切り替え金額。使わない場合は `null` |
| `prices[]` | 都道府県別 `{prefecture, price1, price2}` |
| `price1` | 切り替え金額**未満**の送料（段階を使わない場合はこれが常の送料） |
| `price2` | 切り替え金額**以上**の送料（段階を使わない場合は `null`） |

パラメータは `supplier_id` のみ（**必須**）。カンマ区切りで**最大10件**。

## ⚠️ 一番大事なところ

> **`gradual_border_price` は「送料無料ライン」ではありません。**
> **`price2 == 0` のときだけ**「その金額以上で送料無料」です。
> `price2` が正の値なら「その金額以上で送料が*安くなる*」であって、無料ではありません。

`gradual_border_price` を送料無料ラインとして扱うと、**届いていない社を「届いた」と表示**します。
利益率5%の商材で送料770円を見落とせば、その SKU は赤字です。
これは `knowledge_verify_field_semantics_not_names`（COUNT_NEW 事故）と同じ型の罠で、
**名前が意味を語っているように見えるフィールド**です。判定は必ず `price2` を見ること。

実例（2026-09-04 実データ）: ある社は東京都宛で
`gradual_flag=true / gradual_border_price=20000 / price1=770 / price2=0`
＝「20,000円以上で 770円 → 0円」＝**2万円が本物の送料無料ライン**。

## 実装

`adapters/netsea.py` の `list_tariffs(supplier_ids) -> {supplier_id: tariff}`。
取れなかった社は**戻り値に入れません**（呼び出し側が空欄にできるように）。

読み手側（`T-20260904-004/budget_filter.py` の `read_tariff()`）では、
取れない理由を3つに割って書きます。**まとめて「不明」にしない**:

- 「この社に設定が無い」（`/tariffs` が返さなかった）
- 「対象都道府県外」（`prices[]` にその県が無い）
- 「段階設定なし」（積んでも送料は変わらない ＝ 集約の意味が薄い社）

## 届け先の扱い

送料は**都道府県別**です。本リポは PUBLIC なので、**社長の住所は使いません**。
代表値として東京都で桁を出し、「実額は発注時に届け先で確定」と明記します。
