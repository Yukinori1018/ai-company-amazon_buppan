# Re-Sale AutoSync（雛形）

ヤフオク!の中古品を Amazon に無在庫（FBM）出品し、ヤフオク!側の在庫状況と Amazon 側の
出品ステータスを自動同期するツールの**設計＋コード雛形**。

> ⚠️ **重要**：本ツールが自動化する「ヤフオク!→Amazon 無在庫転売」は **Amazon の
> ドロップシッピングポリシーに原則抵触**します。技術で回避できる問題ではありません。
> 詳細と推奨する適正化（即時仕入れ→自社発送への寄せ方）は
> [`docs/DESIGN.md`](docs/DESIGN.md) 冒頭「法務・ポリシー上の重大注意」を必読。
> **本番投入前に社長の Go/NoGo 判断が必要**。既定 `DRY_RUN=true`（Amazon へ書き込まない）。

## セットアップ

```bash
cd tools/re-sale-autosync
cp .env.example .env          # 実値を記入（SP-API 認証・DB 等）
npm install
npm run prisma:generate
npm run prisma:migrate        # SQLite に初期スキーマを作成
```

## 認証を先に単独テスト（推奨）

全体を動かす前に、**SP-API 認証（LWA トークン取得＋疎通）だけ**を最小構成で検証できます。
SP-API は認証が最も詰まりやすいので、ここが通ってから起動へ進むのが安全です。

```bash
npm run auth:test
# Step1: refresh_token→access_token 取得 / Step2: marketplaceParticipations で疎通・権限確認
```

> 補足: 現行 SP-API は 2023 以降 **AWS SigV4 署名・STS/IAM ロールが不要**になっており、
> 認証は LWA アクセストークンのみです（旧来の STS トークン取得の複雑さはありません）。

## 起動

```bash
npm run dev      # Web/API + ダッシュボード  → http://localhost:3000
npm run worker   # 監視ワーカー（cron 常駐、既定 20 分おき）
```

`DRY_RUN=true` の間、Amazon への出品(PUT)・在庫更新(PATCH)は実行されずログのみ。
実運用に切り替える際は `.env` の `DRY_RUN=false` にし、必ず少数 SKU で検証してから。

## 主なファイル

| 機能 | ファイル |
|---|---|
| 設計書（6セクション） | `docs/DESIGN.md` |
| DB スキーマ | `prisma/schema.prisma` |
| SP-API 認証/出品/在庫 | `src/amazon/spapiClient.ts`, `listings.ts`, `catalog.ts` |
| ヤフオク監視 | `src/yahoo/auctionMonitor.ts` |
| 価格計算 | `src/services/pricing.ts` |
| 同期ロジック（核） | `src/services/syncService.ts` |
| Cron ワーカー | `src/jobs/monitorJob.ts` |
| Web/API + UI | `src/server.ts`, `src/views/index.ejs` |

## API

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/amazon/search?asin=` or `?keyword=` | Amazon 商品情報 |
| GET | `/api/yahoo/:auctionId` | ヤフオク現在状態 |
| POST | `/api/price/preview` | 販売価格の試算 |
| POST | `/api/list` | 出品＋監視紐付け保存 |
| POST | `/api/monitor/run` | 監視を今すぐ1周実行 |

> これは動作の骨格を示す雛形です。SP-API の `attributes` はマーケットプレイス×productType で
> 異なるため、本番では `getDefinitionsProductType` のスキーマに合わせて動的生成してください。
