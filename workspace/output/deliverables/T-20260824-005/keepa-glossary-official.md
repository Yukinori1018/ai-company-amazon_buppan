# Keepa 用語集（正式版）

**Keepa の画面・数値に出てくる語を、公式の定義で引くための辞書です。**

- **出典：Keepa 公式 API ドキュメント（`https://keepa.com/api-docs/` 全30ページ）／ Keepa 公式FAQ。全件の最終確認日 2026-08-24。**
- Keepa は仕様変更が多く、2026年だけでも 2/23・3月・4/20・7/28・8/6・8/9・8/18 に変更が入っています。**最終確認日から3ヶ月を過ぎたら、出典に当たり直してください。**
- 第1版 2026-08-24（T-20260824-005）

---

## この用語集の使い方

1. **語が決まっているなら、巻末の索引から。**〔索引A〕日本語表記から引く／〔索引B〕英語・APIフィールド名から引く。HTML版は上部の検索窓に打ち込めば絞り込めます。
2. **何を疑うべきか分からないなら、§1「特に注意が必要な語」だけ読む。**ここに挙げた10件は、取り違えると判断が逆になります。
3. **ここに載っていない語は「不明」として扱い、判断に使わないでください。**公式に定義が見つからなかった語は §4 にまとめてあります。

> **読み方の約束**
> ・「意味」列は公式原文の訳です。原文にない補足は〔 〕で囲んでいます。
> ・**APIフィールド名**＝Keepa が公式ドキュメントで使っている正式名称。〔API＝プログラムから Keepa のデータを直接取るための窓口。画面表示ではなく、こちらが定義の本体です〕
> ・**「用語」列**＝Keepa の日本語画面に出る表記。画面に対応する表記が無いものは概念名を、それも無いものは「—」を置いています。Keepa は UI の用語集を公開していないため、**実画面で確認できたものと、公式定義から対応を推定したものが混在します。**根拠にするのは APIフィールド名と「意味」列にしてください。

---

## 1. ⚠ 特に注意が必要な語

**この10件は、名前から素直に読むと意味が違います。**

| 語 | よくある読み違い | 公式の定義 | 数字の向き・見分け方 |
|---|---|---|---|
| **BUY BOX の平均売上数**<br>`avgBuyBoxCompetitors` | 売れた個数 | **売上ではありません。**この出品者が扱う商品について、**Buy Box を争っている出品者数の平均**（この出品者自身を含む）。日本語UIの表記は誤訳です | **大きいほど競合が多い＝不利** |
| **新品アイテム数**<br>`COUNT_NEW`（csv 11） | 出品者の数 | **新品オファーの本数**です。1社が FBA と FBM に1本ずつ出せば **2** になります | 大きいほど相乗りが多い。ただし**出品者数の代用にはできない**（→ §3.3「出品者数（実数）」） |
| `stats.min` / `stats.max` | 指定した期間の最安値／最高値 | **記録開始以来（全期間）**の最安値／最高値。`stats=365` を指定しても期間は効きません。期間内の最安・最高は `stats.minInInterval` / `stats.maxInInterval` | — |
| **新品**<br>`NEW`（csv 1） | 出品者の新品最安値（Amazon本体は別枠） | **Amazon 本体もマーケットプレイスの一部として含みます。**さらに **2026-02-23 を境に定義が変わり**、前は「出品価格」、以降は「着地価格（出品価格＋送料）」です | — |
| **先月の購入／月間販売数**<br>`monthlySold` | 予測値、または正確な販売個数 | Amazon の検索結果に出る "bought past month" の値そのもの。**推定値ではありません**（公式明記）。ただし Amazon が "10+" "100+" のような**区切られた範囲でしか提供しない**ため、`1000` は「**少なくとも** 1000回」の意味 | 大きいほど売れている（ただし**下限値**）。**大半のASINは値を持ちません**（値が無い＝売れていない、ではない） |
| **↘ N drops**<br>`salesRankDrops30/90/180/365` | 売れた個数 | 期間内に売れ筋ランキングが**下落（高い値から低い値へ変化）した回数**。公式の記述は「**販売を示すものとみなされる**」まで | 多いほど売れている傾向。**個数と等しいとは公式は書いていません** |
| **`offers` を付けないと値が来ない語**（一群） | 「古い値が返る」 | **値そのものが存在しません**（`-1` または未設定）。対象は csv の 7・9・10・16・17・18・19〜27・32・33 と、`stats` の Buy Box 系・オファー数系 | — |
| **FBAリストが見つかりました**<br>`hasFBA` | FBA出品の有無 | その出品者が現在FBA出品を持っているか。公式が「**通常は正しいが、FBA出品があっても false になりうる**」と明記 | **「はい」は信じてよい。「いいえ」は『無い』ことの証明になりません** |
| **%獲得**<br>`buyBoxStats[].percentageWon` | カートを取っている割合 | その出品者が Buy Box を獲得していた**時間の割合**。**非プライム客に対して**の数値です | 大きいほどその出品者がカートを押さえている |
| `availabilityAmazon` | Amazon 本体の有無は、価格が -1 かどうかで分かる | Amazon 本体オファーの在庫状況。**-1＝Amazon のオファーが存在しない**／0 在庫あり／1 予約／2 不明／3 入荷待ち／4 出荷遅延 | **Amazon 本体の不在を判定する専用フィールドはこれ。**価格履歴の `AMAZON`（csv 0）が -1 なのは「その時点で Amazon の価格データが無い」という意味で、**普段売っている商品が在庫切れのときも -1 になります** |

---

## 2. 値の共通ルール

**どの語にも共通してかかる約束事です。**個別の定義を読む前に、ここを先に押さえてください。

| # | ルール | 出典 |
|---|---|---|
| 1 | **価格はすべて、そのマーケットプレイスの通貨の最小単位の整数。**日本（co.jp）なら「円」そのもの（小数なし）、米国ならセント | product-object |
| 2 | **時刻はすべて「Keepa Time 分」。**Unix秒 = (keepaTime + 21564000) × 60 | product-object |
| 3 | **`-1` は「データなし／その期間にオファーが存在しなかった」。0円ではありません。**`-2` は「判定できなかった」 | product-object / offer-object |
| 4 | **履歴（csv）は値が変わったときだけ追記されます。**更新のたびに点が増えるわけではありません | product-object |
| 5 | **csv 配列の長さを固定と仮定しないこと。**Keepa は予告なく型を追加します（公式明記。実際 2026年に 34・35 が追加された） | product-object |
| 6 | **`productType` を最初に評価すること**（公式が「Must always be evaluated first」と明記）。0 STANDARD 以外は、取得できるデータが限られます | product-object |
| 7 | **グラフは3種類あり、1枚の画像に混ぜられません。**①価格履歴 ②カテゴリ別ランキング＆月間販売数 ③オファー数と評価。それぞれ軸と値の空間が違うため | graph-image |
| 8 | **画面のデータ鮮度は2段階。**誰かがその商品をトラッキングしていれば**1時間に1回**、していなければ**1日1回**更新（公式FAQ）。**API 経由は別ルール**で、最後の更新が `update` に指定した時間（既定1時間）より古ければ、配信前に自動で更新されます | FAQ / product |
| 9 | **`offers` パラメータを付けない限り、一切更新されないデータ群があります**（Buy Box・評価・評価件数・FBA/FBM別価格など）。→ §1、および各表の「注意」列 | product-object |

---

## 3. 用語定義

### 3.1 価格と価格履歴（csv 履歴配列）

`csv` は2次元配列です。第1次元が**価格タイプの番号**（下表）、第2次元が `[Keepa Time 分, 値, …]`。型名に `_SHIPPING` が付くものだけ `[Keepa Time 分, 価格, 送料, …]` の3つ組になります。

