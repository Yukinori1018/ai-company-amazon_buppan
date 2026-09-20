# `monthlySold` は ASIN 単位、ランクは family 共有（粒度が違う）

T-20260920-003 / 2026-09-20。社長の「ランクが良いのは兄弟と連動しているのでは」という疑いを
サンリオ ミニマスコットホルダーの兄弟20 ASIN で検証した結果。**社長の疑いはランクについて正しかった。**

## 結論

| フィールド | 粒度 | 一次情報の文言 |
|---|---|---|
| `monthlySold` | **ASIN 単位（実数）** | **"The value is variation specific."** ／ "It is not an estimate." ／ "This field represents the bought past month metric found on Amazon search result pages." ／ "Most ASINs do not have this value set." |
| `salesRanks` / `salesRankReference` | **family 共有** | "Contains subcategory rank histories." — **variation 固有の記述が無い** |

出典（Keepa 自身が保守する product object の構造定義。api-docs の product-object ページは 404）:
`https://github.com/keepacom/api_backend/blob/master/src/main/java/com/keepa/api/backend/structs/Product.java`

## 実データでの裏取り（これが一番強い）

同じ親 B0F795L9SM の子20件＋1件を並べたら：

- **ランクは 1,310 か 1,292 の2値しかなく、末端カテゴリは21件全員が「2位」。** 親 ASIN も同値。
  親から外れた ASIN だけ本当のランク（94,345位）が出る＝共有の仕組みが見えた。
- **`monthlySold` は 200/200/100/100/50/50 と割れた**（値が入るのは6/21件）。合算なら全員同じになる。
- **決定的**: キティとマイメロディは**ランクが完全に同一**（2025-12 に両方108位、現在両方1,010位）なのに
  `monthlySold` の推移は別物（キティは2026-04に500がピーク／マイメロディは2025-12に1,000がピーク）。

## 運用に落とすと

1. **ランクを仕入れ判定の門に使わない。** バリエーションがある商品では単品の売れ行きを表さない。
   `salesRankDrops` も同じ（family 共有のランクが動いたのを何回見たかの回数）。
2. **`monthlySold` の「なし」は「売れていない」ではなく「月50個未満」。** Amazon が50個未満を表示しないため。
   `lastSoldUpdate` が `lastUpdate` より古い＝以前は表示されていたのに消えた＝**落ちた**、と読む。
3. **`availabilityAmazon` は `offers` なしで取れる（1トークン/ASIN）。** Amazon 本体の有無は
   最初の門にするのが最も安い。今回20件すべてで、本体がいる ASIN は価格が1円単位で固定されていた。
4. バリエーション family には **同じ品番の重複 ASIN** と **本体のまとめ買いセット ASIN**（単価×個数で価格が一致・EAN なし）が
   混ざる。品番だけで名寄せすると別物を掴む。

## トークン実測

19 ASIN を `offers=20&rating=1&buybox=1&stats=90&history=1` で1回 → **`tokensConsumed` = 114**（6.0/ASIN）。
3件のときは14（4.7/ASIN）。**オファー本数が多い ASIN ほど高い**ので、`offers` 付きの見積りは
「7/ASIN」を上限として置くのが安全。
