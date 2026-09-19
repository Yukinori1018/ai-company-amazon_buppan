# Keepa API の利用価値と継続判断（S-A）

T-20260920-002 / サトル（リサーチャー） / 2026-09-20
親: T-20260915-002 → T-20260920-002。判断期限: **2026-10-03**（10-04 に €49 自動更新）

---

## 1. 結論

1. **止めてよい。** 型A（メーカー大量連絡→独占）を実際に回している実践者は、調べた範囲で**1人も Keepa API を使っていません**。使っているのは全員 **ウェブ版 Pro（€29）の Product Finder / Seller Lookup / Best Sellers** です。API を払っているのは「ツールを作って売る人・SaaS・研究者」でした。
2. 当社の API 用途8系統のうち、**型Aで今後も繰り返し要るのは「見積り後の実売確認」と「取引開始後の価格監視」の2つだけ**で、どちらも Amazon の画面（過去1か月に N 点購入）と Pro で代替できます。連絡先メーカーの母数は 2,425社＝**週70通で35週分**あり、更新は8ヶ月後まで不要です（出典: T-20260914-006/01）。
3. 推奨は **③ いったん解約 → 必要な月だけ再契約**。10/2 までに T-3・S-3 の抽出を終えること、再契約は新規契約（Keepa は理由なしに断れる・§3(3)）という2点が条件です。**年10.4万円の固定費を落とせます**（黒字確率への効きは §7）。

> 事実と推測の境目: 「実践者が API を使っていない」は**出典付きの事実**（§3・§4）。「当社が止めても詰まらない」は工程を並べた上での**判定＝推測（確度 中〜高）**で、§6 に根拠を置きました。

---

## 2. イシューと調査スコープ

**イシュー: Keepa API（€49/月）は、型Aを主戦略にした当社の工程のどこかで「無いと詰まる」か。**

| 項目 | 内容 |
|---|---|
| 調査した対象 | Keepa **API** を実務で回している人・事業者（日本・海外）／API をバックエンドに使う商用ツール／GitHub 実装／Keepa 公式 api-docs |
| 打ち切り条件 | 実例20件、または「これ以上は API か Pro かの区別が付かない二次記事しか出ない」ライン。**実際は21件で打ち切り**（§3） |
| 調べなかったこと | Keepa の有料フォーラム・Discord・有料 note の本文（課金が必要＝§4.1）／paywall 記事（付録B に「取得できず」で記載） |
| API は叩いていない | 今回トークン消費ゼロ。解約・契約操作もしていない |

**この調査のロードマップ上の位置**: 10/03 の解約期限に対する社長判断の材料。次につながるのは「固定費を落として12ヶ月黒字の条件を満たす」判断と、「型Aのリサーチ手段を Pro 系に一本化するか」の戦略判断（＝タケシの領分）。

---

## 3. Keepa API を実務で回している実例（21件）

「誰が / 事業 / 使うエンドポイント / 何の判断 / 頻度・規模 / 成果の記載」。**空欄は「記載なし」、未調査は明記**。出典URLは付録A（全件 2026-09-20 取得）。

### 3-1. API を**自分で叩いている**人・組織（＝API 課金者）

