# Re-Sale AutoSync 設計書

> ヤフオク!⇄Amazon 無在庫（FBM）出品ステータス自動同期ツールの設計方針と核となる実装。
> 本書は要件定義の 6 セクションに対応する。**冒頭の「法務・ポリシー上の重大注意」を必ず先に読むこと。**

---

## 採用モデル（確定）: FBM 無在庫 ＋ FBA 有在庫 のハイブリッド

社長方針により、**2 つの運用を 1 ツールで並行**する。商品ごとに `fulfillmentType`（FBM/FBA）で分岐。

| 方式 | フロー | 在庫の考え方 | このツールの役割 |
|---|---|---|---|
| **FBM（無在庫）** | ヤフオク落札**前**に Amazon 出品 → オークション監視 → 終了/取消で在庫0、再出品で在庫1 | 自社が quantity を 0/1 で制御 | **ヤフオク状態→Amazon在庫の自動同期**（cron） |
| **FBA（有在庫）** | 即時仕入れ→検品→ラベル貼替(外注)→FBA納品→出品 | Amazon 倉庫の実数管理 | **仕入れ〜納品パイプライン管理**＋出品 |

### ⚠️ 法務注意（FBM パスに残るリスク・社長判断で進行）

- **FBM（ヤフオク→Amazon 無在庫）は Amazon のドロップシッピングポリシーに抵触するリスクが残る**
  （他の小売業者から仕入れ、実物保有前に出品・販売する形態）。アカウント指標悪化・停止のリスクを
  内包する点は変わらない。**在庫0化の即時性**（落札/終了検知→即停止）でキャンセルを防ぐことが最重要。
- **FBA（即時仕入れ→自社検品→自社名義でFBA納品）はポリシー非抵触**。
- ヤフオク!スクレイピングは Yahoo! の規約・robots・負荷に配慮（§6）。監視は連携済み ID のみ。

### コード上の分岐

- `putListing({ fulfillmentType })`：FBM=`DEFAULT`＋quantity、FBA=`AMAZON_JP`（倉庫管理）。
- FBM 経路：`fbmService.createFbmListing`（出品＋Auction紐付け）→ `monitorJob`＋`syncService.syncOne`（在庫同期）。
- FBA 経路：`pipelineService`（SOURCED→…→LISTED の段階遷移＋出品）。Auction は持たず監視対象外。
- `pricing.calcSellPrice`：FBM/FBA 共通。FBA は fbaFee を、FBM は自社発送費を prepCost に入れる。

---

## 1. アーキテクチャ設計

### 全体構成（テキスト構成図）

```
        ┌─────────────────────────────────────────────────────────┐
        │                     ブラウザ（社長/運用者）                 │
        │  FBM監視一覧 ＋ FBAパイプラインボード（方式を切替えて登録）     │
        └───────────────┬─────────────────────────────────────────┘
                        │ HTTP(JSON)
        ┌───────────────▼─────────────────────────────────────────┐
        │                Web/API サーバ (Express + TypeScript)       │
        │  FBM: /api/fbm/list  /api/monitor/run                      │
        │  FBA: /api/products  /:id/advance  /:id/list               │
        │  共通: /api/amazon/search /api/source/yahoo /api/price/preview│
        └───┬───────────────┬───────────────────┬──────────────────┘
            │               │                   │
   ┌────────▼───────┐ ┌─────▼─────────┐ ┌───────▼──────────┐
   │ Amazon SP-API   │ │ FBM: fbmService│ │ Yahoo auctionMonitor│
   │ (LWA 認証)       │ │ FBA: pipeline  │ │ (Cheerio/Puppeteer) │
   │ catalog/listings│ │ Service        │ └───────┬──────────┘
   │ (FBM/FBA 出品)  │ └─────┬─────────┘         │
   └────────┬───────┘       │                    │
            │        ┌──────▼────────────────────▼─────────────┐
            └───────►│        DB (Prisma / SQLite→PG/MySQL)       │
                     │ Product / Auction(FBM) / SyncLog / PipelineLog│
                     └──────▲───────────────────────────────────┘
                            │ 20分おき（FBM 同期）
        ┌───────────────────┴──────────────────────────────────┐
        │      Cron Worker (node-cron / 将来 BullMQ)              │
        │ FBM: active Auction 巡回→状態判定→Amazon在庫PATCH        │
        │ FBA(Phase2): 在庫残数/価格の監視アラート                  │
        └────────────────────────────────────────────────────────┘
```

