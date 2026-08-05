# Re-Sale AutoSync 設計書

> ヤフオク!⇄Amazon 無在庫（FBM）出品ステータス自動同期ツールの設計方針と核となる実装。
> 本書は要件定義の 6 セクションに対応する。**冒頭の「法務・ポリシー上の重大注意」を必ず先に読むこと。**

---

## ⚠️ 法務・ポリシー上の重大注意（着手前提）

このツールが自動化する「ヤフオク!で購入し、Amazon の顧客へその商品を届ける」無在庫転売モデルは、
**Amazon のドロップシッピングポリシーに原則抵触する**。Amazon が禁じているのは以下の形態である：

> 「他の小売業者（Yahoo!/楽天/他 EC 等）から商品を購入し、その小売業者に直接
> Amazon の顧客へ発送させる」ドロップシッピング。梱包・明細・発送元が自社（登録セラー名）で
> ないものは**規約違反**であり、**アカウント停止・売上保留・返金**のリスクがある。

- **技術で"回避"できる問題ではない。** 本ツールは「在庫同期の自動化」という運用効率化の雛形であって、
  ポリシー違反を許可・推奨するものではない。本番投入は社長の Go/NoGo 判断（実 Do）を要する。
- **正規に近づけるなら**：ヤフオクで落札した実物をいったん自社（または倉庫）で検品・保管し、
  **自社名義で自社が発送する**「有在庫（または即時仕入れ→自社発送）」に寄せる。これなら
  ドロップシッピングポリシーの主要な禁止事項を外せる。本ツールの「在庫同期」機能は
  **有在庫運用でも在庫切れ即時停止の自動化として有効**。
- **ヤフオク!のスクレイピング**：Yahoo! の利用規約・robots.txt・アクセス負荷に配慮する。
  監視は「自分が連携した出品 ID のみ」に限定し、全件クロールはしない。API 提供終了済みのため
  ページ取得で代替するが、頻度・間隔・UA 明示を守る（§6）。

以上を踏まえ、以下は**あくまで技術雛形**として提示する。

---

## 1. アーキテクチャ設計

### 全体構成（テキスト構成図）

```
        ┌─────────────────────────────────────────────────────────┐
        │                     ブラウザ（社長/運用者）                 │
        │   リサーチ＆出品UI（EJS/簡易SPA）: ASIN検索→ヤフオク照合→出品  │
        └───────────────┬─────────────────────────────────────────┘
                        │ HTTP(JSON)
        ┌───────────────▼─────────────────────────────────────────┐
        │                Web/API サーバ (Express + TypeScript)       │
        │  /api/amazon/search  /api/yahoo/:id  /api/price/preview    │
        │  /api/list           /api/monitor/run                     │
        └───┬───────────────┬───────────────────┬──────────────────┘
            │               │                   │
   ┌────────▼───────┐ ┌─────▼─────────┐ ┌───────▼────────┐
   │ Amazon SP-API   │ │ Yahoo 監視     │ │ Pricing サービス │
   │ (LWA 認証)       │ │ (Cheerio/     │ │ (利益率→販売価格) │
   │ catalog/listings│ │  Puppeteer)   │ └────────────────┘
   └────────┬───────┘ └─────┬─────────┘
            │               │
            │        ┌──────▼───────────────────────────────────┐
            │        │        DB (Prisma / SQLite→PG/MySQL)       │
            └───────►│  Product ⇄ Auction (1:1) / SyncLog / Setting│
                     └──────▲───────────────────────────────────┘
                            │ 15〜30分おき
        ┌───────────────────┴──────────────────────────────────┐
        │         Cron Worker (node-cron / 将来 BullMQ)           │
        │  active な Auction を巡回 → 状態判定 → Amazon 在庫 PATCH   │
        └────────────────────────────────────────────────────────┘
```