| # | 誰が | 事業 | エンドポイント | 何の判断のために | 頻度・規模 | 月利/成果の記載 |
|---|---|---|---|---|---|---|
| 1 | ツールドブッパン（Ryoku） | 欧米輸入＋自作ツールの配布 | product / seller / Finder | 「SELLER LISTER」= 複数ASINからセラーIDを集めてセラー一覧を自動生成 → ライバルの出品ASINを丸ごと吸う | ツール配布（2026-02 で配布終了） | 記載なし |
| 2 | amznlog（zent） | 輸入ビジネス＋エンジニア。ツール monoPeak / AsinKeeper を開発 | product（history・stats） | MWS では取れないランキング変動数を取る。AsinKeeper は47項目を抽出 | 1商品1トークン。€15/5トークン分プランで月21.6万トークン | 記載なし。**「個人で扱うことを目的としたAPIではないかも」と明記** |
| 3 | TechTech Note | 中国輸入＋無在庫（副業・試作段階） | product のみ | 手元のASINリストを6条件（1,600円以上・評価3.5以上・複数セラー・2kg未満・30日販売数・利益率20%以上）でふるいにかける | 1回80ASIN（API上限100） | 記載なし。「面倒な手作業の自動化には値する」 |
| 4 | ZIDOOKA!（関西のフリーランスエンジニア） | 業務自動化の受託 | product（history・stats） | GAS から価格履歴・ランキングを取る解説（自社運用の記録ではなく実装解説） | 記載なし | 記載なし |
| 5 | Jürgensmeier & Skiera（Goethe大 ほか） | 学術研究（Amazon の自己優遇の計測） | product（offers/オファー数） | 11マーケットプレイスのオファー構成を測り、Amazon 本体が買い物かごを持つ比率を推定 | 2024-01-19 に11市場を一括取得。N=数十万件規模 | Journal of Marketing 2025 ほか査読論文。R パッケージ `keepar` を公開 |
| 6 | United-Compute | GPU の市場価格ウォッチ（物販ではない） | product | GPU の日次価格を追い、TFLOPS/$ を公開 | GitHub Actions で毎日・28 stars | 記載なし |
| 7 | BWB03 | MCP サーバ「keepa-adapter」の開発 | 33ツール＝公式エンドポイント全網羅 | Claude Desktop から Keepa を引く。ローカルにスナップショット保存・差分検知・BSR分析・販促効果測定 | 2026-09-14 更新・15 stars | 記載なし |
| 8 | akaszynski ほか | Python クライアント `keepa`（非公式・公式が推奨） | product / Finder / deals / seller / bestsellers | 上記すべての土台 | 315 stars・PyPI 公開 | 記載なし |
| 9 | Keepa GmbH 公式 | Java / PHP フレームワーク配布 | 全エンドポイント | 開発者の統合用 | — | — |
| 10 | ntwholesales | GitHub「FBA Brand Sourcing Scanner」 | Finder → product | **仕入れ先のブランドリストを投げて、そのブランドのAmazon商品を日次でスコアリング** | 日次 cron・CSV 出力・0 stars | **成果の記載なし。README に「私（Claude）はライブAPIを叩けない」と書かれた AI 生成コードで、稼いだ実績の証拠ではない** |
| 11 | GitHub 全体 | — | `api.keepa.com` を含むコードは **560件**（リポジトリ検索は KeePass のノイズ多数） | — | 2026-09-20 実測 | — |

### 3-2. API を**製品に組み込んで売っている**事業者（＝API 課金者。当社の代替候補）

| # | 事業者 | 何を売っているか | Keepa の使い方 | 価格 | 備考 |
|---|---|---|---|---|---|
| 12 | Seller Assistant | Amazon 卸／OA 向け SaaS。Price List Analyzer（**卸の価格表を丸ごと流して利益商品を抽出**）・拡張機能 | **Keepa API + Amazon SP-API を自社で統合**し、自社APIとして Keepa の product / Finder も再提供 | 年払 $13.33/月〜、月払 Pro $29.99〜。14日無料 | 当社の「卸価格表 × Amazon 実売」の照合をそのまま代替する製品 |
| 13 | Databar.ai | ノーコードのデータ連携 | Keepa API コネクタ | 未調査 | 行単位課金型 |
| 14 | Keepa API Connector（Google Workspace アドオン） | スプレッドシート用アドオン | セラーID/カテゴリID から ASIN 一括取得、カート価格・30日平均・**30日販売数**を取得 | 未調査（別途 API キーが要ると推測） | 当社の GAS 自作を置き換える位置 |
| 15 | Helium 10 / AMZScout / 主要 OA アプリ | リサーチツール | Keepa グラフを内部に埋め込み（**二次情報**・確度中） | 各社 | Keepa が業界のデータ基盤である傍証 |

### 3-3. **API を使っていない**高実績の実践者（ウェブ版 Pro で同じ仕事をしている）

