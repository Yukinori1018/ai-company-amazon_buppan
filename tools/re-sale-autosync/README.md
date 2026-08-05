# Re-Sale AutoSync（無在庫 / FBM 専用）

ヤフオク! を仕入れ元にした Amazon 無在庫(FBM)出品で、**「Amazonで売れたのに仕入れられない」注文**を
発生させないためのツール。仕入れ元の在庫・価格を定期監視し、**仕入れ不能になった瞬間に Amazon 在庫を 0**
にして、キャンセル＝アカウント健全性低下/停止のリスクを下げる。

> **有在庫(FBA)はこのアプリの対象外**です。FBA は「Keepa＋Claude で商品検索 → 社長が選定 →
> メーカーへ問い合わせて仕入れ → FBA 販売」という手動＋Claude 支援の運用で進めます（アプリ不要）。
>
> ⚠️ **法務注意**: FBM（ヤフオク→Amazon 無在庫）は Amazon のドロップシッピングポリシーに抵触する
> リスクが残ります。本ツールは在庫0化の即時性でリスクを下げますが、ゼロにはできません。詳細は
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
npm run dev      # Web/API + 監視ダッシュボード → http://localhost:3000
npm run worker   # 監視ワーカー（cron 常駐・既定20分おき）
```

## 使い方

1. **リサーチ&出品**：ASIN・SKU・productType・**ヤフオクID**・想定落札価格などを入れて「出品＋監視開始」。
   販売価格と**損益分岐となる仕入れ価格(`maxSourcePrice`)**が自動計算され、DB に SKU⇔オークションIDを保存。
2. **監視**：ワーカーがオークションを巡回し、
   - 終了/取消/ページ消滅 → **在庫0**（その一点物はもう買えない）
   - 現在価格 > 損益分岐 → **在庫0**（利益で買えない）
   - 価格範囲内で開催中 → **在庫1**
   - 取得不能(UNKNOWN) → **触らない**（誤停止/誤出品を防ぐ）
3. 監視間隔（`.env` の `MONITOR_CRON`）を詰めるほど「売れたのに買えない」窓が縮みます。

## 主なファイル

| 機能 | ファイル |
|---|---|
| 設計書（6セクション） | `docs/DESIGN.md` |
| DB スキーマ | `prisma/schema.prisma` |
| SP-API 認証/出品/在庫/検索 | `src/amazon/spapiClient.ts`, `listings.ts`, `catalog.ts` |
| 認証スモークテスト | `src/scripts/testAuth.ts` |
| 価格＋損益分岐計算 | `src/services/pricing.ts` |
| 出品＋監視紐付け | `src/services/fbmService.ts` |
| 仕入れ可能性の同期（核） | `src/services/syncService.ts` |
| ヤフオク監視 | `src/yahoo/auctionMonitor.ts` |
| Cron ワーカー | `src/jobs/monitorJob.ts` |
| Web/API + UI | `src/server.ts`, `src/views/index.ejs` |

## API

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/amazon/search?asin=` or `?keyword=` | Amazon 商品情報 |
| GET | `/api/source/yahoo/:auctionId` | ヤフオク状態/相場の取得 |
| POST | `/api/price/preview` | 販売価格＋損益分岐仕入れ価格の試算 |
| POST | `/api/list` | 無在庫出品＋監視紐付け |
| POST | `/api/monitor/run` | 監視を今すぐ1周 |

> これは動作の骨格を示す雛形です。SP-API の `attributes` はマーケットプレイス×productType で
> 異なるため、本番では `getDefinitionsProductType` のスキーマに合わせて動的生成してください。