▸ この表の「用語」列は、Keepa 日本語画面のグラフ凡例に対応すると**推定**される表記です（Keepa は UI 用語集を公開していません）。根拠にするのは APIフィールド名と「意味」列にしてください。

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| Amazon | `AMAZON`（csv 0） | Amazon 本体が売っているオファーの価格履歴 | — | product-object |
| 新品 | `NEW`（csv 1） | マーケットプレイス新品の最安価格履歴。**Amazon 本体もマーケットプレイスの一部として含む**（Amazon が全体の最安なら `NEW` = `AMAZON`） | ⚠ **2026-02-23 を境に定義が変わる**（前＝最安の出品価格／以降＝最安の着地価格＝出品価格＋送料） | product-object |
| 中古 | `USED`（csv 2） | マーケットプレイス中古の最安価格履歴 | ⚠ 2026-02-23 の定義変更の対象 | product-object |
| 売れ筋ランキング | `SALES`（csv 3） | 売れ筋ランキングの履歴 | すべての商品にランクがあるわけではない。バリエーションの子ASINは通常、個別のランクを持たない | product-object |
| 参考価格 | `LISTPRICE`（csv 4） | 定価（MSRP）の履歴 | — | product-object |
| コレクター商品 | `COLLECTIBLE`（csv 5） | コレクター品の価格履歴 | ⚠ 2026-02-23 の定義変更の対象 | product-object |
| 再生品 | `REFURBISHED`（csv 6） | 再生品の価格履歴 | ⚠ 2026-02-23 の定義変更の対象 | product-object |
| 新品 第三者（自己発送） | `NEW_FBM_SHIPPING`（csv 7） | **Amazon 本体を除く**第三者の新品・自己発送（FBM）価格履歴。**送料込み** | ⚠ `offers` 必須 | product-object |
| タイムセール | `LIGHTNING_DEAL`（csv 8） | タイムセール価格の履歴 | 進行中のセールでは、履歴の最後が「**未来の日付＋価格 -1**」になる。現在価格は `stats.current` から取る | product-object |
| Amazon倉庫 | `WAREHOUSE`（csv 9） | Amazon Warehouse（Amazon の中古アウトレット）の価格履歴 | ⚠ `offers` 必須 | product-object |
| 新品 第三者（FBA） | `NEW_FBA`（csv 10） | **Amazon 本体と Warehouse を除く**第三者の新品FBA最安値の履歴 | ⚠ `offers` 必須 | product-object |
| 新品アイテム数 | `COUNT_NEW`（csv 11） | 新品オファー数の履歴 | ⚠ **出品者数ではない**（→ §1、§3.3） | product-object |
| 中古アイテム数 | `COUNT_USED`（csv 12） | 中古オファー数の履歴 | — | product-object |
| 再生品アイテム数 | `COUNT_REFURBISHED`（csv 13） | 再生品オファー数の履歴 | — | product-object |
| コレクター商品アイテム数 | `COUNT_COLLECTIBLE`（csv 14） | コレクター品オファー数の履歴 | — | product-object |
| — | `EXTRA_INFO_UPDATES`（csv 15） | `offers` 系データを更新した時刻の履歴。値の**絶対値＝その時に取得したオファー数**。値が**正なら全オファーを取得できた**、**負なら取得しきれなかった** | `offers` 系の値が「いつ時点の情報か」を知る手段。公式が「更新頻度が低いので、いつ更新したかを知ることが重要」と明記 | product-object |
| 評価 | `RATING`（csv 16） | 商品評価の履歴。**0〜50の整数**（45 = ★4.5） | ⚠ `offers` 必須 | product-object |
| 評価件数 | `COUNT_REVIEWS`（csv 17） | 商品の**評価件数**の履歴 | ⚠ `offers` 必須。**型名は REVIEWS だが、公式の定義文は rating count（評価件数）** | product-object |
| Buy Box | `BUY_BOX_SHIPPING`（csv 18） | 新品 Buy Box 価格の履歴（**送料込み**）。Buy Box に適格なオファーが無い場合、または Buy Box が中古オファーの場合は **-1** | ⚠ `offers` 必須 | product-object |
| 中古（ほぼ新品／非常に良い／良い／可） | `USED_NEW_SHIPPING` / `USED_VERY_GOOD_SHIPPING` / `USED_GOOD_SHIPPING` / `USED_ACCEPTABLE_SHIPPING`（csv 19〜22） | 中古サブ状態別の価格履歴（送料込み） | ⚠ `offers` 必須 | product-object |
| コレクター商品（4状態） | `COLLECTIBLE_*_SHIPPING`（csv 23〜26） | コレクター品サブ状態別の価格履歴（送料込み） | ⚠ `offers` 必須 | product-object |
| 再生品（送料込み） | `REFURBISHED_SHIPPING`（csv 27） | 再生品の価格履歴（送料込み） | ⚠ `offers` 必須 | product-object |
| eBay 新品 | `EBAY_NEW_SHIPPING`（csv 28） | 対応する eBay ロケールでの新品最安値（送料込み） | ⚠ 公式が「**eBay の出品は情報や商品コードの誤りが多い。価格情報の正確さを当てにするな**」と明記 | product-object |
| eBay 中古 | `EBAY_USED_SHIPPING`（csv 29） | 同上（中古） | ⚠ 同上 | product-object |
| 下取り | `TRADE_IN`（csv 30） | 下取り価格の履歴 | 下取りは全ロケールで提供されているわけではない | product-object |
| — | `RENT`（csv 31） | **廃止済み。値が入ることはありません。**以降の番号の位置を保つためだけに残されています（2026-02-23 にレンタル関連を削除） | — | product-object / changelog |
| Buy Box 中古 | `BUY_BOX_USED_SHIPPING`（csv 32） | 中古 Buy Box 価格の履歴（送料込み・サブ状態は問わない）。適格オファーが無ければ **-1** | ⚠ `offers` 必須 | product-object |
| プライム会員限定 | `PRIME_EXCL`（csv 33） | プライム会員限定の新品最安値の履歴 | ⚠ `offers` 必須 | product-object |
| — | `COUNT_NEW_FBA`（csv 34） | 新品**FBA**オファー数の履歴（**Amazon 本体のオファーを含む**） | 2026年に追加された新しい型（product-object は「2026年3月」、changelog は 2026-02-23 の項に記載） | product-object |
| — | `COUNT_NEW_FBM`（csv 35） | 新品**FBM**オファー数の履歴 | 同上 | product-object |
| — | `offers[].offerCSV` | 個別オファー1件の価格・送料の履歴。`[Keepa Time 分, 価格, 送料, …]` | 送料無料は `0`、**発送不可・送料不明は `-1`**、価格や送料を判定できなかった場合は `-2` | offer-object |

**2026-02-23 の価格定義変更（公式原文の要旨）**
`NEW` / `USED` / `COLLECTIBLE` / `REFURBISHED` の時系列について、**2026年2月23日より前の記録は「最安の出品価格（listing price）」**、**2026年2月23日以降の記録は「最安の着地価格（landing price ＝ 出品価格＋送料）」**を表します。同じ列の中で意味が変わるため、この日をまたぐ期間の最安値・平均値は**定義の異なる値が混ざった数字**になります。（product-object / changelog）

---

### 3.2 売れ行き（ランキング・販売数）

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| ↘ N drops | `salesRankDrops30` / `salesRankDrops90` / `salesRankDrops180` / `salesRankDrops365` | 直近30/90/180/365日に、売れ筋ランキングが**下落（高い値から低い値への変化）した回数**。公式の記述は「**販売を示すものとみなされる**（considered to indicate sales）」まで | ⚠ **公式は「販売個数と等しい」とは書いていない。**更新の間隔内に複数個売れても1回と数えられうる。`stats` で指定した期間には影響されない固定窓 | statistics-object |
| 先月の購入／月間販売数 | `monthlySold` | 過去1か月にこの商品が購入された回数。**Amazon の検索結果ページに出る "bought past month" の値そのもので、推定値ではない**（公式明記） | ⚠ Amazon が "10+" "100+" のような**区切られた範囲でしか提供しない**ため正確な数字ではない。`1000` は「**少なくとも** 1000回」。**大半のASINは値を持たない。**値は**バリエーション単位** | product-object |
| — | `monthlySoldHistory` | `monthlySold` の履歴。形式 `[keepaTime, monthlySold, …]` | 値が無ければ未設定 | product-object |
| — | `lastSoldUpdate` | `monthlySold` を最後に更新した時刻（Keepa Time 分） | `monthlySold` に値が無ければ未設定 | product-object |
| カテゴリ別ランキング | `salesRanks` | キーがカテゴリノードID、値がそのカテゴリでのランク履歴 | — | product-object |
| — | `salesRankReference` | **メインの**売れ筋ランキングが属するカテゴリのノードID。**-1＝不明／-2＝Launchpad 掲載** | どのカテゴリ基準のランクを見ているかを、推測ではなくフィールドとして取得できる | product-object |
| — | `salesRankReferenceHistory` | 上記の履歴。過去のランクがどのカテゴリ基準だったかを対応づけられる | — | product-object |
| — | `salesRankDisplayGroup` | メインの売れ筋ランキングが**どの分類に基づくか**（例：`apparel_display_on_website`） | — | product-object |
| — | `launchpad` | Launchpad カテゴリに掲載されているか | 掲載されている場合、`salesRankReference` は取得できない | product-object |

▸ BSR（売れ筋ランキング）そのものの性質——相対順位である／販売が無くても動く／時間とともに減衰する——は **Amazon 側の仕様であり、Keepa 公式ドキュメントには記述がありません。**Keepa の出典として引かないでください。

---

