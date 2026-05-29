# 07. Jungle Scout（ジャングルスカウト）

## 一行説明

Amazon セラー向け**オールインワン型リサーチ＆運用ツール**の老舗。Helium 10 と並ぶ世界二大ブランドの一角で、UI のシンプルさ・初心者向けチュートリアルの厚さ・サプライヤー DB が特徴。Greg Mercer 創業（2014）、現在は米国 Greenwood Capital 傘下。

## 開発元・所在

- 開発：Jungle Scout LLC（米国 Austin, TX）
- 公式：https://www.junglescout.com/
- 日本語サイト：https://www.junglescout.com/ja/（UI 一部日本語化、サポートは英語チャット主体）
- ビジネスモデル：サブスクリプション（Basic / Suite / Professional）+ アドオン（Cobalt 大手ブランド向け）
- データ源：自社クロール+Amazon 公開データ+SP-API 連携

## 用途（Amazon物販のどこで使うか）

- **市場リサーチ**：Product Database / Opportunity Finder で月販売数・売上・競合数から商品アイデアを探索
- **キーワードリサーチ**：Keyword Scout（競合 ASIN 逆引き、関連 KW、PPC 入札推定）
- **サプライヤー探索**：Supplier Database（Alibaba/Global Sources のサプライヤー網を商品 ASIN から逆引き）★ JS 独自の強み
- **販売トラッキング**：Sales Analytics で日次売上・FBA 手数料・PPC 費を統合管理
- **在庫管理**：Inventory Manager（補充タイミング AI 推定）
- **レビュー収集**：Review Automation（Amazon Buyer-Seller Messaging 経由）
- **出品最適化**：Listing Builder + AI Assist（GPT 連携で見出し・箇条書き生成）
- **ランキング監視**：Rank Tracker（指定 KW での自社/競合順位推移）

## できること（主要機能）

| モジュール | 説明 |
|---|---|
| **Product Database** | カテゴリ・売上・レビュー数等の閾値で全 ASIN を絞り込み |
| **Opportunity Finder** | KW 起点で「需要 vs 競合」マップから穴場を提示 |
| **Extension (Chrome)** | Amazon 商品ページに月販売数・売上・FBA手数料・利益率を重畳 |
| **Keyword Scout** | 競合 ASIN を入れるとその商品が獲得している KW を逆引き |
| **Supplier Database** ★ | ASIN から逆引きでサプライヤー（中国系主） |
| **Listing Builder + AI** | KW スコア＋ AI 文章生成（GPT-4 連携） |
| **Sales Analytics** | 売上・粗利・PPC・返品の統合 P/L |
| **Inventory Manager** | 補充タイミングを過去販売実績から AI 推定 |
| **Rank Tracker** | KW × ASIN の検索順位推移を時系列で監視 |
| **Review Automation** | 規約準拠のレビュー依頼メール自動送信（JP は要確認） |
| **Academy** | 動画講座・コミュニティ（Suite 以上に同梱） |

## 料金プラン（2026年5月時点）

| プラン | 月額 | 年払い | 特徴 |
|---|---|---|---|
| **Basic** | $49/月 | $29/月（$349/年） | 1ユーザー、Extension+主要リサーチ機能の入門枠 |
| **Suite** ★ | $69/月 | $49/月（$589/年） | **個人セラー標準**。全モジュール解放、AI Assist、Rank Tracker、Supplier DB |
| **Professional** | $129/月 | $84/月（$999/年） | マルチアカウント、API 利用、6名まで |
| Cobalt | 要見積 | — | 大手ブランド・代理店向け（年額数百万円） |

**為替前提（1ドル=¥155 換算）**：Suite 年払いは月 ¥7,595 / 単月 ¥10,695 程度。Helium 10 Platinum より約 35% 安い。

**返金保証**：**7日間返金保証**あり（Helium 10 の 30日返金保証より短い）。

## 無料代替

- **無料版なし**（Helium 10 の Free プランのような恒久無料枠は存在しない）
- 7日返金保証を実質トライアルとして使う運用が事実上の無料試用
- 国内特化なら **Keepa + アマサーチ + FBA 計算機** の組み合わせの方が初期コスト ¥0

## 国内Amazon（amazon.co.jp）対応

