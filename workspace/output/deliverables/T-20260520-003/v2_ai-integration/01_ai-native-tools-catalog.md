# 01. AI 内蔵ツール網羅カタログ

## イシュー

「AI を内蔵していると標榜するツール群のうち、Amazon物販で**実用的に AI が機能**しているのはどれか。**AI と銘打っているが実態が薄いもの**はどれか。」

## スコープ

- 海外10本＋国内3本＋公式 1本＝**計13本＋実態薄い枠**
- 既存4本（Keepa / SellerSprite / アマサーチ / FBA計算機）の AI 連携性は [02_existing-4-tools-ai-integration.md](02_existing-4-tools-ai-integration.md) で扱う

## 評価軸

| 軸 | 内容 |
|---|---|
| **AI 機能の中身** | 「LLM ベース／独自モデル／単なる統計」のどれか |
| **JP マーケット対応** | amazon.co.jp で実用に耐えるか |
| **API / Export** | Sato-Scope に組み込めるデータ出口があるか |
| **料金** | 月額（為替は €1≒¥165、$1≒¥152 で換算）|
| **AI 実態評価** | サトル判定：◎濃／〇有／△薄／✕装飾的 |

## 1. 海外 AI ネイティブツール（10本）

### 1-1. AI 機能が実装の中核に組み込まれた本格派

| # | ツール | AI 機能 | 内蔵 LLM | 月額（2026） | API/Export | JP対応 | AI実態 |
|---|---|---|---|---|---|---|---|
| 1 | **Helium 10** | Listing Builder AI（タイトル/箇条書き/説明/裏側キーワード一括生成）、Cerebro AI（逆引きキーワード分析）、AI 画像生成、PPC AI | 非開示（複数 LLM 想定） | Platinum $129/月（年払 $99）、Diamond $359/月 | API は **Enterprise プランのみ**（個人不可）。CSVエクスポート可 | 〇（一部 JP データ） | ◎ |
| 2 | **Jungle Scout** | AI Assist（Review Analysis / Listing Builder / Profits Overview）。使用回数制限あり（Growth 100/月、Brand Owner 500/月） | 非開示 | Starter $49/月、Growth $588/年、Brand Owner+CI $1,548/年 | CSV エクスポート可。API は Cobalt（エンタープライズ）のみ | 〇 | ◎ |
| 3 | **AMZScout** | AI Listing Builder、AI Review Analyzer、PRO AI Extension、AI チャットボット | 非開示 | AI Bundle $59.99/月、$399.99/年 | CSV エクスポート可。公開 API なし | △（US 中心、JP は限定）| 〇 |
| 4 | **ZonGuru** | Listing Optimizer 4.0（**GPT-4 公式採用を明言**）、Love-Hate AI（レビュー感情分析） | **ChatGPT (GPT-4)** | Researcher $29/月、Seller $79〜$159/月（SKU数で段階）| CSV エクスポート可 | △（US 中心）| ◎ |
| 5 | **DataDive** | AI Copywriter、AI Listing Builder、AI Product Brief、Rank Radar、PPC Campaign Builder AI | 非開示 | Starter $39/月、Standard $149/月、Enterprise $490/月 | CSV エクスポート、API は要相談 | △（US 中心）| ◎ |

### 1-2. 単機能特化型 AI ツール

| # | ツール | AI 機能 | 月額（2026） | API/Export | JP対応 | AI実態 |
|---|---|---|---|---|---|---|
| 6 | **Sellesta.ai** | AI キーワードリサーチ、Listing 自動生成、競合分析、PPC 管理 | Free（1リスティング/月）、Basic $5/月（20件）、Pro $39/月（500件）| 公開 API はサイト上未確認 | 〇（マルチマーケット対応）| ◎ |
| 7 | **PickFu** | AI ＋ 実消費者パネルの A/B テスト。画像／タイトル／箇条書きを実購買層に投票 | Pay-as-go $15/poll〜、Pro $79/月、Team $299/月 | API あり（一部プラン）| 〇（パネルは US 中心、JP 限定）| 〇（AIだけでなく実人間パネルが核）|
| 8 | **Photoroom** | AI 商品写真生成・背景除去・Amazon サイズ自動リサイズ・シーン合成 | Free、Pro $9.99/月、Business、API プランあり | **API 公開**（Sato-Scope 連携容易）| 〇（言語非依存）| ◎ |
| 9 | **Seller Assistant App（参考）** | AI 仕入れ判断アシスタント。Keepa グラフ自動解釈 | $25〜$45/月 | API ベータあり | 〇（マルチマーケット）| 〇 |

### 1-3. Amazon 公式（特別枠）

| # | ツール | AI 機能 | 料金 | API/Export | JP対応 | AI実態 |
|---|---|---|---|---|---|---|
| 10 | **Amazon Generative AI for Listings（Enhance My Listing 等）** | 出品者向け公式 AI。商品説明・タイトル・箇条書きの生成と改善提案。**Brand Analytics の AI Buyer Behavior Insights**（Persona-Based Architecture / Shopping-Signal Enhanced Attribution / Repeat Purchase / Demographics） | **無料**（セラーセントラル組込）| **SP-API 経由でデータ取得可**（Brand Analytics は SP-API レポート提供）| ◎ | ◎ |

## 2. 国内 AI 物販ツール（3本）