### 3.3 出品数・出品者数

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| 新品アイテム数 | `COUNT_NEW`（csv 11） | 新品オファー数の履歴。現在値は `stats.current[11]` | ⚠ **出品者数ではありません。**公式の説明文は "count of marketplace merchants selling the product as new"（新品で売っている出品者の数）と書いていますが、**フィールド名は offer count** であり、実データでも**同一出品者が FBA と FBM に1本ずつ出せば 2** になります。出品者数が必要なら下の「出品者数（実数）」の手順を使ってください | product-object |
| **出品者数（実数）** | **該当フィールドなし** | **Keepa に「出品者数」というフィールドは存在しません。**公式が示す手順は、`offers` を取得 → `liveOffersOrder` で現存オファーに絞る → `condition == 1`（新品）→ **`sellerId` の重複を除いて数える** | ⚠ オファー数（`COUNT_NEW` 等）では代用できません | product-object / offer-object |
| — | `totalOfferCount` | この商品の、**全状態を合わせた**オファー総数 | 状態別の内訳は `current[11]`（新品）・`current[12]`（中古）で取る | statistics-object |
| — | `offerCountFBA` / `offerCountFBM` | **取得できた**ライブ新品 FBA / FBM オファーの数。不明なら **-2** | ⚠ `offers` 必須。「取得できた範囲での」数（`offers` で要求した件数が上限） | statistics-object |
| — | `retrievedOfferCount` | このリクエストで取得したオファー数 | ⚠ `offers` 必須 | statistics-object |
| — | `sellerIdsLowestFBA` / `sellerIdsLowestFBM` | **最安の**ライブ新品 FBA / FBM オファーの出品者ID。同価格が複数あれば複数入る | ⚠ `offers` 必須 | statistics-object |
| 販売者 | `offers[].sellerId` | 個別オファーの出品者ID | **実際の出品者数は、この値の重複を除いた個数**で数える | offer-object |
| — | `liveOffersOrder` | **いま Amazon のオファー一覧に載っている順**に並んだ、`offers` 配列のインデックス列 | `offers` 配列には過去のオファーも混ざるため、現存オファーの判定はこれか `lastSeen` で行う（公式推奨）。⚠ **同一出品者・同一状態・同一発送形態の重複オファーがあると同じインデックスが複数回入る**ため、要素数を数えるとオファー数を多く見積もる | product-object |
| — | `offers[].lastSeen` | このオファーを最後に確認した時刻（Keepa Time 分） | 現存オファーだけ扱いたいならこの値で検証すること、と公式が明記 | offer-object |
| — | `offersSuccessful` | `offers` 使用時に、最新のオファー情報を取得できたか | ⚠ **マーケットプレイスのオファーが1件も無い商品でも `true`**（取得成功として扱われる）。`offers` 依存フィールドを使う前に必ず確認せよ、と公式が明記 | product-object |
| — | `offerDuplicates` | 同一出品者・同一状態・同一発送形態で、**最安でないため `offers` 一覧から除外された**重複オファーの価格・送料・コンディション説明 | — | offer-object |
| — | `offers[].isFBA` | そのオファーが FBA（Amazon 発送）か | — | offer-object |
| — | `offers[].isPrime` | そのオファーがプライム配送で買えるか | ⚠ 公式が「**Keepa は SFP（出品者出荷プライム）を確実に識別できない**」と明記 | offer-object |
| — | `offers[].isAmazon` | 出品者が Amazon（例：Amazon.com）か | ⚠ **Amazon Warehouse Deals や、Amazon が別名で運用しているアカウントは Amazon とみなされません** | offer-object |
| — | `offers[].isShippable` | そのオファーが現在発送可能か | 発送不可の例：一時的な在庫切れ、予約商品 | offer-object |
| — | `offers[].isMAP` | MAP（最低広告価格）規制により、Amazon 上で価格が隠されているか | 隠されていても、オファーオブジェクトには価格と送料が入る | offer-object |
| — | `offers[].isWarehouseDeal` | そのオファーが Amazon Warehouse のものか | — | offer-object |
| — | `offers[].minOrderQty` | 最低注文数量 | 値がある場合のみ返る | offer-object |
| 商品の状態 | `offers[].condition` | 0 不明／**1 新品**／2 中古-ほぼ新品／3 中古-非常に良い／4 中古-良い／5 中古-可／6 再生品／7〜10 コレクター品の各状態／11 レンタル | ⚠ **開封品（Open Box）は中古として符号化されます** | offer-object |
| — | `offers[].conditionComment` | 商品の状態を説明する文章 | — | offer-object |

---

### 3.4 Buy Box（カート）

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| Buy Box | `BUY_BOX_SHIPPING`（csv 18） | 新品 Buy Box 価格の履歴（送料込み） | ⚠ `offers` 必須。→ §3.1 | product-object |
| — | `stats.buyBoxPrice` | Buy Box の**新品価格**。無ければ -1 か -2 | ⚠ **`offers` または `buybox` を付けたときにしか設定されません。****送料は含まず**、別フィールド `buyBoxShipping` に入ります | statistics-object |
| — | `stats.buyBoxShipping` | Buy Box の新品**送料**。無ければ -1 か -2 | ⚠ `offers` または `buybox` 必須 | statistics-object |
| — | `stats.buyBoxSellerId` | Buy Box を取っているオファーの出品者ID。無ければ `"-1"` / `"-2"` / null | ⚠ `offers` または `buybox` 必須 | statistics-object |
| — | `buyBoxSellerIdHistory` | Buy Box を保持した出品者IDの履歴。**`-1`＝誰も Buy Box の資格を得なかった（Buy Box 抑制）／`-2`＝出品者を特定できなかった、または在庫切れ** | ⚠ `offers` または `buybox` 必須 | product-object |
| — | `stats.buyBoxIsUnqualified` | Buy Box を獲得した出品者がいるかどうか。**質の低いオファーしか無い場合、誰も Buy Box の資格を得ません** | ⚠ `offers` または `buybox` 必須 | statistics-object |
| — | `stats.buyBoxIsFBA` | Buy Box が FBA（Amazon 発送）か | 同上 | statistics-object |
| — | `stats.buyBoxIsAmazon` | Buy Box の出品者が Amazon か | 同上 | statistics-object |
| — | `stats.buyBoxIsMAP` | MAP（最低広告価格）規制により、Buy Box の新品価格が Amazon 上で非表示になっているか | 同上 | statistics-object |
| — | `stats.buyBoxAvailabilityMessage` | Buy Box オファーの入手可能性。**`IN_STOCK`（すぐ出荷可）／`BACKORDER_NO_ETA`（取り寄せ・納期不明）／`BACKORDER_WITH_ETA`（取り寄せ・納期あり）**の3値 | **2026-04 に自然文（"In Stock" など）から定数へ変更されました** | statistics-object / changelog |
| — | `stats.buyBoxShippingTime` | Buy Box オファーが出荷されるまでの推定処理時間（最小・最大の時間数）。例 `[24, 48]`＝1〜2日で出荷可 | — | statistics-object |
| — | `stats.buyBoxShippingCountry` | Buy Box 出品者の既定の発送元国。**出品者が Amazon の場合は null** | — | statistics-object |
| — | `stats.buyBoxIsPrimeEligible` / `stats.buyBoxIsPrimeExclusive` | Buy Box がプライム対象か／プライム会員限定か | — | statistics-object |
| — | `stats.buyBoxSavingBasis` / `stats.buyBoxSavingBasisType` / `stats.buyBoxSavingPercentage` | Buy Box の参考価格（打ち消し線価格）／その種別（`LIST_PRICE` または `WAS_PRICE`）／表示上の割引率 | **2026-04 以降、更新には `offers` が必要** | statistics-object / changelog |
| — | `stats.buyBoxUsedPrice` / `stats.buyBoxUsedShipping` / `stats.buyBoxUsedSellerId` / `stats.buyBoxUsedIsFBA` / `stats.buyBoxUsedCondition` | 中古 Buy Box の価格・送料・出品者ID・FBAか・サブ状態（2 ほぼ新品／3 非常に良い／4 良い／5 可） | — | statistics-object |
| Buy Box統計 | `stats.buyBoxStats` / `stats.buyBoxUsedStats` | 指定期間の Buy Box 統計。**キーが出品者ID**、値がその出品者の統計オブジェクト | ⚠ `offers` または `buybox` 必須 | statistics-object |
| %獲得 | `buyBoxStats[].percentageWon` | その出品者が Buy Box を獲得していた**時間の割合**。**非プライム客に対して** | ⚠ 「非プライム客に対して」という限定が公式に明記されています | statistics-object |
| 平均価格 | `buyBoxStats[].avgPrice` | その出品者の Buy Box オファーの平均価格 | — | statistics-object |
| — | `buyBoxStats[].avgNewOfferCount` | **その出品者が Buy Box を保持していた間の**「新品」オファー数の平均 | 商品全体の平均ではありません | statistics-object |
| — | `buyBoxStats[].isFBA` | そのオファーが FBA か | — | statistics-object |
| — | `buyBoxStats[].lastSeen` | その出品者が**最後に Buy Box を獲得した時刻**（Keepa Time 分） | — | statistics-object |
| Buy Box対象オファー数 | `buyBoxEligibleOfferCounts` | **Buy Box に適格な**オファー数。8要素の配列で、順に **0 新品FBA／1 新品FBM／2 中古FBA／3 中古FBM／4 コレクター品FBA／5 コレクター品FBM／6 再生品FBA／7 再生品FBM** | ⚠ ①**「適格な」オファーに限られる**（全オファー数ではない）②**オファー数であって出品者数ではない** | product-object |
| — | `competitivePriceThreshold` | 他の小売業者の競合価格（Amazon の他の出品者は除く）に基づく価格。**出品価格＋送料がこれを上回ると Buy Box の対象外になりうる** | — | product-object |
| — | `suggestedLowerPrice` | Amazon が提示する推奨引き下げ価格（送料込み） | — | product-object |
| — | `isSNS` | その商品の Buy Box が「定期おトク便」に対応しているか | — | product-object |