- **対応：◯（部分対応）** — JP ストアの ASIN 入力可、Extension も JP で動作
- **日本語UI**：あり（主要画面は翻訳済）。ただし Academy・ヘルプ・ウェビナーは英語
- **JP データの精度**：販売数推定は US と比べると粗い（カテゴリ係数の最適化が US 中心）
- **Supplier DB**：中国サプライヤー網の検索は JP セラーにとっても価値あり（OEM/輸入志向時）
- **Review Automation**：JP の Amazon コミュニケーションガイドライン抵触リスク高 → **JP では使用非推奨**

## 学習コスト目安

- **Extension の基本操作**：1〜2時間（Keepa とほぼ同等）
- **Product Database / Opportunity Finder**：1日〜（フィルタ設計を理解する必要）
- **Keyword Scout の活用**：2〜3時間
- **Supplier Database 活用（OEM 志向時）**：1日〜
- **全機能フル活用**：1〜2ヶ月（Helium 10 より UI シンプルでやや軽い）

## AI 連携性（v2 観点での追加評価 ★最重要）

- **公式 API：あり（Professional プラン以上）** — Suite では API 利用不可、要 Pro 昇格
- **AI ネイティブ機能**：
  - **AI Assist for Listing Builder**：GPT-4 連携で商品説明・箇条書き・タイトルを KW スコア付き生成
  - **Opportunity Finder の需要スコア**：機械学習ベース（詳細非公開）
  - **Inventory Manager の補充予測**：時系列 AI
- **Sato-Scope への統合可能性**：◯（Pro プラン必須）
  - Suite では API 提供なし → Sato-Scope に組み込むなら Pro ¥10k+/月コース
  - Helium 10（Platinum で API 利用可）に比べ **API 解放のハードルが1段高い**
- v2 カタログでは「**AI ネイティブ × API 公開（Pro 以上） × オールインワン**」だが、**API 解放の階段の重さが Helium 10 より不利**

## 法務・運用上の留意点（ハルオ向け）

- **米国企業との契約**：利用規約は英語版が正本。準拠法は米国テキサス州法
- **データ取得元**：自社クロール部分は Amazon TOS とのグレーゾーン（Keepa・Helium 10 同様の論点）
- **Supplier Database**：表示されるサプライヤー情報は参考値。実際の取引は Jungle Scout 経由ではなく直接交渉となるため、契約・品質保証は自己責任
- **Review Automation（JP）**：特定電子メール法・Amazon コミュニケーションガイドライン抵触リスク高 → **JP では原則使用しない**
- **解約・返金**：7日返金保証あり。年払い解約は月割り返金なし

## カズヨ所見

**「Helium 10 のシンプル版＋サプライヤー DB という強み」**。JP 物販に対しては Helium 10 と同様**過剰投資寄り**だが、用途次第で選好が分かれる：

- **JP セラー単独運用**：Suite ¥7,595/月（年払い）は決して安くなく、Keepa+DELTA tracer+Sato-Scope の方が JP 最適化＋低コスト
- **OEM / 輸入志向**：Supplier Database の独自性は大きい。中国 OEM を視野に入れるなら Jungle Scout に分がある
- **AI 連携前提（仮説A）**：API が Pro 階段（Suite 不可）なため、Sato-Scope の中核データ源候補としては **Helium 10 / Keepa に劣後**
- **初心者教育コンテンツ**：Academy・公式コミュニティの英語圏での評価は高く、学習目的なら選好の余地あり

**タケシ用バトン**：
- 「軸B 即併走候補」としては**当面見送り**（学習コスト・JP特化度・API 階段で不利）
- 「中核ツール候補」としては**OEM 志向に転換した場合のみ再評価**（Supplier DB が刺さる）
- 撤退条件：「導入 3 ヶ月で Opportunity Finder か Supplier Database のどちらかでも実運用に乗らなければ即解約」

## 出典・参考

- 公式：https://www.junglescout.com/
- 日本語ページ：https://www.junglescout.com/ja/
- 料金：https://www.junglescout.com/pricing/
- 機能一覧：https://www.junglescout.com/features/

> 料金・機能は **2026年5月時点の公式記載情報**ベース。為替・プラン名は変動が大きいため導入時に再確認。Greg Mercer 創業以降に Greenwood Capital が買収（2021）し、その後プラン体系の改訂が複数回入っているため、契約直前の再確認推奨。
