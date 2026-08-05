# Re-Sale AutoSync 設計書

> ヤフオク!⇄Amazon 無在庫（FBM）出品ステータス自動同期ツールの設計方針と核となる実装。
> 本書は要件定義の 6 セクションに対応する。**冒頭の「法務・ポリシー上の重大注意」を必ず先に読むこと。**

---

## 採用モデル（確定）と設計インプリケーション

**確定した運用モデル（ポリシー適合）**：

> **即時仕入れ（ヤフオク落札）→ 検品 → ラベル貼替（外注先）→ FBA 納品 → Amazon が自社出品者名義で発送。**

これは実物を自社で保有・Amazon 倉庫へ納品する正規の FBA であり、**ドロップシッピングポリシーには
抵触しない**（他の小売業者に顧客へ直接発送させる形態ではないため）。

### この確定により変わった設計方針（重要）

- **「ヤフオク在庫と同期して Amazon 在庫を 0/1 に自動切替」する当初のコア機能は、FBA では前提が消える。**
  無在庫（FBM）は「先に出品 → 仕入元が消えたら急いで在庫 0」が必須だったが、**FBA は出品前に実物を
  保有**しており、在庫は Amazon 倉庫の実数で管理され売り切れ判定も Amazon が行う。
  → ヤフオクのオークション終了を監視して在庫 0 にする必要が原理的になくなる。
- **ツールの価値の重心は「在庫同期」→「仕入れ判断 ＋ 仕入れ〜FBA 納品パイプライン管理 ＋ FBA 在庫/価格の監視」へ移る。**
- 本コードの `putListing` は **FBA を既定**（`fulfillment_channel_code = AMAZON_JP`、在庫は倉庫実数管理）に更新済み。
  `pricing.ts` は **FBA 手数料（referral ＋ FBA 配送代行 ＋ 外注プレップ費）**で利益を逆算するよう更新済み。
- 旧「ヤフオク監視 → 在庫 PATCH」ロジック（`auctionMonitor.ts` / `syncService.ts` / `monitorJob.ts`）は
  **FBM を併用する場合の任意機能**として温存。FBA 主軸では未使用でよい（README/§5 参照）。

> ヤフオク!スクレイピングを使う場合（リサーチ用の相場取得 or FBM 併用時）は、Yahoo! の利用規約・
> robots.txt・アクセス負荷に配慮する（§6）。監視は自分が連携した ID のみに限定し全件クロールしない。

---

## 1. アーキテクチャ設計

### 全体構成（テキスト構成図）

```
        ┌─────────────────────────────────────────────────────────┐
        │                     ブラウザ（社長/運用者）                 │
        │  パイプラインボードUI: リサーチ→仕入れ登録→段階移動→FBA出品    │
        └───────────────┬─────────────────────────────────────────┘
                        │ HTTP(JSON)
        ┌───────────────▼─────────────────────────────────────────┐
        │                Web/API サーバ (Express + TypeScript)       │
        │  /api/amazon/search  /api/price/preview  /api/products     │
        │  /api/products/:id/advance   /api/products/:id/list        │
        └───┬───────────────┬───────────────────┬──────────────────┘
            │               │                   │
   ┌────────▼───────┐ ┌─────▼─────────┐ ┌───────▼──────────┐
   │ Amazon SP-API   │ │ Pipeline       │ │ Pricing サービス   │
   │ (LWA 認証)       │ │ サービス        │ │ (FBA手数料込み逆算) │
   │ catalog/listings│ │ (段階遷移/出品)  │ └──────────────────┘
   │ (FBA出品 PUT)   │ └─────┬─────────┘
   └────────┬───────┘       │
            │        ┌──────▼───────────────────────────────────┐
            └───────►│        DB (Prisma / SQLite→PG/MySQL)       │
                     │  Product(pipelineStage) / PipelineLog / Setting│
                     └──────▲───────────────────────────────────┘
                            │ 任意 / Phase2（20分おき）
        ┌───────────────────┴──────────────────────────────────┐
        │      Cron Worker (node-cron / 将来 BullMQ)  ※任意       │
        │  FBA在庫残数チェック→再仕入れアラート / 価格追随（Phase2）  │
        └────────────────────────────────────────────────────────┘
```

- **Web/API とワーカーはプロセス分離**（`npm run dev` と `npm run worker`）。
- **DB がシステムの真実（source of truth）**。仕入れた各商品の状態（pipelineStage）を DB で管理し、
  UI/ API からの手動操作で段階を前進させる。FBA 在庫の実数管理は Amazon 側が担う。

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
    ├── server.ts                # Express: API + パイプラインボード
    ├── views/index.ejs          # かんばん UI（仕入済→…→出品中）
    ├── scripts/testAuth.ts      # SP-API 認証スモークテスト（npm run auth:test）
    ├── amazon/
    │   ├── spapiClient.ts        # LWA トークン管理 + 共通HTTP(429リトライ)
    │   ├── catalog.ts            # Catalog Items API（ASIN/キーワード検索）
    │   └── listings.ts           # Listings Items API（FBA/FBM 出品 PUT・任意PATCH）
    ├── yahoo/
    │   └── auctionMonitor.ts     # 仕入れ元相場の参照/FBM併用時の任意機能
    ├── services/
    │   ├── pricing.ts            # FBA手数料込みで販売価格を逆算
    │   └── pipelineService.ts    # 段階遷移(SOURCED→…→LISTED)＋FBA出品
    └── jobs/
        └── monitorJob.ts         # 任意/Phase2: FBA在庫・価格監視のスタブ