---

### 3.5 出品者情報（出品者概要画面 / Seller Object）

**keepa.com の「出品者検索」で出品者を開いたときの画面に対応します。**この節の「用語」列は、**実画面で確認した日本語表記**です。

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| **BUY BOX の平均売上数** | `avgBuyBoxCompetitors` | **この出品者が扱う商品について、Buy Box を争っている出品者数の平均**（この出品者自身を含む） | ⚠ **売上ではありません。日本語UIの表記は誤訳です。**数値が大きいほど「競合の多い棚を扱っている」という意味。**目の前の1商品の混み具合ではなく、その出品者の商品群全体の平均**です | seller-object |
| **購入ボックス切り替えの所有者** | `buyBoxNewOwnershipRate` | **新品 Buy Box の平均獲得率（％）** | ⚠ 「切り替え」は誤訳。意味は「獲得率」 | seller-object |
| **ボックスを購入する 中古の所有者** | `buyBoxUsedOwnershipRate` | **中古 Buy Box の平均獲得率（％）** | ⚠ 同上 | seller-object |
| **え**（96% などと表示） | `positiveRating` | **ポジティブ評価率（％）。ポジティブ評価とは★4または★5**を指します。直近30日・90日・365日・ライフタイムの4値をこの順で格納 | ⚠ 「え」は Rating の誤訳。**★3はポジティブに含まれません**（★3が増えると下がる） | seller-object |
| — | `negativeRating` / `neutralRating` | ネガティブ＝★1または★2／ニュートラル＝★3の比率（％）。同じく30日・90日・365日・ライフタイムの4値 | — | seller-object |
| 評価ブロック | `ratingCount` | **評価件数。**直近30日・90日・365日・ライフタイムの4値をこの順で格納 | — | seller-object |
| — | `recentFeedback` | 直近の顧客フィードバック最大5件。日時・星（**10＝★1 〜 50＝★5**）・取り消し済みか | — | seller-object |
| — | `lastRatingUpdate` | 評価データを最後に更新した時刻（Keepa Time 分） | — | seller-object |
| **FBAリストが見つかりました** | `hasFBA` | その出品者が現在FBA出品を持っているか | ⚠ 公式が「**通常は正しいが、FBA出品があっても false になりうる**（Keepa が全出品を把握できていないため。特に出品数が少なく回転の遅い出品者で起きやすい）」と明記。**「はい」は信じてよいが「いいえ」は『無い』ことの証明にならない** | seller-object |
| **確認済みリスト** | `totalStorefrontAsins` | ストアフロントASIN数と、その指標の最終更新時刻。形式 `[最終更新, 件数]` | ⚠ **2026年2月以降、Amazon のストアフロントを実際に取得した数ではなく、Keepa の内部データベース集計値**です。**実在庫数ではありません。**一度もストアフロントを取得できていなければ null | seller-object / changelog |
| — | `asinList` / `asinListLastSeen` | ストアフロントのASIN一覧（**最大10万件・新しい順**）と、各ASINを最後に確認できた時刻 | ⚠ `storefront` パラメータを使ったときのみ取得できる | seller-object |
| **重複の多い主なセラー** | `competitors` | **同じ商品を扱っていることが最も多い上位5出品者**と、その出品者と共有している出品の割合（％） | ⚠ **上位5社まで。**6位以下は「いない」のではなく「返らない」 | seller-object |
| カテゴリー別／ブランド別リスティング統計 | `sellerCategoryStatistics` / `sellerBrandStatistics` | その出品者の主要カテゴリ／ブランドの統計。`productCount`（点数）・`avg30SalesRank`（それらの30日平均ランク）・`productCountWithAmazonOffer`（うち Amazon のオファーがある数） | ⚠ 公式が自ら「**Keepa のしばしば不完全で古い出品データに基づく**」と明記。％を1桁まで信用しないこと | seller-object |
| **KEEPAによって追跡開始** | `trackingSince` | **Keepa がこの出品者の追跡を開始した時刻** | ⚠ **Amazon での開業日ではありません** | seller-object |
| — | `lastUpdate` | 出品者の基本データを最後に更新した時刻。**評価・ストアフロントの更新は含みません** | — | seller-object |
| セラーID | `sellerId` | 出品者ID（例：`A2L77EE7U53NWQ`） | — | seller-object |
| 店名 | `sellerName` | 出品者の表示名 | — | seller-object |
| 事業者名 | `businessName` | 事業者の名称 | — | seller-object |
| 住所 | `address` | 事業所の住所。配列の1要素が1行で、**最後の要素は2文字の国コード** | — | seller-object |
| — | `customerServicesAddress` | カスタマーサービスの住所（形式は `address` と同じ） | — | seller-object |
| — | `tradeNumber` | **商業登記番号**（公式の例は `HRB 123 456`＝ドイツの登記番号） | ⚠ 日本語画面の「商業番号」がこのフィールドかどうかは公式に記述がありません（→ §4） | seller-object |
| — | `vatID` | VAT（付加価値税）番号 | — | seller-object |
| 電話 | `phoneNumber` | 電話番号 | — | seller-object |
| 代表者 | `representative` | 事業者の代表者名 | — | seller-object |
| — | `businessType` / `shareCapital` / `email` | 事業形態／資本金／事業者のメールアドレス | 値がある場合のみ返る | seller-object |
| — | `seller.csv` | 出品者の履歴。**`csv[0]` ＝評価（％。0〜100の整数）／`csv[1]` ＝評価件数の累計** | 新規に作られた出品者アカウントには評価がまだ無いことがある | seller-object |

▸ **公式の注記：**Keepa の API は、**ハンドメイドカテゴリのみで販売している出品者の情報を提供しません。**

---

### 3.6 統計値（`stats`）

`stats` は、`stats` パラメータを付けたときだけ返る集計オブジェクトです。**新しいデータが増えるわけではなく、`csv` の履歴から計算されたもの**です（公式明記）。

▸ `current` / `avg` / `min` / `max` などの**配列の添字は、すべて §3.1 の csv 番号と同じ**です（`[1]` なら新品、`[11]` なら新品オファー数）。**配列の長さを固定と仮定せず、必ず番号で参照してください。**

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| — | `stats.current` | **最後に更新された時点の**価格・ランク・件数 | `-1` は「その期間にオファーが無かった（在庫切れなど）」 | statistics-object |
| — | `stats.min` / `stats.max` | **これまでに記録された中での**最安値／最高値 | ⚠ **全期間です。`stats=365` を指定しても効きません。**2次元配列で、中身は `[記録された時刻, 値]` の2要素 | statistics-object |
| — | `stats.minInInterval` / `stats.maxInInterval` | `min` / `max` と同じだが、**`stats` パラメータで指定した期間に限定** | 期間内の最安・最高を見たいときはこちら | statistics-object |
| — | `stats.avg` | 指定期間の**加重平均**（weighted mean） | ⚠ 単純平均ではありません。`-1` はデータ不足 | statistics-object |
| — | `stats.avg30` / `stats.avg90` / `stats.avg180` / `stats.avg365` | 直近30／90／180／365日の加重平均 | **`stats` で指定した期間とは独立した固定窓** | statistics-object |
| — | `stats.atIntervalStart` | **`stats` で指定した期間の開始時点**で記録されていた価格 | 期間中の値動きを測る基準に使える | statistics-object |
| — | `stats.outOfStockPercentage30` / `stats.outOfStockPercentage90` / `stats.outOfStockPercentage180` / `stats.outOfStockPercentage365` | その期間の**在庫切れ率**。**0＝一度も切れていない／100＝全期間切れていた／25＝25%の期間切れていた** | **-1＝データ不足、またはその番号が価格ではない**（ランクやオファー数の番号） | statistics-object |
| — | `stats.outOfStockPercentageInInterval` | 同上を、`stats` で指定した期間で計算したもの | — | statistics-object |
| — | `stats.lightningDealInfo` | 過去・進行中・予定のタイムセールを識別する `[開始日, 終了日]`。**予定のみなら終了日が -1**。一度もタイムセールが無ければ null | — | statistics-object |
| — | `stats.stockAmazon` / `stats.stockBuyBox` | Amazon 本体オファー／Buy Box オファーの在庫数 | ⚠ `stock` パラメータ必須（+2トークン） | statistics-object |

