# Keepa Product Finder — 有効フィールドの実測と落とし穴（T-20260817-005 / 2026-08-21）

メーカー仕入れ v1.3 の実走（`workspace/output/deliverables/T-20260817-005/scan_v13.py`）で
Keepa Product Finder（`GET https://api.keepa.com/query`）を実測検証した結果。

## 最大の落とし穴：**未知のフィールドはエラーにならず、黙って無視される**

`{"bogusField_gte":1}` を投げても HTTP 200・`error:null` で返り、`totalResults` は
無条件検索と同じ（2.75億件）。**綴りを1文字間違えるとフィルタが効かないまま
「条件どおり抽出できた」と誤認する。** ドキュメントを読んで安心してはいけない。

**検証手順（確立した型）**: ベースライン selection の `totalResults` を取り、
フィールドを1つずつ足して `totalResults` が動くかを見る。動けば有効・同じなら無視されている。
1プローブ11トークン。数十トークンで数千トークンの無駄打ちを防げる。

## 有効を実測確認したフィールド（domain=5 / 2026-08-21）

| フィールド | 用途 | baseline 1,261,747件 → |
|---|---|---|
| `salesRankDrops30_gte` | **月間ドロップ数**（＝v1.3 の抽出軸） | 162,785 |
| `current_COUNT_REVIEWS_gte` / `_lte` | レビュー数 | 654,387 |
| `categories_exclude`（ルートID配列） | 規制カテゴリ除外 | 1,093,949 |
| `trackingSince_lte`（Keepa分） | 追跡期間◯日以上 | 1,113,507 |
| `variationCount_gte` / `_lte` | バリエーション数 | 106,655 |
| `isAdultProduct`（bool） | アダルト除外 | 1,261,505 |
| `packageWeight_lte`（g） | 重量 | 1,174,906 |
| `sort: [["salesRankDrops30","desc"]]` | 回転の良い順に取れる | — |

既知（過去メモ）: `current_AMAZON_gte/_lte=-1`（本体不在）、`current_COUNT_NEW_gte/_lte`、
`current_SALES_gte/_lte`、`current_NEW_gte/_lte`（**domain=5 は円そのまま。×100 ではない**）。

Keepa 分 = `int(unixtime/60) - 21564000`。

## トークン経済の重要な発見：**perPage は 1000 まで通る**

過去メモには「perPage は最低50」とだけあったが、**上限も検証すべきだった**。

| perPage | 消費トークン | 1000件あたり |
|---|---|---|
| 50 | 11 | 220 |
| **1000** | **20** | **20** |

**Finder の課金は「10 + 件数/100」**。perPage=50 で20ページ回すのは
perPage=1000 の1発に対して **11倍の無駄**。ページングする前に perPage を上げる。

`product` は 1トークン/件。**`stats=365` に追加コストは無い**（stats=30 と同じ1件1トークン）。
過去1年最安値が欲しいなら遠慮なく `stats=365` を投げてよい。

## product レスポンスの読み方（実測）

- `stats.min[i]` は `[keepa時刻, 値]` または `null`。`stats=N` の **N日間**の最小値。
  **index 1 = NEW（新品最安）** が「過去1年最安売価」として最も素直で保守的。
  index 18（BUY_BOX）は `null` になる商品が多く、当てにできない。
- `stats.buyBoxPrice` は **-2**（＝カート無し/不適格）を返すことがある。`-1` だけを
  欠損扱いにすると -2 が価格として紛れ込む。`>= 0` で弾くこと。
- `stats.salesRankDrops30 / 90 / 180 / 365` はここから直読み。
- `monthlySold`（Amazon実データ「◯◯+個購入」）は**月50個以上の商品にしか出ない**。
  実測: 300件中233件で取得できた（＝ドロップ数上位を狙うと出やすい）。
- `brand` / `manufacturer` は `_product_to_amazon()` が捨てるので **raw dict から直読み**（既知）。

## 判定ロジック側で踏んだ落とし穴

- **`current_COUNT_NEW_lte=6` で絞っても、詳細取得すると出品者7の商品が混じる。**
  Finder のインデックスと product の current は更新タイミングが違う。**後処理で必ず再判定**する。
- **v1.3 の「レビュー5〜300＝あまり有名でない」は発売直後の大手SKUを素通しする。**
  実際に Anker / UGREEN / BANDAI / タカラトミー / BURTLE が残った。
  除外は社長判断の領域なので `規模フラグ` 列（大手/海外疑い・中小候補）を立てるに留めた。
- FBA 標準サイズ（45×35×20cm・9kg）判定は `packageLength/Width/Height`（**mm**）と
  `packageWeight`（**g**）から。欠落商品が一定数あるので「不明」区分を用意し、
  **除外せず列に出して人に渡す**（除外すると母数が大きく削れる）。

## 再利用のかたち

`scan_v13.py` は raw レスポンスを `raw/*.json.gz` に保存し、`--from-raw` で
**トークン0**で閾値を変えて再集計できる。閾値をいじる作業でトークンを二度使わない。
条件変更のたびに Keepa を叩き直す設計にしてはいけない。