| # | ツール | AI 機能 | 月額（税込）| API/Export | JP対応 | AI実態 |
|---|---|---|---|---|---|---|
| 11 | **ERESA AI** | 対話型 UI（ChatGPT 風）、リサーチ・分析・AI 画像生成（最短3分で9枚）、Kindle 書籍分析、AI ライティング | 基本 ¥5,980/月、Pro+ ¥9,800/月（7日無料）| Chrome 拡張中心、API は限定的、アマサーチと連携可 | ◎ | ◎ |
| 12 | **せど楽チェッカー** | ChatGPT を組込み、キーワード/ジャンル指定で楽天大量商品から Amazon ASIN を自動特定 | ¥3,000/月（30日無料）| 限定的、CSV エクスポート | ◎ | 〇 |
| 13 | **DELTA tracer（参考：AI非搭載だが国内主要）** | 価格・在庫・ランキング履歴、Keepa 提携データ。**AI 機能は現時点なし** | ¥2,200/月（2週間無料）| Chrome 拡張、限定的 | ◎ | ✕（AI未搭載） |

## 3. 「AI と銘打っているが実態が薄い」枠

WebSearch ベースで以下の傾向を確認。**「AI」を冠していても中身が単なる統計フィルタ／テンプレート文字列置換に留まるもの**が一定数存在。

| 傾向 | 具体例の類型 | サトル所見 |
|---|---|---|
| **AI＝GPT 単純呼び出し** | 個人/コーチが販売する「AI せどりプロンプト集」「ChatGPT で商品リサーチする教材」 | プロンプトの質に大きく依存。ツール本体の価値は限定的。**Sato-Scope に同等プロンプトを組み込む方が再現性が高い** |
| **AI＝検索フィルタ自動化** | 「AI が売れ筋を判定」と謳う一部の国内せどりツール | 実態は単純な閾値フィルタ。**「AI」は装飾的** |
| **AI＝レビューサマリ単発呼び出し** | 一部ツールの「AI レビュー要約」 | LLM コール1回。**Sato-Scope で同等機能を内製可能**（OpenAI/Claude API 直叩き）|

## 4. 重要な所見（事実のみ）

### 4-1. 海外 AI ツールの JP マーケット対応の濃淡

- **JP 実用度◎**: Helium 10、Jungle Scout、SellerSprite、Photoroom、PickFu（パネル US 中心）
- **JP 実用度△**: AMZScout、ZonGuru、DataDive ─ いずれも UI / データが US 偏重。**「AI 内蔵」でも JP データの精度が劣ると AI 出力の質も劣る**

### 4-2. API / データ出口の差

- **API 公開（Sato-Scope 組込容易）**: Photoroom、Keepa（既存）、SellerSprite（既存）、Amazon SP-API
- **エクスポートのみ**: Helium 10（個人プラン）、Jungle Scout、AMZScout、ZonGuru、DataDive、Sellesta、ERESA、せど楽
- **API なし／拡張機能のみ**: アマサーチ、DELTA tracer

### 4-3. 内蔵 LLM の透明性

**ZonGuru が GPT-4 採用を公式明言**している点は珍しい。多くのツールは内部 LLM 非開示。「AI」の中身が分からないと、出力品質の予測が立たない。

## 出典

| ソース | URL | 取得日 |
|---|---|---|
| Helium 10 公式ブログ「Pricing & Membership 2026」 | https://www.helium10.com/blog/pricing-membership-plan-options-how-they-work/ | 2026-05-22 |
| RevenueGeeks「Helium 10 AI Tools 2026」 | https://revenuegeeks.com/helium10-ai-tools/ | 2026-05-22 |
| Jungle Scout 公式・G2 比較 | https://www.g2.com/products/jungle-scout/pricing | 2026-05-22 |
| RevenueGeeks「Jungle Scout AI Assist 2026」 | https://revenuegeeks.com/jungle-scout-ai-assist/ | 2026-05-22 |
| AMZScout 公式 PRO AI | https://amzscout.net/pro-ai/ | 2026-05-22 |
| RevenueGeeks「AMZScout Pricing 2026」 | https://revenuegeeks.com/amzscout-pricing/ | 2026-05-22 |
| ZonGuru 公式 Listing Optimizer 4.0 | https://www.zonguru.com/get/listing-optimizer | 2026-05-22 |
| RevenueGeeks「ZonGuru Pricing 2026」 | https://revenuegeeks.com/zonguru-pricing/ | 2026-05-22 |
| Sellesta.ai 各種レビュー | https://www.saasworthy.com/product/sellesta-ai | 2026-05-22 |
| Data Dive 公式 Pricing | https://datadive.tools/pricing/ | 2026-05-22 |
| PickFu 公式 Amazon | https://www.pickfu.com/industries/amazon | 2026-05-22 |
| Photoroom 公式 Amazon AI | https://www.photoroom.com/ai-product-photography/amazon | 2026-05-22 |
| ERESA AI 公式 | https://eresa.co.jp/column/eresa-ai-amazon-research-tool-guide/ | 2026-05-22 |
| ERESA AI プレスリリース | https://prtimes.jp/main/html/rd/p/000000003.000118686.html | 2026-05-22 |
| せど楽チェッカー公式 | https://sedoraku.com/checker.html | 2026-05-22 |
| DELTA tracer 公式 | https://utilly.jp/service/delta-tracer/ | 2026-05-22 |
| Amazon Brand Analytics 2026 機能 | https://www.zonguru.com/blog/amazon-brand-analytics | 2026-05-22 |
| Amazon 公式：商品ページ生成 AI | https://www.aboutamazon.jp/news/smb/generative-ai-to-create-product-description-for-listings | 2026-05-22 |
| Bloomberg「AIで商品を無断掲載」 | https://www.bloomberg.com/jp/news/articles/2026-01-07/T8GPJWT96OSS00 | 2026-05-22 |

> 公式サイト直 fetch は HTTP 403 が頻発したため、料金・機能は WebSearch のスニペットおよび二次情報ソースを複数突合して採用。最終的な導入判断時には公式サイトで再確認してください。