| # | 誰が | 実績の記載 | 使っている機能 | 何の判断のために | API 言及 |
|---|---|---|---|---|---|
| 16 | **EC STARs Lab.／中西恒太**（当社が型Aの原典にしている人） | スクール運営・メーカー仕入れの指導 | **Keepa 有料版（Pro）必須と明記**（「必ず有料版にして使ってください」€19≒3,400円/月） | ランク5万位以内・Amazon本体なし・出品者数などで商品を絞り、そこからメーカーを辿る | **一切なし** |
| 17 | ECセラーラボ（メーカー仕入れのリサーチ手順） | — | **Keepa Chrome 拡張 ＋ Amazon 管理画面 ＋ スプレッドシート** | カテゴリリサーチ／**セラーリサーチ（メーカー仕入れをしている他セラーの出品商品からメーカーを逆引き）**。ランク5万位以内・カート取得率80%未満 | なし |
| 18 | Simon Knight（FBA Mogul） | **自称 7 Figure Amazon Seller**（UK/ドバイ） | **Pro ウェブの Product Finder**（「Product Finder は有料サブスクが必要」と明記） | **仕入れ先のブランドリストを貼って、その全商品をAmazon上で一発で洗い出す**。Amazon OOS%・New Offer Count・Buy Box % Amazon で絞る。Brand と Manufacturer は別項目 | なし |
| 19 | BT Slinger（BowTied Slinger） | ニュースレター運営（規模の記載なし） | **Pro ウェブの Product Finder**（明記） | 逆引き仕入れ。ランク・在庫状況・出品者数・"discontinued"等のテキスト検索で絞り、**卸のブランドを Finder に入れて勝ち筋商品を特定 → 営業担当にメールで特別発注を依頼** | なし |
| 20 | Gのすけ | **EC物販 年商1億円突破**（国内／輸入） | **Keepa 内のツール「Product Best Sellers」**（Pro） | Amazon 画面が100位までしか見えない制約を超えてランキングを見る／急上昇商品の検知 | なし |
| 21 | tremas-lab（Sara） | 二次情報サイト（実績の記載なし） | — | **API を払うべき人／払わなくていい人**の切り分けを明示（§4 で引用） | あり |

**この表から読める事実（N=21）**

- API 課金者 15件の内訳は、**ツール開発・配布 9件／SaaS・アドオン 4件／学術 1件／物販以外の価格ウォッチ 1件**。**「自分の仕入れ判断のためだけに API を払っている実践者」は0件**。
- 逆に、**月商・年商の数字を出している実践者（#18 7桁ドル・#20 年商1億）は全員ウェブ版 Pro**。
- **当社の型A（卸/メーカーのブランド名 → Amazon上の商品を洗い出す → 営業担当に連絡）そのものの手順が、#18・#19 で Pro ウェブの Product Finder として書かれている。** API 版ではない。

---

## 4. 用途の分類 — 実践者は本当に何に使っているか

| 用途 | API で実際にやっている人（§3 の#） | 主な担い手 | 社長の関心への答え |
|---|---|---|---|
| **(a) 仕入れ判断（利益商品を探す）** | #3（80ASIN/回のふるい分け）・#10（ブランド日次スコア・実績なし）・#12（卸価格表の一括判定・SaaS側） | **ほぼ SaaS 側**。個人は試作レベル | **社長の見立ては実践者の実態と一致します。** 「API で利益商品を探す」を自力でやっている実践者は #3 の副業試作しか見つかりませんでした。実績者は Pro ウェブか SaaS を買っています |
| **(b) 価格・在庫の監視** | #6（GPU 日次）・#7（差分検知つき MCP）・#12（SaaS）／公式 tracking API は webhook 通知あり | ツール側 | SKU が数十〜数百になってから効く用途。当社は現在 SKU ほぼ0 |
| **(c) 競合／セラー調査** | #1（SELLER LISTER＝セラーID収集）・#14（セラーIDからASIN一括） | 自作ツール勢 | Pro の Seller Lookup が同じことを画面でやる（CSV/Excel 出力可・「500商品でも1,000商品でも」） |
| **(d) メーカー／ブランドの発掘** | **API でこれをやっている実例は0件。** Pro ウェブでは #16〜#19 が全員やっている（#18「仕入れ先のブランドリストを貼って全商品を洗い出す」、#17「他セラーの出品商品からメーカーを逆引き」） | **Pro ウェブ** | **当社が API で 2,425社の母数を出したのは、実践者の型より一歩進んだ使い方**（brandStoreName 空欄での炙り出しは実例が見つからず＝当社独自）。ただし型Aの実践者はこれを Pro の画面でやって年商を作っている |
| **(e) 需要の裏取り（月100個以上売れているか）** | #14（30日販売数をシートへ） | Pro ウェブでも可 | **Keepa の monthly sold フィルタは Product Finder に実装済み**（Pro）。元データは Amazon 公表値で、**50個/月以上の商品にしか表示されない**（＝社長の「月100個以上」基準はそのまま使える） |
| **(f) その他** | #5 学術研究・#9 公式クライアント配布・#8 OSS 土台 | — | 当社に関係なし |