**`stats` パラメータで指定した期間が効くフィールド**：`stats.avg` ／ `stats.atIntervalStart` ／ `stats.minInInterval` ／ `stats.maxInInterval` ／ `stats.outOfStockPercentageInInterval` ／ `stats.buyBoxStats` ／ `stats.buyBoxUsedStats`。
**効かない（固定窓の）フィールド**：`stats.avg30`〜`stats.avg365` ／ `stats.outOfStockPercentage30`〜`365` ／ `salesRankDrops30`〜`365` ／ **`stats.min` / `stats.max`（全期間）**。（statistics-object）

---

### 3.7 商品の属性・手数料

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| — | `productType` | **最初に評価すべきフィールド**（公式明記）。**0 STANDARD**（すべて取得可）／**1 DOWNLOADABLE**・**2 EBOOK**（価格・評価・オファーのデータなし。更新頻度も低い）／**3 INACCESSIBLE**（同上。ランクとオファー数の更新頻度も低く、欠けるフィールドがある）／**4 INVALID**（無効・廃止ASIN 等で現在データなし。一時的なこともある）／**5 VARIATION_PARENT**（親ASIN） | — | product-object |
| — | `availabilityAmazon` | Amazon 本体オファーの在庫状況。**-1 Amazon のオファーが存在しない／0 在庫あり出荷可／1 予約／2 不明／3 入荷待ち／4 出荷遅延** | ⚠ **「Amazon 本体がいるか」を判定する専用フィールドはこれです。**価格履歴の `AMAZON`（csv 0）が -1 なのは「その時点で価格データが無い」という意味で、**在庫切れでも -1 になります** | product-object |
| — | `availabilityAmazonDelay` | `availabilityAmazon` が 4 のときの、遅延の幅（時間） | — | product-object |
| — | `fbaFees.pickAndPackFee` | **この商品の FBA ピック＆パック手数料。**寸法と重量、および**現在のオファー価格と等しい販売価格を仮定して**算出されます | ⚠ **FBA費用の全部ではなく「ピック＆パック」のみ**（保管料・長期保管料は含まない）。現在オファーが無ければ最後に判明した価格、それも無ければ**販売価格 100.00 を仮定した値**が入ります | product-object |
| — | `referralFeePercentage` | **仮定した販売価格における** Amazon 販売手数料の％ | ⚠ 仮定価格の決め方は `fbaFees` と同じ（現在価格→最後の価格→100.00） | product-object |
| — | `variableClosingFee` | 成約時手数料（メディア系商品） | 該当しなければ未設定 | product-object |
| — | `returnRate` | 顧客の返品率。**null＝不明または平均的／1＝返品率が低い／2＝返品率が高い** | — | product-object |
| — | `isHeatSensitive` | 熱に弱い商品か（例：溶けやすいもの） | — | product-object |
| — | `isAdultProduct` | 成人向けとみなされる商品か | — | product-object |
| — | `isHaul` / `isMerchOnDemand` | Amazon Haul の商品か／Amazon Merch on Demand の商品か | Amazon Haul の商品は基本情報しか取得できない | product-object |
| — | `isEligibleForSuperSaverShipping` | Buy Box が無料配送の対象か | — | product-object |
| — | `isEligibleForTradeIn` | 下取り対象商品か | — | product-object |
| — | `numberOfItems` / `packageQuantity` | 商品の個数／パッケージ内の個数 | 取得できなければ -1（`packageQuantity` は 0 か -1） | product-object |
| — | `parentAsin` | **親ASIN**（バリエーションがある商品の代表ASIN）。バリエーションが無ければ null | ⚠ `monthlySold` など**バリエーション単位の値**を読むときは、いま親と子のどちらを見ているかを必ず確認してください | product-object |
| — | `parentAsinHistory` | `parentAsin` の履歴。時刻は「**それまでの親ASINが有効でなくなった時点**」を示す | 親ASINの変更追跡は 2024-03-18 開始 | product-object |
| — | `variations` | バリエーション（子ASIN）の一覧 | `productType` が 5（VARIATION_PARENT）の商品で設定される | product-object |
| — | `ingredients` | 商品の原材料表示 | — | product-object |
| 商品名 | `title` | 商品タイトル | ⚠ Amazon はメディア以外の全カテゴリでタイトルを**75文字（スペース含む）**に制限しており、収まらない説明は `itemHighlights` に分けて掲載されます。**まれにエスケープされていないHTMLが混じることがある** | product-object |
| — | `itemHighlights` | タイトルに加えて表示される**最大125文字**の説明（素材・推奨用途など）。Amazon は検索対象として扱う | — | product-object |
| — | `urlSlug` | 商品ページURLのスラッグ | — | product-object |
| — | `audienceRating` | 対象年齢の目安（メディア商品） | — | product-object |

---

### 3.8 Product Finder（商品検索の絞り込み条件）

▸ この表の「用語」列は、Keepa の Product Finder 画面のラベルに対応すると**推定**されるものを含みます。**Product Finder の結果表の上にある「Show API query」を押すと、いま設定している条件の APIフィールド名がそのまま読めます**（公式の Tip）。日本語ラベルと原語の対応を確定させたいときはこれが確実です。

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| 新品 - 下落（直近7日間）ほか | `deltaPercent[1,7,30,90]_<価格タイプ>` | 現在値と、1／7／30／90日平均値との**相対差**（0〜100％）。**正の値は「値下がりした」もの、負の値は「値上がりした」ものを絞り込みます。**0 は変化なし | ⚠ **符号の向きに注意。**「値上がりした商品を探す」なら負の値を指定します | product-finder |
| — | `delta[1,7,30,90]_<価格タイプ>` | 同じものの**絶対差**（通貨の最小単位） | 符号の意味は `deltaPercent` と同じ | product-finder |
| — | `deltaLast_<価格タイプ>` | 現在値と**直前の値**との差 | 正＝下落／負＝上昇 | product-finder |
| — | `isLowest_<価格タイプ>` / `isLowest90_<価格タイプ>` | 現在価格が**史上最安か**／**直近90日で最安か**（真偽値） | — | product-finder |
| — | `isLowestOffer` | 選んだ価格タイプが、**全新品オファーの中で最安か**（Amazon 本体とマーケットプレイス新品に適用） | — | product-finder |
| — | `current_<価格タイプ>` / `avg30_<価格タイプ>` 等 | `stats` の各値による絞り込み。価格タイプ名は `AMAZON` `NEW` `BUY_BOX_SHIPPING` など | — | product-finder |
| — | `availabilityAmazon` | Amazon 本体オファーの在庫状況（値は §3.7 と同じ） | ⚠ Amazon 本体がいない商品を除外・抽出する条件はこれ | product-finder |
| — | `buyBoxStatsSellerCount[30,90,180,365]` | その期間に **Buy Box を獲得したことがある出品者の数** | ⚠ 「オファーを出している出品者数」とは別物（**Buy Box を一度も取れなかった出品者は数えられません**） | product-finder |
| — | `buyBoxStatsAmazon[30,90,180,365]` | その期間に **Amazon 本体のオファーが Buy Box を保持していた割合（％）** | — | product-finder |
| — | `buyBoxStatsTopSeller[30,90,180,365]` | 最も Buy Box 獲得率が高い出品者のシェア（％。**Amazon を含む**） | — | product-finder |
| — | `sellerIds` / `sellerIdsLowestFBA` / `sellerIdsLowestFBM` / `buyBoxUsedSellerId` | 出品者IDによる絞り込み（出品している／FBA最安／FBM最安／中古Buy Box 適格） | — | product-finder |
| — | `minMatch` | 配列条件の **K-of-N 一致**。既定では配列内の項目は OR（どれか1つ該当すればよい）だが、`{"sellerIds": 2}` と書くと**列挙した出品者のうち2社以上**が出品している商品だけに絞れる | 項目数と同じ数を指定すると AND になる | product-finder |
| — | `title` | 商品タイトルの**キーワード単位**の検索（最大50語・大文字小文字は区別しない）。**部分一致は不可。**`"Digital Camera"` でフレーズ指定、`-digital` で除外 | — | product-finder |
| — | `manufacturer` / `brand` 等 | 製造者名・ブランド名などの文字列配列による絞り込み | — | product-finder |
| — | `rootCategory` / `categories_include` / `categories_exclude` | ルートカテゴリ／サブカテゴリでの絞り込み（それぞれ最大50件のカテゴリノードID） | — | product-finder |
| — | `monthlySold` / `deltaPercent90_monthlySold` | 月間販売数（→ §3.2）／その直近90日の変化率（％） | ⚠ **大半のASINは `monthlySold` の値を持ちません** | product-finder |
| — | `monthlySoldPeak` / `monthlySoldPeakDate` / `monthlySoldLastKnown` / `monthlySoldLastKnownDate` | 月間販売数の**過去最高値**とその時期／**最後に判明した値**とその時期 | — | product-finder |
| — | `outOfStockPercentage90` | 直近90日の在庫切れ率。価格タイプ別の形（`_BB` / `_BB_USED` / `_NEW` / `_USED`）もある | — | product-finder |
| — | `outOfStockCountAmazon30` / `outOfStockCountAmazon90` | 直近30／90日に Amazon 本体が在庫切れになった**回数** | — | product-finder |
| — | `trackingSince` / `lastPriceChange` / `lastOffersUpdate` | Keepa が追跡を開始した時刻／最後に価格変動が記録された時刻／**オファー関連データが最後に更新された時刻** | `lastOffersUpdate` は「オファー系データが新しい商品だけ」を取り出すのに使える | product-finder |
| — | `hasReviews` / `returnRate` / `productType` | レビューの有無／返品率／商品タイプによる絞り込み | — | product-finder |
| — | `hasParentASIN` / `singleVariation` / `historicalParentASIN` | 親ASINを持つか／1商品につきバリエーション1件だけ返す／親ASINから過去の子ASINを探す | — | product-finder |
| — | `variationCount` | **この商品のバリエーション数**による絞り込み | ⚠ **バリエーションの無い商品でこの値が 0 になるのか 1 になるのかは、公式に記述がありません**（→ §4）。`variationCount ≧ 1` のような条件を置くと、意図せず全商品を落としうる | product-finder |
| — | `dealType` | セールバッジの種類（`LIMITED_TIME_DEAL` `PRIME_EXCLUSIVE` `CLEARANCE_NO_RETURNS` など13種） | — | product-finder |
| — | `page` / `perPage` | ページ番号／1ページの件数（既定・最小50件） | ⚠ **`page=0` のときだけ `perPage` を最大10,000にできます。**0以外のページでは `page × perPage` が10,000を超えてはいけません | product-finder |