- **Web/API とワーカーはプロセス分離**（`npm run dev` と `npm run worker`）。
- **DB がシステムの真実**。FBM は「ヤフオク実態 ⇄ Amazon在庫」を cron で冪等同期、FBA は段階遷移を手動管理。

### ディレクトリ構造

```
tools/re-sale-autosync/
├── README.md
├── package.json / tsconfig.json / .env.example / .gitignore
├── prisma/
│   └── schema.prisma            # Product(pipelineStage) / PipelineLog / Setting
├── docs/
│   └── DESIGN.md                # 本書
└── src/
    ├── config.ts                # 環境変数の Zod 検証
    ├── logger.ts / db.ts        # pino ロガー / Prisma シングルトン
    ├── server.ts                # Express: FBM監視一覧 ＋ FBAボード ＋ API
    ├── views/index.ejs          # UI（方式切替＋FBM表＋FBAかんばん）
    ├── scripts/testAuth.ts      # SP-API 認証スモークテスト（npm run auth:test）
    ├── amazon/
    │   ├── spapiClient.ts        # LWA トークン管理 + 共通HTTP(429リトライ)
    │   ├── catalog.ts            # Catalog Items API（ASIN/キーワード検索）
    │   └── listings.ts           # Listings Items API（FBM/FBA 出品 PUT・在庫 PATCH）
    ├── yahoo/
    │   └── auctionMonitor.ts     # ヤフオク生存確認（Cheerio/Puppeteer・多数決判定）
    ├── services/
    │   ├── pricing.ts            # 手数料込みで販売価格を逆算（FBM/FBA共通）
    │   ├── fbmService.ts         # FBM出品＋Auction紐付け
    │   ├── syncService.ts        # FBM: ヤフオク状態→Amazon在庫 同期（核）
    │   └── pipelineService.ts    # FBA: 段階遷移(SOURCED→…→LISTED)＋出品
    └── jobs/
        └── monitorJob.ts         # node-cron: FBM同期サイクル（+FBA Phase2）
```

---

## 2. データベーススキーマ

`prisma/schema.prisma` を参照。FBM/FBA 両対応。

| テーブル | 役割 | 主なカラム |
|---|---|---|
| **Product** | 出品する 1 商品（SKU 単位・FBM/FBA共通） | `asin`, `sku(unique)`, `productType`, `fulfillmentType`, 原価内訳(`purchasePrice`/`procurementShipping`/`prepCost`/`fbaFee`), `sellPrice`, FBM用(`quantity`/`listingState`), FBA用(`pipelineStage`/`fnsku`) |
| **Auction** | 監視対象ヤフオク（**FBM のみ**・Product と 1:1） | `yahooAuctionId(unique)`, `status`, `currentPrice`, `endTime`, `checkFailCount`, `active` |
| **SyncLog** | FBM 在庫同期の監査ログ | `auctionStatus`, `action`, `from/toQuantity`, `spapiStatus` |
| **PipelineLog** | FBA 段階遷移の監査ログ | `fromStage`, `toStage`, `note` |
| **Setting** | 既定利益率・手数料率・外注単価等 | `key`, `value` |

設計判断：

- **`fulfillmentType` で分岐**。FBM は `quantity`/`listingState`＋`Auction` を使い、FBA は `pipelineStage`
  （`SOURCED → INSPECTED → RELABELED → INBOUND → LISTED → SOLD_OUT`）を使う。
- **`Auction` は FBM 商品のみ**が 1:1 で持つ（`checkFailCount` で UNKNOWN 連続時の誤停止を防ぐ）。FBA は持たない。
- **原価内訳を Product に保存**し利益計算と監査を両立。ログは FBM=`SyncLog` / FBA=`PipelineLog` に分離。
- **SQLite で開始**し、`provider` と `DATABASE_URL` の差し替えだけで PostgreSQL/MySQL に移行可能。

