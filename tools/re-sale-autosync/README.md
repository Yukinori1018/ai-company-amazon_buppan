# Re-Sale AutoSync（FBM 無在庫監視 ＋ FBA 仕入れパイプライン）

ヤフオク! を仕入れ元に、**2 つの運用を 1 ツール**で扱う。商品ごとに `fulfillmentType` で分岐。

- **FBM（無在庫）**: ヤフオク落札**前**に Amazon 出品 → オークションを監視 → 終了/取消で在庫0、再出品で在庫1。
- **FBA（有在庫）**: 即時仕入れ → 検品 → ラベル貼替（外注）→ FBA 納品 → 出品（かんばんで段階管理）。

> ⚠️ **法務注意**: **FBM（ヤフオク→Amazon 無在庫）は Amazon のドロップシッピングポリシーに抵触する
> リスクが残ります**（実物保有前に出品・販売する形態）。在庫0化の即時性でキャンセルを防ぐ設計にしていますが、
> リスクは消えません。**FBA（即時仕入れ→自社検品→自社名義でFBA納品）は非抵触**。詳細は
> [`docs/DESIGN.md`](docs/DESIGN.md)。既定 `DRY_RUN=true`（Amazon へ書き込まない）。

## セットアップ

```bash
cd tools/re-sale-autosync
cp .env.example .env          # 実値を記入（SP-API 認証・DB 等）
npm install
npm run prisma:generate
npm run prisma:migrate        # SQLite に初期スキーマを作成
npm run auth:test             # （推奨）SP-API 認証だけ先に単独検証
```

> 現行 SP-API は **AWS SigV4/STS/IAM ロール不要**（LWA トークンのみ）。旧来の複雑さはありません。

## 起動

```bash
npm run dev      # Web/API + UI（FBM監視一覧＋FBAボード）→ http://localhost:3000
npm run worker   # 監視ワーカー（cron 常駐・既定20分おき）: FBM在庫同期
```

## 使い方

- **FBM**: フォームで方式=FBM、ASIN・SKU・productType・**ヤフオクID**・価格を入れて「FBM出品＋監視開始」。
  以後ワーカーがオークションを巡回し、終了/取消で在庫0、再出品で在庫1に自動同期。
- **FBA**: 方式=FBA で「仕入れ登録（SOURCED）」→ ボード上で `検品済→ラベル貼替済→FBA納品済` と前進 →
  `FBA納品済` で「FBA出品」を押すと SP-API 出品 → `出品中`。
  段階: `SOURCED → INSPECTED → RELABELED → INBOUND → LISTED → SOLD_OUT`。

## 主なファイル

| 機能 | ファイル |
|---|---|
| 設計書（6セクション） | `docs/DESIGN.md` |
| DB スキーマ | `prisma/schema.prisma` |
| SP-API 認証/出品/検索 | `src/amazon/spapiClient.ts`, `listings.ts`, `catalog.ts` |
| 認証スモークテスト | `src/scripts/testAuth.ts` |
| 価格計算（FBM/FBA共通） | `src/services/pricing.ts` |
| FBM 出品＋監視紐付け | `src/services/fbmService.ts` |
| FBM 在庫同期（核） | `src/services/syncService.ts` |
| FBA パイプライン（核） | `src/services/pipelineService.ts` |
| ヤフオク監視 | `src/yahoo/auctionMonitor.ts` |
| Cron ワーカー | `src/jobs/monitorJob.ts` |
| Web/API + UI | `src/server.ts`, `src/views/index.ejs` |

## API

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/amazon/search?asin=` or `?keyword=` | Amazon 商品情報 |
| GET | `/api/source/yahoo/:auctionId` | ヤフオク状態/相場の取得 |
| POST | `/api/price/preview` | 手数料込みの利益試算 |
| POST | `/api/fbm/list` | FBM 出品＋監視紐付け |
| POST | `/api/monitor/run` | FBM 監視を今すぐ1周 |
| POST | `/api/products` | FBA 仕入れ登録（SOURCED） |
| POST | `/api/products/:id/advance` | FBA 段階を1つ前進 |
| POST | `/api/products/:id/list` | FBA 出品（INBOUND→LISTED） |

> これは動作の骨格を示す雛形です。SP-API の `attributes`／FBA チャネルコードはマーケットプレイス×
> productType で異なるため、本番では `getDefinitionsProductType` のスキーマに合わせて動的生成してください。
