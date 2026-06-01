# 02. 既存4本の AI 連携可否（API / Export / Webhook / 規約）

## イシュー

「v1 で評価した既存4本（Keepa / SellerSprite / アマサーチ / FBA計算機）を **Sato-Scope（FastAPI バックエンド）**に組み込めるか。技術的可否と規約上の制約は何か。」

## 結論（事実ベース）

| ツール | API 公開 | データエクスポート | Webhook | Sato-Scope 組込可否 | 規約上の制約 |
|---|---|---|---|---|---|
| **Keepa** | **◎ 公開済（Token 制）** | CSV あり | 一部アラート機能あり（Email/Telegram/RSS）| **◎ 容易** | 商用利用可。Terms あり。Sato-Scope は社長個人ツールなので問題なし |
| **SellerSprite** | **◎ 公開済（要問い合わせ・7日無料試用）** | 50回/日/ユーザー | 公式 Webhook 確認できず | **〇 可能**（API 契約必要）| 中国企業運営。データ取扱は法務（ハルオ）案件 |
| **アマサーチ** | **✕ 公開 API なし** | 限定的 | なし | **△ 困難**（ERESA / MonoTracer 経由のみ）| 拡張機能スクレイピングは利用規約内 |
| **FBA計算機** | **✕ 公式単体 API なし。ただし SP-API の Product Fees API で同等機能あり** | セラーセントラルから手動 | なし | **◎ SP-API 経由で代替可** | 自社利用は無料継続（2026年以降も）|

## 詳細

### 2-1. Keepa

**API スペック:**
- アクセスキー認証＋Token 制（1リクエストで1〜複数 Token 消費）
- Token は1分あたり生成（プラン依存）、60分で expire
- 月額 €19（≒¥3,000）の Premium で**1 token/minute** の基本アクセス権付与
- Python SDK あり（`pip install keepa`）、Postman コレクションあり

**Sato-Scope 組込シナリオ:**
- FastAPI バックエンドから直接 HTTP リクエスト or Python SDK 経由
- 「価格履歴・販売数推定・Product Finder 結果」を JSON で取得し、社長ダッシュボードに描画
- **Token コストの設計**が必要（1検索＝1 Token として、月間 60×24×30 = 43,200 Token 上限）

**規約:**
- 商用利用を妨げる明示条項は WebSearch 範囲で確認できず（要、法務最終確認）
- データ可搬性は確保されている（CSV エクスポート可）

### 2-2. SellerSprite

**API スペック:**
- 公式 API ドキュメント: https://sellersprite.github.io/
- エンドポイント例：`/v1/product/research`、`/v1/product/competitor-lookup`、`/v1/keyword/miner`、`/v1/traffic/keyword`
- 問い合わせ先：bi@iyunya.com（7日間無料試用可）
- データエクスポート：50回/日/ユーザー

**Sato-Scope 組込シナリオ:**
- FastAPI から直接コール
- **「ASIN ⇄ キーワード逆引き」** が独自価値。これは Keepa にない
- 競合トラッキング・PPC 分析データを Sato-Scope ダッシュボードに統合可

**規約・リスク:**
- ⚠️ **中国企業運営** ─ データ取扱・経済安全保障法整合性は法務（ハルオ）の判断要
- 海外運営による突然の値上げ・サービス終了リスクは国内ツールより高め
- API 料金は別途（要問い合わせ）

### 2-3. アマサーチ

**API スペック:**
- **公式 API は公開されていない**（一次情報・WebSearch 範囲）
- ERESA との連携は可能（公式機能）
- MonoTracer との連携も公式案内あり
- Chrome 拡張機能としての利用が中心

**Sato-Scope 組込シナリオ:**
- 直接組込は不可
- **代替案：ERESA / ERESA AI を経由する**か、**アマサーチを「人間が触る目視ツール」として割り切る**
- 店舗せどりのバーコード読み取りはモバイルアプリ単体運用が向いている（API 不要のユースケース）

**規約:**
- 日本法人運営（株式会社IDEATECH）。日本の個人情報保護法・特商法準拠
- スクレイピングは利用規約内