```

---

## 2. データベーススキーマ

`prisma/schema.prisma` を参照。**FBA 有在庫モデル**のため、監視対象テーブルではなく
「仕入れ〜FBA納品〜出品」を追うパイプライン中心の構成。

| テーブル | 役割 | 主なカラム |
|---|---|---|
| **Product** | 仕入れた 1 商品（SKU 単位） | `asin`, `sku(unique)`, `productType`, `purchasePrice`, `procurementShipping`, `prepCost`, `fbaFee`, `targetMargin`, `sellPrice`, `pipelineStage`, `listingState`, `fnsku`, `sourceUrl/sourceRef/purchasedAt` |
| **PipelineLog** | 状態遷移の監査ログ | `fromStage`, `toStage`, `note` |
| **Setting** | 既定利益率・手数料率・外注単価等 | `key`, `value` |

設計判断：

- **`pipelineStage`** で `SOURCED → INSPECTED → RELABELED → INBOUND → LISTED → SOLD_OUT` を管理。
  実物を保有するため、無在庫時代の「監視対象オークション」テーブル（Auction）は廃止。仕入れ元は
  一度きりの参照情報として Product に内包（`sourceUrl` / `sourceRef` / `purchasedAt`）。
- **原価内訳を Product に保存**（落札・仕入送料・外注プレップ費・FBA手数料）し、利益計算と監査を両立。
- **`PipelineLog`** に全遷移を残し、外注先への受け渡しや納品漏れを後から追える。
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

実装：`src/yahoo/auctionMonitor.ts`。**位置づけ変更**：FBA 有在庫では在庫の自動同期は不要のため、
本モジュールは「**リサーチ時の仕入れ元相場の参照**」（`GET /api/source/yahoo/:id`）と、FBM を
併用する場合の任意機能に用途を限定。cron の自動同期からは切り離した。

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

実装：`src/jobs/monitorJob.ts`。**FBA 有在庫のため、在庫の自動同期ループは廃止**（実物を保有し
在庫は倉庫実数管理のため不要）。パイプラインの状態遷移は UI/ API からの手動操作
（`pipelineService.advanceStage`）で進める。

cron ワーカーは **Phase 2 の任意機能**として残置し、以下を担う想定（現状は LISTED/INBOUND 件数を
集計する安全なスタブ）：

- `node-cron` で既定 **20 分おき**（`MONITOR_CRON`）。
- **FBA 在庫残数チェック**（FBA Inventory API）→ 在庫僅少で**再仕入れアラート**。
- **価格追随**（Product Pricing API）→ 想定利益を割る価格で**通知/リプライス**。
- 将来は **BullMQ** に移行し、リトライ・遅延・並列度をキューで制御するとスケールしやすい。

---

## 6. 開発を進める上での注意点

### レート制限・エラーハンドリング

- **SP-API はトークンバケット方式のレート制限**。各オペレーションに rate/burst があり、
  超過で 429。`x-amzn-RateLimit-Limit` ヘッダを読み、**429/5xx は指数バックオフ + Retry-After**
  で再試行（本実装済み）。大量更新は **PATCH ではなく Feeds API** に寄せる。
- すべての外部呼び出しに **タイムアウト**を設定。失敗は `PipelineLog`/pino に構造化ログで残す。
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

### Amazon ドロップシッピングポリシー違反の回避（最重要）

> 冒頭の「重大注意」の再掲。技術的緩和策だけでは合法・適正にならない点に留意。

- **推奨は「即時仕入れ→自社発送（有在庫寄り）」**。ヤフオク落札品を自社で検品・保管し、
  **自社名義・自社梱包で発送**する。他小売業者に直接発送させない。これで
  ドロップシッピングポリシーの主要禁止事項を外せる。本ツールの在庫同期は有在庫でも有効。
- **ハンドリングタイムを長めに**設定し、仕入れ（落札→入手）の猶予を確保。到着遅延・
  キャンセル率の悪化を防ぐ。
- **在庫 0 化は即時性が命**：オークション終了/落札を検知したら**最優先で Amazon を停止**し、
  「買えない注文」を発生させない（キャンセル率・顧客体験の毀損＝アカウント健全性の悪化を防ぐ）。
- **価格・出荷の整合**：想定落札価格が上振れした場合に赤字出品にならないよう、`targetMargin`
  に加え**下限価格ガード**を将来追加（現状は `calcSellPrice` で試算のみ）。
- **本番投入は社長の Go/NoGo（実 Do）を必須**とする。`DRY_RUN=true` を既定にし、
  検証が済むまで Amazon への書き込みを行わない。
```
