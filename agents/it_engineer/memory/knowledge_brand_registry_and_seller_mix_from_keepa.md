# ブランド登録の有無と出品者の構成を Keepa で安く取る（2026-09-14 / T-20260914-006 T-3）

「ブランド未登録で、メーカー本人は売らず、第三者が売っている」ASIN（P2）を抜く作業。見積り 4,900 token → 実績は約3,350（下の順番で削れた）。

## 手順（再利用可）

1. **ブランドストアは既存の product raw を先に見る。** `brandStoreName` は `offers` なしの普通の product（1 token）に入っている。T-1 の raw（同じ日の朝）に全件入っていたので **0 token** だった。取り直す前に手元の raw を grep する。
2. **出品者の構成は `buybox=1`（計3 token/ASIN）＋`history=0` で `stats.buyBoxStats`。** 90日間にカートを取った出品者ごとに `percentageWon`・`isFBA`・`lastSeen`。全オファー（`offers=`・約7 token）は要らない。
3. **`buybox=1` はストアなしの ASIN だけに当てる。** ストアありは P1 と決まるので出品者を見る必要がない（1,394→829で約1,700 token 削減）。
4. **出品者名は獲得率10%以上だけ `/seller`（1 token/ID・100ID/リクエスト）。** 400 ASIN で distinct 452 ID（全保持者なら 840）。閾値で約半分になる。
5. 判定・集計は raw からの 0 token スクリプトに分ける（`t3_classify.py`）。取得スクリプトは1リクエスト1ファイルで保存し、保存済みを飛ばす＝再実行で続きから。

## 精度

- **S-1 のサトルの目視（商品ページの byline）と、同じ ASIN の `brandStoreName` は 25/25 一致。** 目視のブランドストア確認は Keepa で置き換えてよい。
- `brandStoreName` の中身はブランド名とは限らない（「〇〇のストアを表示」というリンク文言、別ブランド名）。**空か空でないかだけで使う。**
- 照合は「ASIN 単位」で。社名やブランド名で寄せると表記揺れで取りこぼす（S-1 の GORIX は名前一致で 24 中 1 件しか引けなかった）。サトルの `byline.json` に社ごとの見た ASIN が残っていた。

## 罠

- 試験呼び出しの保存名が本番の glob（`*bb*`）に掛からず、試験の5件を本番でもう一度取った（15 token の二重払い）。**試験の保存名は本番と同じ命名規則にする**か、試験では保存しない。
- Amazon.co.jp の sellerId は `AN1VRQENFRJN5`。`buyBoxStats` に出れば本体がカートを取った履歴あり。

関連: [[knowledge_keepa_dependency_inventory_before_cancel]] [[knowledge_demand_first_pool_is_brand_bound]] [[knowledge_keepa_count_new_is_not_seller_count]]