---

### 3.9 リクエストとトークン

**トークン**＝ Keepa API を使うための「回数券」です。プランごとに毎分一定数が補充され、リクエストのたびに消費されます。

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| トークンバケット | — | プランは**毎分 R トークンを24時間365日生成し続け**、リクエストがそれを消費する仕組み。**各トークンの有効期限は60分**で、バケツの容量は **R × 60 トークン** | ⚠ **未使用分は60分で失効します。**貯められるのは1時間分だけ（＝一度に使える最大量でもある） | plans-tokens |
| — | `tokensLeft` / `refillRate` / `refillIn` | すべてのAPIレスポンスに入る、**現在のトークン残高**／補充レート／次の補充までの時間 | — | request-basics |
| — | `stats`（パラメータ） | `stats` オブジェクトを付けて返す。**直近x日**、または**期間の指定**（ISO8601 の日付2つ、または Unix ミリ秒2つ） | **追加トークンなし。**新しいデータが増えるわけではなく、`csv` から計算されます | product |
| — | `offers`（パラメータ） | 取得する**最新のマーケットプレイスオファー数**（20〜100） | ⚠ **見つかったオファーページ1枚（最大10オファー）につき6トークン。**オファーが1件も無くても、取得に成功すれば最低5トークン。**`offers` を使うと基本の1トークン/ASIN は適用されません** | product |
| — | `buybox`（パラメータ） | Buy Box 関連データを付けて返す | **+2トークン/商品** | product |
| — | `stock`（パラメータ） | 在庫数を付けて返す | **+2トークン/商品** | product |
| — | `rating`（パラメータ） | 評価・レビュー件数の履歴を付けて返す | **最大 +1トークン/商品** | product |
| — | `only-live-offers`（パラメータ） | 現存オファーだけを返す（`offers` と併用） | 追加トークンなし。**現存オファーだけを要求して取得に失敗した場合、トークンは消費されません** | product |
| — | `update`（パラメータ） | 「最後の更新が **N 時間**より古ければ強制的に更新する」の N。**既定は 1 時間** | **`update=0`＝常に最新を取る**（前回更新が1時間以内なら +1トークン）。**`update=-1`＝更新しない**（Keepa のDBに無い商品なら**0トークン**で何も返さない） | product |
| — | `history`（パラメータ） | `history=0` で `csv`・`salesRanks` などの履歴を返さない | 追加トークンなし。レスポンスを大幅に軽くできる | product |
| — | `days`（パラメータ） | 履歴を直近N日に制限する | 追加トークンなし | product |
| Product Finder のトークン単価 | — | **1リクエスト 10トークン ＋ 結果100ASINあたり1トークン** | — | product-finder |
| Seller Finder | — | 出品者データベースを条件検索して**出品者IDの一覧だけ**を返すエンドポイント（2026-08-09 新設）。**10トークン＋返却100件あたり1トークン** | 返るのはIDのみ。中身は Seller Information で引き直す | changelog |
| Domain ID（市場） | — | 対象マーケットプレイスの番号。**1 com／2 co.uk／3 de／4 fr／5 co.jp／6 ca／8 it／9 es／10 in／11 com.mx／12 com.br**。**日本は 5** | ⚠ Keepa 自身のドキュメント内で不統一：`product.html` `product-finder.html` `seller-object.html` は 12（com.br）まで載せていますが、**`product-object.html` だけ 11（com.mx）までしか載せていません**（2026-08-24 時点） | product / product-finder / seller-object / product-object |
| 公式 MCP サーバ | — | Keepa 自身がホストする AI アシスタント向け接続口（`https://keepa.com/mcp`）。認証は既存のAPIアクセスキー、消費するのは**契約中プランのトークン**で、新規契約や追加課金は不要 | ⚠ 公式が「**APIキーは秘密。キーを書いた設定ファイルを共有リポジトリにコミットしてはならない**」と明記。応答は**プログラム向けではなく言語モデル向けに整形**されている（コードを書くなら REST API を直接使え、と公式） | mcp |

---

### 3.10 グラフ・トラッキング（画面まわり）

| 用語 | APIフィールド名 | 意味 | 注意 | 出典 |
|---|---|---|---|---|
| グラフ①「価格履歴」 | — | 価格の推移とルートカテゴリの売れ筋ランキングを描くグラフ | 描ける csv 型：0〜10・15・18〜30・32・33 | graph-image |
| グラフ②「カテゴリ別ランキング＆月間販売数」 | — | カテゴリ別のランクと月間販売数を描くグラフ | ⚠ **csv 型からは作られません**（専用のパラメータで指定） | graph-image |
| グラフ③「オファー数と評価」 | — | オファー数・星評価・評価件数を描くグラフ | 描ける csv 型：11〜14・16・17・34・35 | graph-image |
| 再開タイマー（Rearm Timer） | — | 価格アラートが一度鳴ったあと、次に鳴るまでの休止期間。**既定は7日間** | 「しない」＝到達したらそのアラートは無効化（再通知には希望価格の変更が必要）。「x日間」＝到達後 x日休止して再有効化。**希望価格ごとに独立**しており、1商品に複数の希望価格を設定できる | FAQ |
| トラッキング | — | 商品の価格を監視して通知を受ける機能 | ⚠ **誰かがトラッキングしている商品は1時間に1回、していない商品は1日1回**しか更新されません（→ §2-8） | FAQ |

---

## 4. 定義が確認できていない語

**以下は公式に定義が見つかりませんでした。推測で埋めていません。判断に使わないでください。**

| 語 | 状態 |
|---|---|
| **評価 -1%**（Dataタブ Buy Box統計の評価列） | 公式の `buyBoxStats` に評価の項目自体が存在しない。**定義不明** |
| **商業番号**（出品者概要画面） | 近いのは `tradeNumber`（商業登記番号）だが、**日本の許可番号との対応は公式に記述なし** |
| **Data Quota / Quota: 100%**（keepa.com 画面右上） | 公式APIドキュメントに記述なし。**APIトークンとは別勘定**である点だけが確定 |
| **日本語UIラベルの原語**（全般） | Keepa は UI 用語集を公開していない。Product Finder は「Show API query」で確定できる（→ §3.8） |
| **出品者概要画面が無料プランで開けるか** | 公式の記述を発見できず |
| `variationCount`（バリエーション無し商品での値） | **0 か 1 か、公式に記述なし** |

---

## 5. 出典

**すべて 2026-08-24 に確認。**表の「出典」列の略号は以下に対応します。

