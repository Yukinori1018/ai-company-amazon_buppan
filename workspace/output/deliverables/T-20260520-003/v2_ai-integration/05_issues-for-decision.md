# 05. 論点シート（A/B/C の素材、戦略提言ではなく問いの提示）

## このシートの位置づけ

**サトル（リサーチャー）は戦略提言をしない**。本シートは、タケシ（プランナー）が A/B/C の戦略案を立てるための**事実ベースの素材**と**未解決の問い**を提示するもの。

カズヨ仮説 A（「Sato-Scope を中核に据え、外部ツールはデータ源と目視確認に絞る」）を**支持する事実／反証する事実／未解決の問い**を整理する。

> ## ⚠️ 2026-05-25 訂正（社長指摘を受けて）
>
> 本シートは ERESA AI を「Sato-Scope の代替候補」のニュアンスで扱っていた（特に R3、後述の案 C）。
> **これは誤り**。社長指摘により、両者は**別レイヤーの補完関係**と確認された：
> - **Sato-Scope** = 仕入れ発見レイヤー（楽天/Yahoo! ⇄ Amazon の価格差。「どこから仕入れるか」）
> - **ERESA AI** = Amazon 内 分析・出品支援レイヤー（ランキング/履歴/キーワード/AI 文章・画像生成。「Amazon 内でどう戦うか」）
>
> 両者は**答える問いが違い、機能が重ならない**。よって「ERESA があるから Sato-Scope 不要」論は取り下げる。
> Sato-Scope は仕入れ発見を担う**唯一の自社資産**で ERESA に置換不可。R3 と下記 A/B/C の「案 C」は
> この前提で読み替えること。**ただし R1（軸B 0周問題）は本訂正後も有効**。

## 1. 仮説 A を支持する事実

| # | 事実 | 出典 |
|---|---|---|
| S1 | **SP-API 自社利用は2026年以降も無料継続**。第三者開発のみ年 $1,400 USD 課金 | Amazon 公式発表 2025-11-03、PPC.land |
| S2 | Keepa / SellerSprite は API 公開済み。Sato-Scope に直接データ流入可能 | Keepa API ドキュメント、SellerSprite API ドキュメント |
| S3 | Amazon SP-API の Product Fees API で **FBA計算機相当の機能が完全自動化可能** | SP-API Product Fees API ドキュメント |
| S4 | **海外 AI ツール（AMZScout、ZonGuru、DataDive 等）は JP マーケット精度が△**で、JP セラーには相対的に弱い | 各ツール公式レビュー |
| S5 | **AI が勝手に商品説明を盛る事故**が報道済（Bloomberg 2026/1）。SaaS の AI 出力をそのまま使うとリスク。**Sato-Scope では人間検品工程を強制設計できる** | Bloomberg、note 業界記事 |
| S6 | 多くの SaaS の内部 LLM が非開示。**LLM プロバイダを社長自身が選べる**のは Sato-Scope の優位点 | 各 SaaS の公式情報（ZonGuru が GPT-4 採用を明言する以外、非開示が多い）|
| S7 | データ可搬性。Sato-Scope なら撤退時のロックインが小さい | 自明 |

## 2. 仮説 A を反証する／弱める事実

| # | 事実 | 出典 |
|---|---|---|
| R1 | **社長は副業初心者、軸B 0周（経験ゼロ）**。Sato-Scope を中核に据えても、**「グラフを読む経験値」「商品判断の勘所」がないとデータは活きない** | 社長プロファイル、v1 個票（Keepa の項）|
| R2 | **海外 AI 内蔵ツールは即日利用可能**で、開発工数ゼロ。Helium 10 / Jungle Scout は学習リソース（YouTube・公式チュートリアル）が日本語含めて潤沢 | 各ツール公式 |
| R3 | **ERESA AI（国内特化、ChatGPT 連携）が ¥5,980/月で利用可**。JP マーケット精度◎、対話 UI、AI 画像生成も含む。**Sato-Scope を作らなくても近い機能が買える** | ERESA AI 公式、コマースピック |
| R4 | **アマサーチに公式 API がない**ため、店舗せどりの即時判断は SaaS / 拡張機能に依存せざるを得ない | アマサーチ公式、WebSearch 範囲 |
| R5 | **Helium 10 / SellerSprite の独自データ**（逆引き ASIN、PPC 推定）は内部アルゴリズム依存。**Sato-Scope で完全に再現するには独自データ収集が必要**で、現実的でない | SellerSprite、Helium 10 各公式 |
| R6 | **Sato-Scope は Phase 1 完了済み**だが、SaaS の機能網羅性に追いつくには Phase 2〜N で相当の開発工数が見込まれる（具体的工数は IT エンジニア（コウタロウ）案件）| Sato-Scope 開発計画 |
| R7 | **PickFu（実消費者パネル）の代替は Sato-Scope では作れない**（人間パネルが核）。これは外部依存が継続する | PickFu 公式 |

## 3. 未解決の問い（A/B/C 素材）

### 問い1：「Sato-Scope の射程」をどこまで広げるか