- **Web/API とワーカーはプロセス分離**（`npm run dev` と `npm run worker`）。監視の重い処理が
  UI レスポンスを阻害しない。将来は BullMQ でジョブをキュー化しスケールアウト可能。
- **DB がシステムの真実（source of truth）**。Amazon/ヤフオク双方の状態を DB に集約し、
  同期ロジックは「DB の希望値 ⇄ 外部の実態」の突合として実装する（冪等）。

### ディレクトリ構造

```
tools/re-sale-autosync/
├── README.md
├── package.json / tsconfig.json / .env.example / .gitignore
├── prisma/
│   └── schema.prisma            # Product / Auction / SyncLog / Setting
├── docs/
│   └── DESIGN.md                # 本書
└── src/
    ├── config.ts                # 環境変数の Zod 検証
    ├── logger.ts / db.ts        # pino ロガー / Prisma シングルトン
    ├── server.ts                # Express: API + EJS ダッシュボード
    ├── views/index.ejs          # 最小 UI
    ├── amazon/
    │   ├── spapiClient.ts        # LWA トークン管理 + 共通HTTP(429リトライ)
    │   ├── catalog.ts            # Catalog Items API（ASIN/キーワード検索）
    │   └── listings.ts           # Listings Items API（PUT出品 / PATCH在庫）
    ├── yahoo/
    │   └── auctionMonitor.ts     # 生存確認スクレイピング（Cheerio/Puppeteer）
    ├── services/
    │   ├── pricing.ts            # 利益率→販売価格の逆算
    │   └── syncService.ts        # ヤフオク状態→Amazon在庫 の同期（核）
    └── jobs/
        └── monitorJob.ts         # node-cron スケジューラ + 1サイクル実行
```

---

## 2. データベーススキーマ

`prisma/schema.prisma` を参照。要点：

| テーブル | 役割 | 主なカラム |
|---|---|---|
| **Product** | Amazon 出品（SKU 単位） | `asin`, `sku(unique)`, `productType`, `costPrice`, `shippingCost`, `targetMargin`, `sellPrice`, `quantity`, `listingState` |
| **Auction** | 監視対象ヤフオク（Product と 1:1） | `yahooAuctionId(unique)`, `status`, `currentPrice`, `endTime`, `lastCheckedAt`, `checkFailCount`, `active` |
| **SyncLog** | 同期の監査ログ | `auctionStatus`, `action`, `from/toQuantity`, `spapiStatus`, `message` |
| **Setting** | 既定利益率・手数料率等 | `key`, `value` |

設計判断：

- **Product ⇔ Auction は 1:1**。「Amazon の SKU/ASIN」と「監視対象オークションID」の紐付けが
  要件の中核なので外部キーで厳密に結ぶ（`Auction.productId @unique`）。
- **`checkFailCount`**：ヤフオク取得が一時的に失敗（UNKNOWN）しても、即 Amazon を止めない。
  連続失敗が閾値を超えたら人手確認へ寄せる（誤停止＝機会損失＆評価毀損の防止）。
- **`SyncLog`** を必ず残し、「なぜその時 Amazon を止めた/戻したか」を後から監査できるようにする。
- **SQLite で開始**し、`provider` と `DATABASE_URL` の差し替えだけで PostgreSQL/MySQL に移行可能。

---

## 3. Amazon SP-API 連携の実装方針

実装：`src/amazon/spapiClient.ts`（認証）、`src/amazon/listings.ts`（出品/在庫）。

### 認証（LWA）

- 2023 以降 SP-API は **AWS SigV4 署名・IAM ロール不要**。LWA の `refresh_token` から
  `access_token` を取得し、`x-amz-access-token` ヘッダに載せて呼ぶだけ。
- `access_token` は約 1 時間で失効 → **内部でキャッシュし、60 秒マージンで自動更新**。

### 出品登録（PUT / Listings Items API 2021-08-01）