**tremas-lab（#21）が挙げる「API を払うべき人」**: 数千〜数万ASINを定期処理する／自動通知・分析システムを作る／カテゴリ全体を分析する／開発とDB運用を自分で続けられる。
**「払わなくていい人」**: 週末に副業でせどりをする個人／判断の速さを少し上げたいだけの人／プログラムの保守とエラー対応をやりたくない人／価格アラートが欲しいだけの人（Keepa 標準機能で足りる）。

---

## 5. 代替手段との比較

まず、当社が持っていない **Keepa Pro（€29）に何が付くか**を確定させます。当社は API €49 の1本だけで、**Pro の画面は1度も使っていません**（参照: `reference_keepa_billing_api_only.md`）。

| 機能 | 無料 | **Pro €29** | API €49（当社の現契約） |
|---|---|---|---|
| ランク／出品者数／評価の履歴グラフ | × | ○ | ○（JSON） |
| **Product Finder（条件で全DB検索）** | × | **○（画面。1検索でクオータ5%消費・1%/時 回復＝1日20〜24検索）** | ○（1クエリ約10トークン） |
| **Finder 結果の CSV/Excel 出力** | × | **○（全列 or ASINのみ。表示は1画面最大5,000件）** | ○（JSON） |
| **Product Viewer（ASIN/UPC を一括投入）** | × | **○（1回 最大10,000件、クオータ100%で1日 最大36,000件の入出力）** | ○（1件1トークン） |
| Seller Lookup（セラーの出品ASIN全件） | × | ○（CSV/Excel 出力可） | ○（/seller 1トークン） |
| Best Sellers（100位より深いランキング） | × | ○ | ○ |
| **API アクセス** | × | **○ ただし 1トークン/分**（＝月約4.3万トークン） | 20トークン/分（＝月約86万） |
| 価格の履歴グラフ | ○ | ○ | ○ |

> 出典: Keepa 公式スクリプト（購入画面の文言）＝当社 T-20260912-002/09、revenuegeeks（2026）、ひこーるラボ・ECセラーラボ（画面の実写解説）。**Pro の「1トークン/分」で全エンドポイントが使えるか（Finder を含むか）は未確認。**

### 用途ごとの代替可否

| 用途 | 解約したら何で代替するか | 代替できるか |
|---|---|---|
| (a) 仕入れ判断 | Pro の Product Finder（画面＋CSV）／Seller Assistant 等 SaaS（$13〜30/月）／Amazon 画面 | **できる**（実践者は全員これ） |
| (b) 価格・在庫の監視 | Pro のトラッキング＋メール通知／Amazon の画面／SKU が増えたら SaaS | **できる**（当社の SKU 数では画面で足りる） |
| (c) 競合・セラー調査 | Pro の Seller Lookup（CSV 出力可） | **できる** |
| (d) メーカー発掘（母数づくり） | Pro の Product Finder ＋ Product Viewer（1日1万ASIN投入・3.6万件出力） | **ほぼできる。ただし未確認点1つ** — ブランドストア名（`brandStoreName`）が Product Viewer の出力列にあるかを確認していない。無ければ「自社出品していないメーカー」の判定だけ手作業（ブランド名で Amazon 検索）になる |
| (e) 需要の裏取り | **Amazon の商品ページ「過去1か月に N点以上購入」（無料・一次情報）**／Pro の monthly sold フィルタ | **できる**（元データが同じ Amazon 公表値） |
| (f) 大量の履歴を自動で回す | **代替なし** | **できない。** 1回1万〜2万トークンの夜間スキャン（T-1 型）は、Pro の 1トークン/分では 7時間 → **約1週間**に伸びる |
| 出品当日のカート価格で利益再計算 | Amazon の商品ページを見る（1商品10秒） | できる（SKU 数個なら手作業で十分） |
| SP-API | 当社は規約同意前。Seller Assistant 等は SP-API と Keepa を併用している | 未着手（別論点） |

**代替できないのは「速度」だけです。** 取れるデータの種類ではなく、単位時間あたりの件数が 1/20 になります。

---

## 6. 当社での利用価値 — 型Aの工程を並べて判定

型A＝ネット販売に疎い国内中小メーカーへ大量に連絡し、独占／正規取引を取る。工程ごとに「API が無いと詰まるか」を判定します。