| 案 | 概要 | コスト感（推測） | 効率優位フェーズ | 差別化優位フェーズ |
|---|---|---|---|---|
| **A（仮説のまま）** | Sato-Scope 中核。SaaS はデータ源（Keepa API、SellerSprite API、SP-API）と目視（アマサーチ）に絞る | 開発工数：高、運用月額：低（Keepa €19＋SellerSprite API＋LLM API 数千円）| 軸B 10周以降 | 全フェーズ |
| **B（折衷）** | Sato-Scope は SP-API データ統合とダッシュボードに専念。リスティング生成・画像生成・PPC は SaaS（Helium 10 or ERESA AI）に外注 | 開発工数：中、運用月額：中（Helium 10 $129 or ERESA AI ¥5,980 ＋ Keepa €19）| 軸B 1〜10周 | 軸B 5周以降 |
| **C（外部 AI フル活用）** | ERESA AI ＋ Keepa ＋ FBA計算機（公式 GUI）。Sato-Scope は数字集計と撤退判断補助に限定 | 開発工数：低、運用月額：中〜高（ERESA AI ¥5,980 ＋ Keepa €19 ＋ アマサーチ ¥1,980 等）| 軸B 0〜3周 | 弱い |

### 問い2：「人間検品工程」をどう実装するか（全案共通）

事実：**AI 出力責任は出品者**（景品表示法・特商法）。

- A 案では Sato-Scope に「公開前承認」ワークフローを組み込む必要あり
- B/C 案では SaaS の AI 出力を必ず人間が見るフローを運用ルールで担保
- **どの案でも「公開前の人間チェック」は外せない** → これは制約条件であり論点ではない

### 問い3：「軸B 0周問題」をどう解くか

事実：社長は軸B 0周（経験ゼロ）。タケシ／マサルの仮想 PDCA で扱うべき論点：
- 「Sato-Scope を作る前に軸B 1周を回すべきか？」
- 「Sato-Scope の Phase 2 開発と軸B 1周は並行可能か？」
- 「ERESA AI 7日無料 → 30日 → 解約、をまず試して『AI 内蔵ツールの実感』を得るのが先か？」

### 問い4：「中国企業ツール（SellerSprite）の Yes/No」

事実：SellerSprite は中国企業（杭州）運営。データ取扱・経済安全保障法整合性は法務案件。

- **法務（ハルオ）に発注してから採用判断する**プロセスを通すべき
- 代替候補：Helium 10 Cerebro AI（US 企業、ただし JP データはやや劣る）

### 問い5：「リプライサー（価格自動改定）」を Sato-Scope に組み込むか

事実：価格暴落リスクが高い領域。
- 既存 SaaS（Sellery、BQool、価格.com Plus 等）が成熟している
- 自社開発の場合、テスト不足が暴落事故につながる
- **Phase 3 以降の論点**として保留が現実的

## 4. タケシ（プランナー）への引き継ぎ事項

| カテゴリ | 引き継ぎ内容 |
|---|---|
| **戦略案の起点** | 上記 A/B/C を出発点にしてよい。ただし「ハイブリッド」「フェーズ移行型」も含めて検討推奨 |
| **必ず触れてほしい論点** | 問い3（軸B 0周問題）、問い5（リプライサー） |
| **撤退条件の起点** | 「Sato-Scope Phase 2 開発が N ヶ月遅延したら C 案にフォールバック」「軸B 1周で月商 X 円に届かなければ全案再評価」等の数字は事実から導けない（経営判断）|
| **マサルへのバトン** | A/B/C それぞれのプレモーテム（最悪3シナリオ）を依頼。特に A 案の「Sato-Scope 開発失敗 → 機会損失」シナリオ |

## 5. 法務（ハルオ）への引き継ぎ事項

| 案件 | 内容 |
|---|---|
| **SellerSprite** | 中国企業データ取扱の Yes/No 判断 |
| **Keepa API** | 商用利用条項の最終確認（Sato-Scope は社長個人ツール扱いだが念のため）|
| **Amazon SP-API** | 自社利用条件（「他セラーへのデータ提供禁止」線引き）|
| **AI 出力責任** | 景品表示法・特商法上、AI 生成リスティングを公開する際の出品者責任の整理 |

## 6. IT エンジニア（コウタロウ）への引き継ぎ事項

| 案件 | 内容 |
|---|---|
| **Phase 2 設計** | A 案採用時の Sato-Scope 拡張範囲とマイルストーン |
| **API 連携工数見積** | Keepa API、SellerSprite API、SP-API の連携工数（人日）|
| **人間検品ワークフロー** | 「AI ドラフト → 人間承認 → 公開」を強制する UI 設計 |
| **LLM プロバイダ選定** | OpenAI / Claude / Gemini どれを使うか（コスト・品質・規約）|

## 出典

| ソース | URL | 取得日 |
|---|---|---|
| Amazon SP-API 有料化発表 | https://developer.amazonservices.com/spp-announcement-ja-jp | 2026-05-22 |
| PPC.land「SP-API 有料化 2026」 | https://ppc.land/amazon-introduces-fees-for-third-party-developer-api-access-in-2026/ | 2026-05-22 |
| Bloomberg「AI で商品無断掲載」 | https://www.bloomberg.com/jp/news/articles/2026-01-07/T8GPJWT96OSS00 | 2026-05-22 |
| ERESA AI 公式 | https://eresa.io/ | 2026-05-22 |
| Helium 10 公式 Pricing | https://www.helium10.com/blog/pricing-membership-plan-options-how-they-work/ | 2026-05-22 |
| SellerSprite API ドキュメント | https://sellersprite.github.io/ | 2026-05-22 |
| Keepa API ドキュメント | https://keepaapi.readthedocs.io/en/latest/api_methods.html | 2026-05-22 |
| Amazon SP-API Product Fees | https://developer-docs.amazon.com/sp-api/docs/product-fees-api | 2026-05-22 |
| Nova Data「SP-API 自社利用継続無料」 | https://novadata.io/resources/news/amazon-sp-api-subscription-fees-2026 | 2026-05-22 |

— サトル（リサーチャー）／取得日 2026-05-22
