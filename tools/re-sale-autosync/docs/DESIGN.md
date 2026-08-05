# Re-Sale AutoSync 設計書（無在庫 / FBM 専用）

> ヤフオク! を仕入れ元にした Amazon 無在庫(FBM)出品で、**「Amazonで売れたのに仕入れられない」注文**を
> 発生させないためのツール。要件定義の 6 セクションに対応する。

---

## このツールの存在意義（最重要）

無在庫(FBM)の最大リスクは、**Amazon で売れた後に仕入れ元から商品を確保できない**こと。これが起きると
出荷遅延・キャンセルにつながり、**アカウント健全性の低下・最悪アカウント停止**を招く。

本ツールの唯一の目的は、このリスクをアプリの力で極力下げること：

- 出品した商品の**仕入れ元（ヤフオク オークション）の「仕入れ可能性(procurability)」を定期監視**する。
- 仕入れ不能になった瞬間に **Amazon 在庫を 0** にして、「買えない注文」を物理的に発生させない。
- 「仕入れ不能」の判定は 2 種類：
  1. **オークションの消滅**：終了(落札含む)・取消・ページ消滅 → その一点物はもう買えない → 在庫0
  2. **価格の超過**：現在価格 > 損益分岐となる仕入れ元価格(`maxSourcePrice`) → 利益で買えない → 在庫0
- 監視間隔（`MONITOR_CRON`）を詰めるほど「売れたのに買えない」窓が縮む。

> **有在庫(FBA)はこのアプリの対象外**。FBA は「Keepa＋Claude で商品検索 → 社長が選定 →
> メーカーへメール/電話で仕入れ交渉 → FBA 販売」という**手動＋Claude 支援の運用**で進める（アプリ不要）。

### ⚠️ 法務注意（残存リスク）

FBM（他の小売業者=ヤフオク から仕入れ、実物保有前に Amazon で出品・販売する形態）は、Amazon の
ドロップシッピングポリシーに**抵触するリスクが残る**。本ツールは在庫0化の即時性でキャンセルを抑止し
リスクを下げるが、ゼロにはできない。運用は社長判断のもと、`DRY_RUN=true` で検証してから本番投入する。

---

## 1. アーキテクチャ設計

```
        ┌─────────────────────────────────────────────────────────┐
        │                    ブラウザ（社長/運用者）                  │
        │  リサーチ＆出品UI ＋ 監視ダッシュボード（状態/価格/損益分岐）  │
        └───────────────┬─────────────────────────────────────────┘
                        │ HTTP(JSON)
        ┌───────────────▼─────────────────────────────────────────┐
        │                Web/API サーバ (Express + TypeScript)       │
        │  /api/amazon/search  /api/source/yahoo/:id                │
        │  /api/price/preview  /api/list  /api/monitor/run          │
        └───┬───────────────┬───────────────────┬──────────────────┘
            │               │                   │
   ┌────────▼───────┐ ┌─────▼─────────┐ ┌───────▼────────┐
   │ Amazon SP-API   │ │ Yahoo 監視     │ │ Pricing サービス │
   │ (LWA 認証)       │ │ (Cheerio/     │ │ 販売価格＋損益分岐 │
   │ catalog/listings│ │  Puppeteer)   │ │ 仕入れ価格を算出   │
   └────────┬───────┘ └─────┬─────────┘ └────────────────┘
            │               │
            │        ┌──────▼───────────────────────────────────┐
            └───────►│        DB (Prisma / SQLite→PG/MySQL)       │
                     │  Product ⇄ Auction (1:1) / SyncLog / Setting│
                     └──────▲───────────────────────────────────┘
                            │ 20分おき（詰めるほど安全）
        ┌───────────────────┴──────────────────────────────────┐
        │         Cron Worker (node-cron / 将来 BullMQ)           │
        │  active な Auction を巡回 → 仕入れ可能性判定 → 在庫 PATCH  │
        └────────────────────────────────────────────────────────┘
```

- **Web/API とワーカーはプロセス分離**（`npm run dev` と `npm run worker`）。監視の負荷が UI を阻害しない。
- **DB がシステムの真実**。「ヤフオク実態 ⇄ Amazon在庫」を cron で冪等同期する。

### ディレクトリ構造