---

## 3. Amazon SP-API 連携の実装方針

実装：`src/amazon/spapiClient.ts`（認証）、`src/amazon/listings.ts`（出品/在庫）。

### 認証（LWA）

- 2023 以降 SP-API は **AWS SigV4 署名・IAM ロール不要**。LWA の `refresh_token` から
  `access_token` を取得し、`x-amz-access-token` ヘッダに載せて呼ぶだけ。
- `access_token` は約 1 時間で失効 → **内部でキャッシュし、60 秒マージンで自動更新**。

### 出品登録（PUT / Listings Items API 2021-08-01）— FBA

```
PUT /listings/2021-08-01/items/{sellerId}/{sku}?marketplaceIds=A1VC38T7YXB528
```
- `productType` は ASIN／カテゴリで必須。`getDefinitionsProductType` でスキーマを取得し、
  `attributes` を動的に組む（`condition_type`, `purchasable_offer`, `fulfillment_availability`）。
- **FBA（既定）**：`fulfillment_availability.fulfillment_channel_code = "AMAZON_JP"`。
  **在庫数は指定しない**（Amazon 倉庫の実数で管理。納品＝Inbound Shipment で反映）。
  `putListing({ fulfillmentType: 'FBA' })` として実装。
- FBM 併用時のみ `fulfillment_channel_code = "DEFAULT"` ＋ `quantity` ＋ ハンドリングタイムを記述。

### 在庫の考え方（FBA）

- FBA では在庫は**倉庫の実数**。無在庫時代の「quantity を 0/1 に PATCH して停止/再開」は不要。
  `setOutOfStock()`/`setInStock()`（PATCH）は **FBM 併用時の任意機能**として残置。
- 補充判断は Phase 2 の **FBA Inventory API** による残数チェックで行う想定（§5）。
- 大量出品は **Feeds API（JSON_LISTINGS_FEED）**で 1 リクエストにまとめると効率的。

### 安全弁

- `DRY_RUN=true` の間は PUT/PATCH を**実行せずログのみ**。本番前検証で誤出品を防ぐ。
- 429/5xx は **指数バックオフ + Retry-After 尊重**で最大 3 回リトライ（§6）。

---

## 4. ヤフオク! 監視ロジックの実装方針

実装：`src/yahoo/auctionMonitor.ts`。**FBM 無在庫の在庫同期の要**。FBA ではリサーチ時の相場参照に使う。

- Yahoo! オークション公式 API は提供終了のため、**商品ページ取得で状態判定**する。
- 取得は 2 モード：`cheerio`（軽量 HTTP、既定）／`puppeteer`（JS レンダリング必須ページ用）。
  Puppeteer 失敗時は Cheerio にフォールバック。
- **判定は複数シグナルの多数決**で頑健化（HTML 構造変化への耐性）：
  - `ENDED`：「このオークションは終了しています」等 + `残り時間/入札する` が無い
  - `CANCELLED`：「削除されました」「出品が取り消され」
  - `NOT_FOUND`：404 or 「ページが見つかりません」
  - `ACTIVE`：「残り時間 / 入札する / 即決」
  - `UNKNOWN`：上記いずれも判定不能（**この時は Amazon を触らない**）
- 価格は JSON-LD → meta → DOM の順でフォールバック抽出。終了時刻は `og:auction:end_time`。
- **ポライトネス**：UA＋連絡先明示、`YAHOO_REQUEST_INTERVAL_MS` で最低間隔を確保、
  監視対象は「連携済み ID のみ」。`parseAuctionHtml()` は純関数として分離しテスト容易に。

---

## 5. 定期実行タスク（Cron）の実装

実装：`src/jobs/monitorJob.ts`、FBM 同期の核は `src/services/syncService.ts`。

- `node-cron` で既定 **20 分おき**（`MONITOR_CRON`）。`active` な Auction（=FBM商品）を全件取得し、
  **`p-limit` で同時実行数を絞って**巡回。**多重起動防止**フラグ＋**`Promise.allSettled`**で頑健化。