```
PUT /listings/2021-08-01/items/{sellerId}/{sku}?marketplaceIds=A1VC38T7YXB528
```
- `productType` は ASIN／カテゴリで必須。`getDefinitionsProductType` でスキーマを取得し、
  `attributes` を動的に組む（`condition_type`, `purchasable_offer`, `fulfillment_availability`）。
- FBM は `fulfillment_availability.fulfillment_channel_code = "DEFAULT"`。無在庫は
  **ハンドリングタイム（lead_time_to_ship_max_days）を長めに**して仕入れ猶予を確保。

### 在庫更新（PATCH）

```
PATCH /listings/2021-08-01/items/{sellerId}/{sku}
{ "productType":"PRODUCT",
  "patches":[{ "op":"replace",
    "path":"/attributes/fulfillment_availability",
    "value":[{ "fulfillment_channel_code":"DEFAULT", "quantity":0 }] }] }
```
- **停止 = quantity 0 / 再開 = quantity 1**。`setOutOfStock()` / `setInStock()` として公開。
- 大量 SKU を一括更新する場合は **Feeds API（`POST_FLAT_FILE_INVLOADER` 系 or JSON_LISTINGS_FEED）**
  に切り替えると 1 リクエストで数千件を処理できる（PATCH はリアルタイム少量向け）。

### 安全弁

- `DRY_RUN=true` の間は PUT/PATCH を**実行せずログのみ**。本番前検証で誤出品/誤更新を防ぐ。
- 429/5xx は **指数バックオフ + Retry-After 尊重**で最大 3 回リトライ（§6）。

---

## 4. ヤフオク! 監視ロジックの実装方針

実装：`src/yahoo/auctionMonitor.ts`。

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

実装：`src/jobs/monitorJob.ts`、同期の核は `src/services/syncService.ts`。

- `node-cron` で既定 **20 分おき**（`MONITOR_CRON`）。`active` な Auction を全件取得し、
  **`p-limit` で同時実行数を絞って**巡回（ヤフオク/Amazon 双方の負荷・レート制御）。
- **多重起動防止**フラグ（`running`）で、前サイクルが長引いた場合の重複実行を回避。
- 1 件の失敗が全体を止めないよう **`Promise.allSettled`** で握る。
- 同期ロジック（`syncOne`）：
  1. ヤフオク状態を取得 → Auction に観測結果を保存
  2. 状態→希望在庫にマッピング（ACTIVE→1 / ENDED・CANCELLED・NOT_FOUND→0 / UNKNOWN→触らない）
  3. **希望値と現在値が一致すれば何もしない（冪等）**
  4. 差分があれば Amazon を PATCH → Product 更新 → **SyncLog に必ず記録**
  5. 落札/終了で停止したら `Auction.active=false`（再出品検知したい運用では維持も可）
- 将来は **BullMQ** に移行し、リトライ・遅延・並列度をキューで制御するとスケールしやすい。

---

## 6. 開発を進める上での注意点

### レート制限・エラーハンドリング

- **SP-API はトークンバケット方式のレート制限**。各オペレーションに rate/burst があり、
  超過で 429。`x-amzn-RateLimit-Limit` ヘッダを読み、**429/5xx は指数バックオフ + Retry-After**
  で再試行（本実装済み）。大量更新は **PATCH ではなく Feeds API** に寄せる。
- **UNKNOWN で誤停止しない**設計（`checkFailCount` 閾値）。ヤフオクの一時的失敗で在庫を
  落とすと機会損失＋アカウント指標悪化につながる。
- すべての外部呼び出しに **タイムアウト**を設定。失敗は `SyncLog`/pino に構造化ログで残す。
- **秘密情報は `.env`（gitignore 済み）**。`.env.example` のみコミット。

### ヤフオク! スクレイピングの配慮

- 監視は**自分が連携した ID のみ**。全件クロール・高頻度アクセスをしない。
- UA と連絡先を明示、`robots.txt` と利用規約を尊重、間隔を空ける。
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