```
tools/re-sale-autosync/
├── README.md
├── package.json / tsconfig.json / .env.example / .gitignore
├── prisma/schema.prisma          # Product / Auction / SyncLog / Setting
├── docs/DESIGN.md                # 本書
└── src/
    ├── config.ts                 # 環境変数の Zod 検証
    ├── logger.ts / db.ts         # pino ロガー / Prisma シングルトン
    ├── server.ts                 # Express: API + 監視ダッシュボード
    ├── views/index.ejs           # UI（リサーチ&出品＋監視一覧）
    ├── scripts/testAuth.ts       # SP-API 認証スモークテスト
    ├── amazon/
    │   ├── spapiClient.ts         # LWA トークン管理 + 共通HTTP(429リトライ)
    │   ├── catalog.ts             # Catalog Items API（ASIN/キーワード検索）
    │   └── listings.ts            # Listings Items API（FBM 出品 PUT / 在庫 PATCH）
    ├── yahoo/auctionMonitor.ts    # 生存確認スクレイピング（Cheerio/Puppeteer）
    ├── services/
    │   ├── pricing.ts             # 販売価格＋損益分岐仕入れ価格の算出
    │   ├── fbmService.ts          # 無在庫出品＋監視Auction紐付け
    │   └── syncService.ts         # 仕入れ可能性の判定→Amazon在庫同期（核）
    └── jobs/monitorJob.ts         # node-cron: 監視サイクル
```

---

## 2. データベーススキーマ

`prisma/schema.prisma` を参照。

| テーブル | 役割 | 主なカラム |
|---|---|---|
| **Product** | Amazon 無在庫出品（SKU 単位） | `asin`, `sku(unique)`, `productType`, `purchasePrice`, `procurementShipping`, `otherCost`, `targetMargin`, `sellPrice`, **`maxSourcePrice`**, `quantity`, `listingState` |
| **Auction** | 監視対象ヤフオク（Product と 1:1） | `yahooAuctionId(unique)`, `status`, `currentPrice`, `endTime`, `checkFailCount`, `active` |
| **SyncLog** | 同期の監査ログ | `auctionStatus`, `reason`, `action`, `from/toQuantity`, `spapiStatus` |
| **Setting** | 既定利益率・手数料率等 | `key`, `value` |

設計判断：

- **Product ⇔ Auction は 1:1**。「Amazon の SKU/ASIN」と「監視対象オークションID」の紐付けが核。
- **`maxSourcePrice`**（損益分岐となる仕入れ元価格）を保存し、価格超過での「仕入れ不能」を判定する。
- **`checkFailCount`**：取得が一時的に失敗(UNKNOWN)しても即停止しない。連続閾値超で人手確認へ。
- **`SyncLog.reason`** に判定根拠（AUCTION_ENDED / PRICE_OVER_MAX 等）を残し監査可能に。
- **SQLite で開始**し、`provider` と `DATABASE_URL` の差し替えだけで PostgreSQL/MySQL に移行可能。

---

## 3. Amazon SP-API 連携の実装方針

実装：`src/amazon/spapiClient.ts`（認証）、`src/amazon/listings.ts`（出品/在庫）。

### 認証（LWA）

- 2023 以降 SP-API は **AWS SigV4 署名・IAM ロール不要**。LWA の `refresh_token` から `access_token`
  を取得し `x-amz-access-token` ヘッダに載せる。約 1 時間で失効するため**内部でキャッシュ＋自動更新**。
- **`npm run auth:test`** で認証＋疎通だけを単独検証してから全体を起動する運用を推奨。

### 出品登録（PUT / Listings Items API 2021-08-01）— FBM

```
PUT /listings/2021-08-01/items/{sellerId}/{sku}?marketplaceIds=A1VC38T7YXB528
```
- FBM は `fulfillment_availability.fulfillment_channel_code = "DEFAULT"` ＋ `quantity` ＋
  **ハンドリングタイム（`lead_time_to_ship_max_days`）を長め**にして落札→入手の猶予を確保。
- `productType`／`attributes` は `getDefinitionsProductType` のスキーマに合わせて動的生成する。

### 在庫更新（PATCH）

```
PATCH /listings/2021-08-01/items/{sellerId}/{sku}
{ "productType":"PRODUCT",
  "patches":[{ "op":"replace", "path":"/attributes/fulfillment_availability",
    "value":[{ "fulfillment_channel_code":"DEFAULT", "quantity":0 }] }] }
```
- **停止 = quantity 0 / 再開 = quantity 1**。`setOutOfStock()` / `setInStock()` として公開。
- 大量 SKU の一括更新は **Feeds API（JSON_LISTINGS_FEED）**が効率的。
- `DRY_RUN=true` の間は PUT/PATCH を**実行せずログのみ**。429/5xx は指数バックオフ+Retry-Afterで再試行。

---

## 4. ヤフオク! 監視ロジックの実装方針

実装：`src/yahoo/auctionMonitor.ts`。