- FBM 同期ロジック（`syncOne`）：
  1. ヤフオク状態を取得 → Auction に観測結果を保存
  2. 状態→希望在庫（ACTIVE→1 / ENDED・CANCELLED・NOT_FOUND→0 / UNKNOWN→触らない）
  3. **希望値と現在値が一致すれば何もしない（冪等）**
  4. 差分があれば Amazon を PATCH → Product 更新 → **SyncLog に必ず記録**
  5. 落札/終了で `Auction.active=false`
- FBA 商品は Auction を持たないため対象外。**FBA の在庫残数チェック・価格追随は Phase 2** で本ワーカーに追加予定。
- 将来は **BullMQ** に移行し、リトライ・遅延・並列度をキューで制御するとスケールしやすい。

---

## 6. 開発を進める上での注意点

### レート制限・エラーハンドリング

- **SP-API はトークンバケット方式のレート制限**。各オペレーションに rate/burst があり、
  超過で 429。`x-amzn-RateLimit-Limit` ヘッダを読み、**429/5xx は指数バックオフ + Retry-After**
  で再試行（本実装済み）。大量更新は **PATCH ではなく Feeds API** に寄せる。
- **FBM で UNKNOWN 時は在庫を触らない**設計（`checkFailCount` 閾値）。ヤフオクの一時的失敗で在庫を
  落とすと機会損失＋アカウント指標悪化につながる。連続 UNKNOWN が閾値超で人手確認へ。
- すべての外部呼び出しに **タイムアウト**を設定。失敗は `SyncLog`/`PipelineLog`/pino に構造化ログで残す。
- **秘密情報は `.env`（gitignore 済み）**。`.env.example` のみコミット。

### SP-API 認証の先行検証（最も詰まりやすい箇所）

- 認証は SP-API 実装で最も複雑になりがち。**`npm run auth:test`（`src/scripts/testAuth.ts`）で
  トークン取得＋疎通だけを単独検証**してから全体を起動する運用を推奨。
- 現行 SP-API は **AWS SigV4/STS/IAM ロール不要**（2023〜）。LWA アクセストークンのみで、
  旧来の STS トークン取得の複雑さはない。`spapiClient.ts` がトークンをキャッシュ＋自動更新する。

### ヤフオク! スクレイピングの配慮

- 監視は**自分が連携した ID のみ**。全件クロール・高頻度アクセスをしない。
- UA と連絡先を明示、`robots.txt` と利用規約を尊重、間隔を空ける。
- **IP ブロック対策**: リクエスト間隔（`YAHOO_REQUEST_INTERVAL_MS`）に加え、`throttle()` で
  **±40% のランダムジッタ**を乗せ機械的パターンを崩す。Cron 間隔（`MONITOR_CRON`）と
  `p-limit`（同時実行数）で全体の頻度も抑制。**429/503 は指数バックオフ + Retry-After** で再試行。
- 構造変化に備え **多数決判定 + UNKNOWN フォールバック**。壊れたら止めるのではなく人手確認へ。

### Amazon ドロップシッピングポリシー（FBM パスの最重要注意）

> 冒頭の法務注意の再掲。**FBM（無在庫）パスにはポリシー抵触リスクが残る**（技術的緩和では消えない）。

- **FBA パス**は「即時仕入れ→自社検品→自社名義でFBA納品」＝**ポリシー非抵触**。可能な限りこちらへ寄せる。
- **FBM パスを運用する場合の緩和策**（リスクを下げるだけで消しはしない）：
  - **在庫 0 化の即時性が命**：オークション終了/落札を検知したら**最優先で Amazon を停止**し、
    「買えない注文（→キャンセル）」を出さない。キャンセル率悪化はアカウント健全性を直接毀損する。
  - **ハンドリングタイムを長めに**設定し、落札→入手の猶予を確保。
  - **UNKNOWN では止めも動かしもしない**（誤停止＝機会損失、誤出品＝在庫なし販売）。
  - **下限価格ガード**を将来追加し、落札価格の上振れ時の赤字出品を防ぐ（現状 `calcSellPrice` は試算のみ）。
- **本番投入は社長の Go/NoGo（実 Do）を必須**とし、`DRY_RUN=true` を既定にして検証が済むまで書き込まない。
```