### 2-4. FBA計算機（Amazon Revenue Calculator）

**API スペック:**
- **単独 API は提供されていない**（セラーセントラル上の Web UI のみ）
- **ただし SP-API の Product Fees API（`getMyFeesEstimate` / `getMyFeesEstimates`）で同等機能が提供されている**
- Catalog Items API v2022-04-01 と組み合わせれば、ASIN 入力 → 手数料試算が完全自動化可能

**Sato-Scope 組込シナリオ:**
- **これが Sato-Scope 中核機能の最有力候補**
- SP-API は **自社利用（社長自身のセラーアカウント）であれば2026年以降も無料継続**（一次：Amazon 公式発表 2025-11-03）
- 第三者向け開発のみ年 $1,400 USD 課金。Sato-Scope は対象外
- 1リクエストで最大20 ASIN の手数料試算が可能

**規約:**
- Amazon SP-API Developer 登録が必要（個人/法人セラー本人なら通過）
- 自社利用条件：「他セラーにデータ提供しない」線引きを守れば OK

## Sato-Scope（FastAPI）連携設計の事実整理

| データ層 | 推奨ソース | 取得方法 |
|---|---|---|
| **価格・在庫・ランキング履歴** | Keepa API | Token 課金 |
| **キーワード ⇄ ASIN 逆引き、競合分析** | SellerSprite API | サブスクリプション |
| **手数料試算・販売実績・在庫** | Amazon SP-API（Product Fees / Finances / FBA Inventory）| 自社利用無料 |
| **競合のレビュー感情分析・売れ筋画像生成** | OpenAI / Anthropic API + Photoroom API | 従量課金 |
| **店舗せどり（モバイル目視）** | アマサーチ（拡張/アプリ）| API 連携せず、人間操作 |

## 重要な発見（事実ベース）

1. **既存4本のうち3本が Sato-Scope に組み込める**（Keepa 直接、SellerSprite 直接、FBA計算機は SP-API で代替）。組み込めないのは**アマサーチのみ**
2. **アマサーチは「AI 連携前提では相対的に弱い」**が、**店舗せどりの目視判断ツールとしてはなお有効**
3. **SP-API 自社利用無料継続** は Sato-Scope の経済性を強く支える（年 $1,400 USD 課金は他社開発者向けで、社長個人ツールは対象外）

## 出典

| ソース | URL | 取得日 |
|---|---|---|
| Keepa API ドキュメント | https://keepaapi.readthedocs.io/en/latest/api_methods.html | 2026-05-22 |
| Keepa API 公式 | https://keepa.com/#!api | 2026-05-22 |
| RevenueGeeks「Keepa Pricing 2026」 | https://revenuegeeks.com/keepa-pricing/ | 2026-05-22 |
| SellerSprite API ドキュメント | https://sellersprite.github.io/ | 2026-05-22 |
| SellerSprite API 概要記事 | https://www.sellersprite.com/en/blog/SellerSprite-Data-Service | 2026-05-22 |
| アマサーチ公式 | https://amasearch.knz-c.com/ | 2026-05-22 |
| ERESA × アマサーチ連携解説 | https://eresa.jp/column/efficient-research-with-amasearch-and-eresa/ | 2026-05-22 |
| SP-API 公式 Welcome | https://developer-docs.amazon.com/sp-api/docs/welcome | 2026-05-22 |
| SP-API Product Fees API | https://developer-docs.amazon.com/sp-api/docs/product-fees-api | 2026-05-22 |
| SP-API 有料化（Amazon 公式） | https://developer.amazonservices.com/spp-announcement-ja-jp | 2026-05-22 |
| PPC.land「Amazon SP-API 有料化 2026」 | https://ppc.land/amazon-introduces-fees-for-third-party-developer-api-access-in-2026/ | 2026-05-22 |
| AWS Prescriptive Guidance「SP-API データ一覧」 | https://docs.aws.amazon.com/prescriptive-guidance/latest/strategy-gen-ai-selling-partner-api/data-sp-api.html | 2026-05-22 |