- Yahoo! オークション公式 API は提供終了のため、**商品ページ取得で状態判定**する。
- 取得は 2 モード：`cheerio`（軽量 HTTP・既定）／`puppeteer`（JS レンダリング必須ページ用）。
- **判定は複数シグナルの多数決**で頑健化：
  - `ENDED`：「このオークションは終了しています」等 ＋ `残り時間/入札する` が無い
  - `CANCELLED`：「削除されました」「出品が取り消され」／ `NOT_FOUND`：404 or 「見つかりません」
  - `ACTIVE`：「残り時間 / 入札する / 即決」／ `UNKNOWN`：判定不能（**在庫を触らない**）
- 価格は JSON-LD → meta → DOM の順でフォールバック抽出（`maxSourcePrice` 判定に使う）。
- **ポライトネス／IPブロック対策**：UA＋連絡先明示、最低間隔＋**±40%ジッタ**、429/503 バックオフ、
  監視対象は「連携済み ID のみ」。`parseAuctionHtml()` は純関数として分離しテスト容易に。

---

## 5. 定期実行タスク（Cron）の実装

実装：`src/jobs/monitorJob.ts`、判定の核は `src/services/syncService.ts`。

- `node-cron` で既定 **20 分おき**（`MONITOR_CRON`）。`active` な Auction を全件取得し、**`p-limit`**
  で同時実行数を絞って巡回。**多重起動防止**フラグ＋**`Promise.allSettled`**で頑健化。
- 判定ロジック（`syncOne` → `decide`）：
  1. ヤフオク状態＋現在価格を取得 → Auction に観測結果を保存
  2. 希望在庫を決定：
     - ENDED / CANCELLED / NOT_FOUND → **0**（消滅＝もう買えない）
     - ACTIVE かつ 現在価格 > `maxSourcePrice` → **0**（利益で買えない）
     - ACTIVE かつ 価格範囲内 → **1**（仕入れ可能）
     - UNKNOWN → 触らない
  3. **希望値と現在値が一致すれば何もしない（冪等）**
  4. 差分があれば Amazon を PATCH → Product 更新 → **SyncLog に理由付きで記録**
  5. 消滅系（ENDED/CANCELLED/NOT_FOUND）なら `Auction.active=false`（価格超過は復帰し得るので監視継続）
- 将来は **BullMQ** に移行し、リトライ・遅延・並列度をキューで制御するとスケールしやすい。

---

## 6. 開発を進める上での注意点

### レート制限・エラーハンドリング

- **SP-API はトークンバケット方式のレート制限**。429/5xx は **指数バックオフ + Retry-After 尊重**で
  再試行（実装済み）。大量更新は **PATCH ではなく Feeds API** に寄せる。
- **UNKNOWN では在庫を触らない**（`checkFailCount` 閾値）。一時的失敗での誤停止＝機会損失、
  誤出品＝在庫なし販売、の両方を防ぐ。連続 UNKNOWN が閾値超で人手確認へ。
- すべての外部呼び出しに **タイムアウト**。失敗は `SyncLog`/pino に構造化ログで残す。
- **秘密情報は `.env`（gitignore 済み）**。`.env.example` のみコミット。

### SP-API 認証の先行検証

- 認証は最も詰まりやすい。**`npm run auth:test`** でトークン取得＋疎通だけを単独検証してから起動する。
- 現行 SP-API は **AWS SigV4/STS/IAM ロール不要**（LWA トークンのみ）。旧来の複雑さはない。

### ヤフオク! スクレイピングの配慮

- 監視は**自分が連携した ID のみ**。全件クロール・高頻度アクセスをしない。UA と連絡先を明示、
  `robots.txt`・利用規約を尊重、間隔を空ける（**±40%ジッタ**＋429/503 バックオフ）。
- 構造変化に備え **多数決判定 + UNKNOWN フォールバック**。壊れたら止めるのではなく人手確認へ。

### Amazon 無在庫(FBM)のアカウント健全性を守る工夫（本ツールの主眼）

- **仕入れ可能性の即時反映**：終了/取消/価格超過を検知したら**最優先で在庫0**にし、「買えない注文」を出さない。
- **監視間隔を詰める**ほど「売れたのに買えない」窓が縮む（負荷とのトレードオフ。`MONITOR_CONCURRENCY`で制御）。
- **ハンドリングタイムを長めに**し、落札→入手の猶予を確保して出荷遅延を防ぐ。
- **下限価格ガード＝`maxSourcePrice`** で赤字での強制仕入れを回避（価格超過は在庫0）。
- **本番投入は社長の Go/NoGo（実 Do）を必須**とし、`DRY_RUN=true` を既定にして検証が済むまで書き込まない。
- ⚠️ 上記はリスクを**下げる**工夫であり、FBM のドロップシッピングポリシー抵触リスクを**消すものではない**。