| 略号 | URL |
|---|---|
| product-object | `https://keepa.com/api-docs/product-object.html` |
| statistics-object | `https://keepa.com/api-docs/statistics-object.html` |
| offer-object | `https://keepa.com/api-docs/offer-object.html` |
| seller-object | `https://keepa.com/api-docs/seller-object.html` |
| product | `https://keepa.com/api-docs/product.html` |
| product-finder | `https://keepa.com/api-docs/product-finder.html` |
| plans-tokens | `https://keepa.com/api-docs/plans-tokens.html` |
| request-basics | `https://keepa.com/api-docs/request-basics.html` |
| graph-image | `https://keepa.com/api-docs/graph-image.html` |
| changelog | `https://keepa.com/api-docs/changelog.html` |
| mcp | `https://keepa.com/api-docs/mcp.html` |
| FAQ | `https://keepa.com/#!support`（日本語UI・未ログインで閲覧可） |

▸ **Keepa に、利用者向けの操作マニュアルは存在しません。**`keepa.com/help` `/faq` `/manual` `/guide` `/docs` `/tutorial` はいずれも 404 です。**用語の定義を確定できる一次情報は、上記の API ドキュメントだけ**です。

---

## 索引A｜日本語表記から引く

**記号・英字から始まる語**

| 見出し語 | 掲載 |
|---|---|
| %獲得 | §3.4 |
| Amazon | §3.1 |
| Amazon倉庫 | §3.1 |
| Buy Box | §3.1 / §3.4 |
| BUY BOX の平均売上数 | §3.5 |
| Buy Box 中古 | §3.1 |
| Buy Box対象オファー数 | §3.4 |
| Buy Box統計 | §3.4 |
| Domain ID（市場） | §3.9 |
| eBay 中古 | §3.1 |
| eBay 新品 | §3.1 |
| FBAリストが見つかりました | §3.5 |
| KEEPAによって追跡開始 | §3.5 |
| Product Finder のトークン単価 | §3.9 |
| Seller Finder | §3.9 |
| ↘ N drops | §3.2 |

**五十音順**

| 見出し語 | 掲載 |
|---|---|
| 売れ筋ランキング | §3.1 |
| え（96% などと表示） | §3.5 |
| オファー数　→「新品アイテム数」「totalOfferCount」 | §3.3 |
| 確認済みリスト | §3.5 |
| カテゴリ　→「カテゴリ別ランキング」「rootCategory」 | §3.2 |
| カテゴリ別ランキング | §3.2 |
| カテゴリー別／ブランド別リスティング統計 | §3.5 |
| カート　→「Buy Box」 | §3.1 |
| グラフ①「価格履歴」 | §3.10 |
| グラフ②「カテゴリ別ランキング＆月間販売数」 | §3.10 |
| グラフ③「オファー数と評価」 | §3.10 |
| 月間販売数　→「先月の購入／月間販売数」 | §3.2 |
| 公式 MCP サーバ | §3.9 |
| 購入ボックス切り替えの所有者 | §3.5 |
| コレクター商品 | §3.1 |
| コレクター商品アイテム数 | §3.1 |
| コレクター商品（4状態） | §3.1 |
| 再開タイマー（Rearm Timer） | §3.10 |
| 再生品 | §3.1 |
| 再生品アイテム数 | §3.1 |
| 再生品（送料込み） | §3.1 |
| 最安値　→「stats.min」（全期間）「stats.minInInterval」（期間内） | §3.6 |
| 参考価格 | §3.1 |
| 在庫切れ率　→「stats.outOfStockPercentage30」 | §3.6 |
| 下取り | §3.1 |
| 出品者数（実数） | §3.3 |
| 商品の状態 | §3.3 |
| 商品名 | §3.7 |
| 新品 | §3.1 |
| 新品アイテム数 | §3.1 / §3.3 |
| 新品 - 下落（直近7日間）ほか | §3.8 |
| 新品 第三者（FBA） | §3.1 |
| 新品 第三者（自己発送） | §3.1 |
| 事業者名 | §3.5 |
| 住所 | §3.5 |
| セラーID | §3.5 |
| 先月の購入／月間販売数 | §3.2 |
| タイムセール | §3.1 |
| 代表者 | §3.5 |
| 中古 | §3.1 |
| 中古アイテム数 | §3.1 |
| 中古（ほぼ新品／非常に良い／良い／可） | §3.1 |
| 重複の多い主なセラー | §3.5 |
| 手数料　→「fbaFees.pickAndPackFee」「referralFeePercentage」 | §3.7 |
| 店名 | §3.5 |
| 電話 | §3.5 |
| トラッキング | §3.10 |
| トークン　→「トークンバケット」 | §3.9 |
| トークンバケット | §3.9 |
| ドロップ数　→「↘ N drops」 | §3.2 |
| 販売者 | §3.3 |
| バリエーション　→「parentAsin」「variations」「variationCount」 | §3.7 |
| 評価 | §3.1 |
| 評価件数 | §3.1 |
| 評価ブロック | §3.5 |
| プライム会員限定 | §3.1 |
| 平均売上数　→「BUY BOX の平均売上数」 | §3.5 |
| 平均価格 | §3.4 |
| ボックスを購入する 中古の所有者 | §3.5 |

---

## 索引B｜英語・APIフィールド名から引く

**A**

| フィールド名 | 掲載 |
|---|---|
| `address` | §3.5 |
| `AMAZON` | §3.1 |
| `asinList` | §3.5 |
| `asinListLastSeen` | §3.5 |
| `audienceRating` | §3.7 |
| `availabilityAmazon` | §3.7 / §3.8 |
| `availabilityAmazonDelay` | §3.7 |
| `avg30_<価格タイプ>` | §3.8 |
| `avgBuyBoxCompetitors` | §3.5 |

**B**

| フィールド名 | 掲載 |
|---|---|
| `brand` | §3.8 |
| `businessName` | §3.5 |
| `businessType` | §3.5 |
| `BUY_BOX_SHIPPING` | §3.1 / §3.4 |
| `BUY_BOX_USED_SHIPPING` | §3.1 |
| `buybox` | §3.9 |
| `buyBoxEligibleOfferCounts` | §3.4 |
| `buyBoxNewOwnershipRate` | §3.5 |
| `buyBoxSellerIdHistory` | §3.4 |
| `buyBoxStats[].avgNewOfferCount` | §3.4 |
| `buyBoxStats[].avgPrice` | §3.4 |
| `buyBoxStats[].isFBA` | §3.4 |
| `buyBoxStats[].lastSeen` | §3.4 |
| `buyBoxStats[].percentageWon` | §3.4 |
| `buyBoxStatsAmazon[30,90,180,365]` | §3.8 |
| `buyBoxStatsSellerCount[30,90,180,365]` | §3.8 |
| `buyBoxStatsTopSeller[30,90,180,365]` | §3.8 |
| `buyBoxUsedOwnershipRate` | §3.5 |
| `buyBoxUsedSellerId` | §3.8 |

**C**

| フィールド名 | 掲載 |
|---|---|
| `categories_exclude` | §3.8 |
| `categories_include` | §3.8 |
| `COLLECTIBLE` | §3.1 |
| `COLLECTIBLE_*_SHIPPING` | §3.1 |
| `competitivePriceThreshold` | §3.4 |
| `competitors` | §3.5 |
| `COUNT_COLLECTIBLE` | §3.1 |
| `COUNT_NEW` | §3.1 / §3.3 |
| `COUNT_NEW_FBA` | §3.1 |
| `COUNT_NEW_FBM` | §3.1 |
| `COUNT_REFURBISHED` | §3.1 |
| `COUNT_REVIEWS` | §3.1 |
| `COUNT_USED` | §3.1 |
| `current_<価格タイプ>` | §3.8 |
| `customerServicesAddress` | §3.5 |

**D**

| フィールド名 | 掲載 |
|---|---|
| `days` | §3.9 |
| `dealType` | §3.8 |
| `delta[1,7,30,90]_<価格タイプ>` | §3.8 |
| `deltaLast_<価格タイプ>` | §3.8 |
| `deltaPercent90_monthlySold` | §3.8 |
| `deltaPercent[1,7,30,90]_<価格タイプ>` | §3.8 |

**E**

| フィールド名 | 掲載 |
|---|---|
| `EBAY_NEW_SHIPPING` | §3.1 |
| `EBAY_USED_SHIPPING` | §3.1 |
| `email` | §3.5 |
| `EXTRA_INFO_UPDATES` | §3.1 |

**F**

| フィールド名 | 掲載 |
|---|---|
| `fbaFees.pickAndPackFee` | §3.7 |

**H**

| フィールド名 | 掲載 |
|---|---|
| `hasFBA` | §3.5 |
| `hasParentASIN` | §3.8 |
| `hasReviews` | §3.8 |
| `historicalParentASIN` | §3.8 |
| `history` | §3.9 |