| # | 工程 | API の要否 | 根拠・代替 | 判定 |
|---|---|---|---|---|
| 1 | **連絡先メーカーの母数づくり** | **もう要らない** | 既に 2,425社（80%区間 1,896〜2,984）を抽出済み。**週70通なら35週＝約8ヶ月分**（T-20260914-006/01）。母数を使い切るまで再抽出は発生しない | **詰まらない** |
| 2 | 母数の「質」を上げる（電話番号・企業規模・HP・EC有無） | **要らない** | Keepa には電話番号・HP・EC有無のデータが無い。取得元は各社サイト・gBizINFO 等（S-B の担当範囲） | **詰まらない**（API と無関係） |
| 3 | 送信（メール／FAX／電話） | 要らない | — | 詰まらない |
| 4 | **見積りが来た後の「本当に売れているか」確認** | **要らない（画面で足りる）** | Amazon の商品ページの「過去1か月に N点以上購入」が一次情報で無料。50個/月未満は非表示＝社長の月100個基準はこれで判定できる。ランク履歴が見たいときは Pro | **詰まらない。ただし1件ずつ手で見る** |
| 5 | 出品当日のカート価格で利益を再計算 | 要らない | Amazon の画面（1商品10秒）。当社の SKU 数は現在ほぼ0〜10 | 詰まらない |
| 6 | **取引開始後の価格崩れ・競合参入の監視** | **要らない（今は）** | 扱う SKU が数個のうちは画面と Keepa の無料グラフで足りる。**SKU が数十を超えたら Pro か SaaS（Seller Assistant 月$13〜30）へ**。API を自分で回すのは実践者の型ではない | **詰まらない。SKU 増加時に再検討** |
| 7 | 打診先メーカーが Amazon に実在するか／自社出品しているかの検証 | あると速い | 現在 10トークン/社。代替は「ブランド名で Amazon 検索」（1社30秒）。952社なら約8時間の手作業 | **詰まる手前**。§7 の再契約トリガーに置く |
| 8 | 需要先行スキャン（T-1 型・Product Finder の大量抽出） | **API か Pro のどちらかが必要** | 無料版では Product Finder が使えない。Pro の画面（1検索1万件・CSV出力）でも可能だが、当社が組んだ自動処理はそのままでは動かない | **補給月にだけ必要** |

**判定**: 工程8つのうち **API が無いと止まるのは #8 の1つだけ**で、それは「毎月やる作業ではない」（前回実行は 2026-09、次は補給月）。#1 が今後8ヶ月不要である以上、**10月以降の型Aの進行は API 無しで回ります（推測・確度 高）**。

**逆に、事実として押さえておくべき不利な点**

- 当社が API で作った 2,425社の母数（brandStoreName 空欄での炙り出し）は、**実践者の誰もやっていない独自の手**です。これは「API のおかげで一歩先に出た」とも読めます（推測）。ただし母数はもう手元にあり、**使い切るのに8ヶ月**かかります。
- 取得済みデータは解約後も自社業務で使い続けられます（API T&C §11(2)・ハルオ判定 T-20260912-002/10）。**捨てることにはなりません。**

---

## 7. 結論

### 3択の比較

| 案 | 年コスト | 得るもの | 失うもの・リスク |
|---|---|---|---|
| ① 継続（€49×12） | **約10.4万円**（8,732円/月） | 20トークン/分の速度。いつでも夜間スキャンが打てる | 実践者が使っていない機能に月8,700円。使途は年1〜2回の抽出だけ |
| ② 解約して Pro €29 に移る | 約6.2万円（5,168円/月） | Product Finder・Product Viewer・Seller Lookup・Best Sellers の**画面**＋1トークン/分の API。**型A実践者（#16〜#20）と同じ道具立て** | 速度 1/20。Pro の契約は §4.1（金銭）で社長承認が必要。brandStoreName が出力列にあるか未確認 |
| **③ いったん解約し、必要な月だけ再契約（推奨）** | **年1回なら 約0.9万円／年3回で 約2.6万円** | 固定費をほぼ消す。補給月だけ 20トークン/分を取り戻す | 再契約は**新規契約**。復活不可・その時点の定価・**Keepa は理由を示さず申込を断れる（T&C §3(3)）**。年8回以上再契約すると Pro×12 より高くなる |

### 推奨: ③（10/3 までに解約）

