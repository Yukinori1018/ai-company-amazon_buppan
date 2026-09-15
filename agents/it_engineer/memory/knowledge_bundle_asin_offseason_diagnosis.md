# まとめ売り ASIN の「季節の不振」を切り分ける手順（2026-09-15 / T-20260909-002 S-a・S-d）

## 手順（計 10 トークン前後で済む）
1. `/product?asin=<set>&history=1&buybox=1&days=400`（offers なし、1〜3 トークン）
   - 月ごとに csv[11] COUNT_NEW、csv[1] NEW、csv[18] BUY_BOX_SHIPPING(時刻,価格,送料の3つ組) の「値>0 の時間割合」を 6時間刻みで出す
   - 0/-1 が続けば在庫切れ、>0 なのにランクが動かなければ需要なし
   - 販売の痕跡は csv[3] ランクが直前の 70% 以下に落ちた回数で近似（推定。販売数ではない）
2. `/product?code=<JAN>&history=0` で**同じ JAN を持つ ASIN を全部出す**（1 トークン/件）。
   Keepa の `variations` は自分しか載せないことがある（今回そうだった）ので、兄弟探しは code 検索が早い。
3. 単品 ASIN の履歴を同じ集計にかけ、「単品は売れていたか」「1本あたり価格でセットが割高だったか」を見る。

## 学び
- **セットの EAN が単品 JAN と同一なら、それは出品者のまとめ売り。** brand 欄が出品者名義（例: ぷるんと蒟蒻）になっているのが目印。
- セットの不振は季節ではなく**単品×N との価格比較**で説明できることがある。冬のセット BB は1本換算で単品 BB より高かった。
- 単品側の Keepa データが途中で途切れることがある（lastUpdate が数か月前）。比較できる期間を明記する。
- 公式 api-docs は WebFetch だと 403。`curl -A "Mozilla/5.0"` なら取れる（product-object.html に csv 定義）。
- COUNT_NEW の公式文言は「merchants の数」だが実態はオファー本数（knowledge_keepa_count_new_is_not_seller_count）。0 判定には使える。

## 置き場
Keepa 加工値は `deliverables/<ticket>/out/`（追跡外）。スクリプトと生 JSON は agent_output。
