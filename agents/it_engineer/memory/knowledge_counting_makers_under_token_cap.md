# 条件に合う「メーカー数」を token 上限の中で数える（2026-09-16 / T-20260914-006 S-A）

型A の3基準（本体なし・FBA 出品者2以上・ランク5万以内）を満たす中小メーカー数を、1回 5,000 token 以内で出した手順。
**「条件に合う社は何社か」と聞かれたら、この型で出せる。**

## 事実（domain=5・2026-09-16 実測）

- **`offerCountFBA_gte` は Finder で有効**（`product-finder.html` の "Offer counts & Buy Box statistics"。`totalOfferCount`・`offerCountFBM`・`buyBoxEligibleOfferCountsNewFBA` も同じ節）。`_gte=100000` で0件＝効いている。
- **`offerCountFBA` は Finder 側ではほぼ全件に値がある**（`_gte=0` が 493万中 493万）。一方、`offers` なしの product では `stats.offerCountFBA=-2`（未取得）になる。**product の -2 を見て「Finder でも使えない」と思わないこと。**
- `brand` 条件（String[]）も有効。実在ブランド5件・架空0件。1ブランド 11 token。
- ランク5万以内でも ASIN は数百万になる（本体なし・メディア除外で546万）。**バリエーションの子が親のランクを共有するため。** 単品に絞ると上限 ルート数×5万。
- 3基準＋メディア/規制3除外＝7.69万（近似）→ 一覧の実数 75,574。ルート15本を perPage=10,000 で取り、1万超はランク帯で2分割（服・家電で発生）＝**1,274 token**。

## 手順

1. 件数プローブ（11 token/回）で漏斗の桁を出す。新しいフィールドは「`_gte=巨大値` で0件」を必ず確かめる
2. ASIN 一覧は Finder で全件（10＋件数/100）。ブランドは product でしか取れない（1 token/件）ので、**全件読むか標本かを件数で決める**（7.5万件＝約63時間・上限超え → 標本）
3. 標本はルート比例・乱数固定。手元の raw（全リポの `*.json.gz` を索引化した `sa_cache.py`）と重なる分は0 token。今回は2,499中47件しか重ならなかった（過去の抽出は価格帯・公表販売数で絞っていて母集団が違う）
4. 区分は T-1 の関数をそのまま import（`t1_classify.row`・`t1_bigbrands.known_big`・gBiz キャッシュ）。除外の手順を写し直さない
5. 社数は ASIN に比例しない。3通りで幅を出す:
   - Chao1（標本内の1回/2回の社から）＝下側。標本率3%で1回だけの社が多いと、ほとんど伸びない＝床として読む
   - 家族HT＝Σ(1/一覧内の兄弟数)×N/n。product の `variations` から0 token。社数はこれ以下
   - **社HT＝Σ(1/k)×N/n（k＝その社のブランドで Finder を引いた一覧内 ASIN 数）。不偏推定。** 必要な区分のブランドだけ引く（11 token/ブランド）

## 罠

- `a && nohup b &` は a ごと背景に回る。a（索引の再構築・約1分）が終わるまで b のログが出ず、「起動していない」と誤読しかけた。**前処理と本体は別の行で起動する**
- 標本の取得順はルート ID 順。途中で集計すると1カテゴリに偏った数字が出る（途中は家電ばかり）。**途中の数字は報告に使わない**
- 希薄化曲線を9倍（2の9乗）まで外挿すると、1.7倍/倍の小さな差が数十倍に効く。単独の推定には使わない

関連: [[knowledge_demand_first_pool_is_brand_bound]] [[knowledge_keepa_product_finder_fields]] [[knowledge_brand_registry_and_seller_mix_from_keepa]]