1. 型Aの実践者は誰も API を使っておらず、当社の工程で API が無いと止まるのは「補給月の大量抽出」1つだけです（§6）。
2. その1つは**年1〜3回**で、必要になった月だけ €49 を払えば取り戻せます（年0.9〜2.6万円）。
3. 条件は2つ。**10/2 までに T-3・S-3 の抽出を終える**こと、**再契約を断られる可能性（低・回復不能）を撤退条件に織り込む**こと（ハルオ判定どおり）。

### 年間コストが12ヶ月黒字条件にどう効くか

**€49/月＝約8,700円/月の固定費削減。マサルの感度（固定費 月1,000円 ≒ 黒字確率 3.5pt）を当てると、①継続と③解約の差は月約8,000円＝約28pt**（線形近似の大幅な外挿なので、**数字そのものより「固定費の中で最大級の1本」という位置づけ**として読んでください。マサルの試算はもともと年1回＝728円/月を置き値にしており、③はその置き値どおり、①は置き値より約28pt 不利という関係です）。

---

## 8. 論点シート（ここから先は戦略判断＝タケシの領分）

事実は出し切りました。以下は**戦略判断**なので、サトルは踏み込みません。

| 論点 | 材料 |
|---|---|
| **Pro €29 を契約するか（②の後段）** | 型A実践者（EC STARs Lab.・FBA Mogul・年商1億のGのすけ）は全員 Pro。Product Finder は「必ず有料版」と原典が明記。一方で当社は Pro を1度も使っておらず、画面操作の学習コストは未計測。**金銭＝§4.1** |
| Seller Assistant（$13〜30/月）を Pro の代わりに検討するか | 卸の価格表を一括判定する Price List Analyzer は、型Aで見積りが来た後の判定にそのまま効く。14日無料トライアルあり（**申込＝§4.1**） |
| 補給月の再契約トリガーを何に置くか | 候補: 母数の残りが週70通換算で8週を割ったとき／新カテゴリに広げるとき／SKU が30を超えたとき |
| 10/2 までの抽出を実行するか（T-3・S-3） | 合計 約1.4万〜2.2万トークン・12〜18時間。9/20〜10/2 の12日で供給 約34.6万トークン（28,800/日）＝その6%以下 |

---

## 付録A. 出典（全件 2026-09-20 取得）

**Keepa 公式（一次）**
- API Documentation 索引（全13エンドポイント: product / search / query=Product Finder / deal / bestsellers / category / seller / sellerquery / topseller / lightningdeal / graphimage / tracking） https://keepa.com/api-docs/
- Plans & Tokens（解約は期間末まで有効・期間終了後は復活不可） https://keepa.com/api-docs/plans-tokens.html
- API T&C（Version of July 28, 2026。§3(3) 申込拒否・§11(2) 保存データの利用） https://keepa.com/cdn/termsAPI.txt
- 公式 Java / PHP フレームワーク https://github.com/keepacom/api_backend ・ https://github.com/keepacom/php_api

**API を実務で回している例**
- ツールドブッパン「[Keepa API⑥] セラーリスト自動生成ツール SELLER LISTER を公開」 https://tooledbuppan.com/keepa-api-6/ （**本文取得できず**＝サイトがニュースポータルへ転送。検索結果のスニペットと ①〜⑥ の記事タイトルのみ）
- amznlog「MWS APIキーの取得が困難になってきたのでkeepa APIも視野に入れてみる→実際に作ってみた」 https://amznlog.com/keepa-api
- TechTech Note「Amazon中国輸入 | KeepaAPIを使用して商品リサーチの一部をシステム化してみた」 https://techtech-note.com/1264/
- ZIDOOKA!「Keepa APIによるAmazon商品価格情報の取得と活用」 https://www.zidooka.com/archives/197
- Jürgensmeier & Skiera「Measuring Self-Preferencing on Digital Platforms」Journal of Marketing 2025 https://journals.sagepub.com/doi/full/10.1177/00222429251360772 ／「Opportunities for self-preferencing in international online marketplaces」IMR 41(5) https://www.emerald.com/imr/article/41/5/1118/1224020/Opportunities-for-self-preferencing-in ／R パッケージ https://github.com/lukas-jue/keepar
- United-Compute/gpu-price-tracker https://github.com/United-Compute/gpu-price-tracker
- BWB03/keepa-adapter（MCP サーバ・33ツール） https://github.com/BWB03/keepa-adapter
- akaszynski/keepa（Python クライアント・315 stars） https://github.com/akaszynski/keepa ／ドキュメント https://keepaapi.readthedocs.io/en/latest/
- ntwholesales/fbaautomation（ブランドリスト日次スキャン・**AI生成コード**） https://github.com/ntwholesales/fbaautomation
- GitHub コード検索 `api.keepa.com` = 560件（`gh api search/code`・2026-09-20 実測）