**I**

| フィールド名 | 掲載 |
|---|---|
| `ingredients` | §3.7 |
| `isAdultProduct` | §3.7 |
| `isEligibleForSuperSaverShipping` | §3.7 |
| `isEligibleForTradeIn` | §3.7 |
| `isHaul` | §3.7 |
| `isHeatSensitive` | §3.7 |
| `isLowest90_<価格タイプ>` | §3.8 |
| `isLowest_<価格タイプ>` | §3.8 |
| `isLowestOffer` | §3.8 |
| `isMerchOnDemand` | §3.7 |
| `isSNS` | §3.4 |
| `itemHighlights` | §3.7 |

**L**

| フィールド名 | 掲載 |
|---|---|
| `lastOffersUpdate` | §3.8 |
| `lastPriceChange` | §3.8 |
| `lastRatingUpdate` | §3.5 |
| `lastSoldUpdate` | §3.2 |
| `lastUpdate` | §3.5 |
| `launchpad` | §3.2 |
| `LIGHTNING_DEAL` | §3.1 |
| `LISTPRICE` | §3.1 |
| `liveOffersOrder` | §3.3 |

**M**

| フィールド名 | 掲載 |
|---|---|
| `manufacturer` | §3.8 |
| `minMatch` | §3.8 |
| `monthlySold` | §3.2 / §3.8 |
| `monthlySoldHistory` | §3.2 |
| `monthlySoldLastKnown` | §3.8 |
| `monthlySoldLastKnownDate` | §3.8 |
| `monthlySoldPeak` | §3.8 |
| `monthlySoldPeakDate` | §3.8 |

**N**

| フィールド名 | 掲載 |
|---|---|
| `negativeRating` | §3.5 |
| `neutralRating` | §3.5 |
| `NEW` | §3.1 |
| `NEW_FBA` | §3.1 |
| `NEW_FBM_SHIPPING` | §3.1 |
| `numberOfItems` | §3.7 |

**O**

| フィールド名 | 掲載 |
|---|---|
| `offerCountFBA` | §3.3 |
| `offerCountFBM` | §3.3 |
| `offerDuplicates` | §3.3 |
| `offers` | §3.9 |
| `offers[].condition` | §3.3 |
| `offers[].conditionComment` | §3.3 |
| `offers[].isAmazon` | §3.3 |
| `offers[].isFBA` | §3.3 |
| `offers[].isMAP` | §3.3 |
| `offers[].isPrime` | §3.3 |
| `offers[].isShippable` | §3.3 |
| `offers[].isWarehouseDeal` | §3.3 |
| `offers[].lastSeen` | §3.3 |
| `offers[].minOrderQty` | §3.3 |
| `offers[].offerCSV` | §3.1 |
| `offers[].sellerId` | §3.3 |
| `offersSuccessful` | §3.3 |
| `only-live-offers` | §3.9 |
| `outOfStockCountAmazon30` | §3.8 |
| `outOfStockCountAmazon90` | §3.8 |
| `outOfStockPercentage90` | §3.8 |

**P**

| フィールド名 | 掲載 |
|---|---|
| `packageQuantity` | §3.7 |
| `page` | §3.8 |
| `parentAsin` | §3.7 |
| `parentAsinHistory` | §3.7 |
| `perPage` | §3.8 |
| `phoneNumber` | §3.5 |
| `positiveRating` | §3.5 |
| `PRIME_EXCL` | §3.1 |
| `productType` | §3.7 / §3.8 |

**R**

| フィールド名 | 掲載 |
|---|---|
| `RATING` | §3.1 |
| `rating` | §3.9 |
| `ratingCount` | §3.5 |
| `recentFeedback` | §3.5 |
| `referralFeePercentage` | §3.7 |
| `refillIn` | §3.9 |
| `refillRate` | §3.9 |
| `REFURBISHED` | §3.1 |
| `REFURBISHED_SHIPPING` | §3.1 |
| `RENT` | §3.1 |
| `representative` | §3.5 |
| `retrievedOfferCount` | §3.3 |
| `returnRate` | §3.7 / §3.8 |
| `rootCategory` | §3.8 |

**S**

| フィールド名 | 掲載 |
|---|---|
| `SALES` | §3.1 |
| `salesRankDisplayGroup` | §3.2 |
| `salesRankDrops180` | §3.2 |
| `salesRankDrops30` | §3.2 |
| `salesRankDrops365` | §3.2 |
| `salesRankDrops90` | §3.2 |
| `salesRankReference` | §3.2 |
| `salesRankReferenceHistory` | §3.2 |
| `salesRanks` | §3.2 |
| `seller.csv` | §3.5 |
| `sellerBrandStatistics` | §3.5 |
| `sellerCategoryStatistics` | §3.5 |
| `sellerId` | §3.5 |
| `sellerIds` | §3.8 |
| `sellerIdsLowestFBA` | §3.3 / §3.8 |
| `sellerIdsLowestFBM` | §3.3 / §3.8 |
| `sellerName` | §3.5 |
| `shareCapital` | §3.5 |
| `singleVariation` | §3.8 |
| `stats` | §3.9 |
| `stats.atIntervalStart` | §3.6 |
| `stats.avg` | §3.6 |
| `stats.avg180` | §3.6 |
| `stats.avg30` | §3.6 |
| `stats.avg365` | §3.6 |
| `stats.avg90` | §3.6 |
| `stats.buyBoxAvailabilityMessage` | §3.4 |
| `stats.buyBoxIsAmazon` | §3.4 |
| `stats.buyBoxIsFBA` | §3.4 |
| `stats.buyBoxIsMAP` | §3.4 |
| `stats.buyBoxIsPrimeEligible` | §3.4 |
| `stats.buyBoxIsPrimeExclusive` | §3.4 |
| `stats.buyBoxIsUnqualified` | §3.4 |
| `stats.buyBoxPrice` | §3.4 |
| `stats.buyBoxSavingBasis` | §3.4 |
| `stats.buyBoxSavingBasisType` | §3.4 |
| `stats.buyBoxSavingPercentage` | §3.4 |
| `stats.buyBoxSellerId` | §3.4 |
| `stats.buyBoxShipping` | §3.4 |
| `stats.buyBoxShippingCountry` | §3.4 |
| `stats.buyBoxShippingTime` | §3.4 |
| `stats.buyBoxStats` | §3.4 |
| `stats.buyBoxUsedCondition` | §3.4 |
| `stats.buyBoxUsedIsFBA` | §3.4 |
| `stats.buyBoxUsedPrice` | §3.4 |
| `stats.buyBoxUsedSellerId` | §3.4 |
| `stats.buyBoxUsedShipping` | §3.4 |
| `stats.buyBoxUsedStats` | §3.4 |
| `stats.current` | §3.6 |
| `stats.lightningDealInfo` | §3.6 |
| `stats.max` | §3.6 |
| `stats.maxInInterval` | §3.6 |
| `stats.min` | §3.6 |
| `stats.minInInterval` | §3.6 |
| `stats.outOfStockPercentage180` | §3.6 |
| `stats.outOfStockPercentage30` | §3.6 |
| `stats.outOfStockPercentage365` | §3.6 |
| `stats.outOfStockPercentage90` | §3.6 |
| `stats.outOfStockPercentageInInterval` | §3.6 |
| `stats.stockAmazon` | §3.6 |
| `stats.stockBuyBox` | §3.6 |
| `stock` | §3.9 |
| `suggestedLowerPrice` | §3.4 |

**T**

| フィールド名 | 掲載 |
|---|---|
| `title` | §3.7 / §3.8 |
| `tokensLeft` | §3.9 |
| `totalOfferCount` | §3.3 |
| `totalStorefrontAsins` | §3.5 |
| `trackingSince` | §3.5 / §3.8 |
| `TRADE_IN` | §3.1 |
| `tradeNumber` | §3.5 |

**U**

| フィールド名 | 掲載 |
|---|---|
| `update` | §3.9 |
| `urlSlug` | §3.7 |
| `USED` | §3.1 |
| `USED_ACCEPTABLE_SHIPPING` | §3.1 |
| `USED_GOOD_SHIPPING` | §3.1 |
| `USED_NEW_SHIPPING` | §3.1 |
| `USED_VERY_GOOD_SHIPPING` | §3.1 |

**V**

| フィールド名 | 掲載 |
|---|---|
| `variableClosingFee` | §3.7 |
| `variationCount` | §3.8 |
| `variations` | §3.7 |
| `vatID` | §3.5 |

**W**

| フィールド名 | 掲載 |
|---|---|
| `WAREHOUSE` | §3.1 |

**#**

| フィールド名 | 掲載 |
|---|---|
| `(該当フィールドなしの概念)` | §3.3 |