**API を製品に組み込んでいる事業者**
- Seller Assistant「Seller Assistant API」（Keepa API と SP-API を統合） https://www.sellerassistant.app/blog/seller-assistant-api/ ／Keepa エンドポイント https://developer.sellerassistant.app/keepa/get-product ・ https://developer.sellerassistant.app/api-21568126 ／料金 https://revenuegeeks.com/software/seller-assistant-app
- Databar.ai https://databar.ai/explore/keepa-api
- Keepa API Connector（Google Workspace Marketplace） https://workspace.google.com/marketplace/app/keepa_api_connector/366094842816

**API を使っていない実践者（Pro ウェブ）**
- EC STARs Lab.（中西恒太）「【有料級】Keepaの使い方徹底解説」 https://ecstarslab.com/blog/keepa-keezon/
- ECセラーラボ「メーカー仕入れにおける利益商品のリサーチ方法」 https://ec-seller-labo.co.jp/article/maker-purchase-research/ ／「Product Finderの使い方完全マニュアル」 https://ec-seller-labo.co.jp/article/keepa-product-finder/
- FBA Mogul（Simon Knight・7 Figure Seller）「Keepa Product Finder: Every Filter Explained (2026)」 https://fbamogul.com/keepa-product-finder-getting-started-guide/
- BowTied Slinger「Reverse Sourcing With Keepa Product Finder」 https://www.bowtiedslinger.com/p/reverse-sourcing-with-keepa-product
- Gのすけ（EC物販 年商1億突破）「Keepa内ツールの活用」 https://note.com/g_nosuke/n/n7bf7a9371b38
- ひこーるラボ「Keepa Product Finder の使い方」 https://hikomhikom.com/keepa-premium-data-access/ ／「Keepa Seller Lookup とは？」 https://hikomhikom.com/keepa-seller-lookup/
- tremas-lab「Keepa APIは必要？迷ったら読む判断ガイド」 https://www.tremas-lab.com/keepa-api-handan/
- revenuegeeks「Keepa Pricing 2026: Free vs €29 Pro」 https://revenuegeeks.com/software/keepa/pricing ／「Keepa API: Pricing, Tokens & Real Costs」 https://revenuegeeks.com/software/keepa/api

**社内（前提として参照）**
- T-20260912-002/08 Keepa 依存の棚卸し・09 Keepa 再契約の可否・10 Keepa 解約後のデータ利用
- T-20260914-006/01 型A の送信先の母数（2,425社）
- memory: `reference_keepa_billing_api_only.md`・`knowledge_maker_extraction_keepa.md`・`knowledge_keepa_dropcount_is_polling.md`・`reference_keepa_api_capabilities.md`

## 付録B. 取得できなかったページ・調査の限界

| 対象 | 状況 |
|---|---|
| tooledbuppan.com（Keepa API ①〜⑥ 全記事） | **取得できず。** 独自ドメインが海外ニュースポータルへ転送される状態で、curl・WebFetch・r.jina.ai いずれも本文を返さない。Wayback も 429。**検索スニペットのみを根拠にしており、確度は中** |
| Basil Latif（Medium・10,000ASIN を Keepa API で引いた記事×2本） | **取得できず**（Cloudflare 403）。検索スニペットから「1万ASIN超のオファー履歴取得に10時間以上」「オファー履歴はトークンを多く食う」を採ったが**確度 中** |
| The Olson Report「What Keepa's New Monthly Sold Filters Are Really For」 | **取得できず**（$9/月の paywall。§4.1 で課金せず） |
| Reddit r/FulfillmentByAmazon の生の声 | 検索で該当スレッドに到達できず。**未調査** |
| Keepa Pro の画面そのもの | **未契約のため未検証。** Pro の機能・クオータ・出力列は公式スクリプトの文言と第三者の画面解説に依存（brandStoreName の出力可否は未確認） |
| 型A実践者の API 利用の「不在証明」 | 「言及が無い」ことの確認であり、**非公開で使っている可能性は否定できない**（推測・不在証明の限界） |


