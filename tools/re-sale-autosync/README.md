# Re-Sale AutoSync（FBA仕入れパイプライン）

即時仕入れ（ヤフオク落札）→ 検品 → ラベル貼替（外注）→ FBA 納品 → 出品 の流れを管理し、
Amazon SP-API で FBA 出品する **有在庫**運用の支援ツール。

> **運用モデル（確定）**: 実物を自社で保有し、Amazon 倉庫へ納品して Amazon が自社出品者名義で
> 発送する正規の FBA。**ドロップシッピングポリシーには抵触しません。**
> 無在庫（FBM）前提の「ヤフオク在庫→Amazon在庫 リアルタイム同期」は不要のため廃止しました
> （FBA は在庫を倉庫の実数で管理するため）。詳細は [`docs/DESIGN.md`](docs/DESIGN.md)。
> 既定 `DRY_RUN=true`（Amazon へ書き込まない）。本番切替は少数 SKU で検証してから。

## セットアップ

```bash
cd tools/re-sale-autosync
cp .env.example .env          # 実値を記入（SP-API 認証・DB 等）
npm install
npm run prisma:generate
npm run prisma:migrate        # SQLite に初期スキーマを作成
```

## 認証を先に単独テスト（推奨）

SP-API は認証が最も詰まりやすいので、全体起動の前にここだけ通します。

```bash
npm run auth:test   # LWAトークン取得 → marketplaceParticipations で疎通・権限確認
```

> 現行 SP-API は **AWS SigV4/STS/IAM ロール不要**（LWA トークンのみ）。旧来の複雑さはありません。

## 起動

```bash
npm run dev      # Web/API + パイプラインボード → http://localhost:3000
npm run worker   # 任意/Phase2: FBA在庫・価格監視ワーカー（現状スタブ）
```

## パイプライン段階

`SOURCED(仕入済) → INSPECTED(検品済) → RELABELED(ラベル貼替済) → INBOUND(FBA納品済) → LISTED(出品中) → SOLD_OUT(在庫切れ)`

ボード上で各カードのボタンから 1 段階ずつ前進。`INBOUND` で「FBA出品」を押すと SP-API 出品 → `LISTED`。

## 主なファイル

| 機能 | ファイル |
|---|---|
| 設計書（6セクション） | `docs/DESIGN.md` |
| DB スキーマ | `prisma/schema.prisma` |
| SP-API 認証/出品/検索 | `src/amazon/spapiClient.ts`, `listings.ts`, `catalog.ts` |
| 認証スモークテスト | `src/scripts/testAuth.ts` |
| 価格計算（FBA手数料込み） | `src/services/pricing.ts` |
| パイプライン管理（核） | `src/services/pipelineService.ts` |
| 仕入れ元相場の参照（任意） | `src/yahoo/auctionMonitor.ts` |
| FBA在庫/価格監視（Phase2） | `src/jobs/monitorJob.ts` |
| Web/API + ボード UI | `src/server.ts`, `src/views/index.ejs` |

## API

| メソッド | パス | 用途 |
|---|---|---|
| GET | `/api/amazon/search?asin=` or `?keyword=` | Amazon 商品情報 |
| GET | `/api/source/yahoo/:auctionId` | 仕入れ元(ヤフオク)相場の参照 |
| POST | `/api/price/preview` | FBA手数料込みの利益試算 |
| POST | `/api/products` | 仕入れ登録（SOURCED 起票） |
| POST | `/api/products/:id/advance` | 段階を1つ前進 |
| POST | `/api/products/:id/list` | FBA 出品（INBOUND→LISTED） |

> これは動作の骨格を示す雛形です。SP-API の `attributes`／FBA チャネルコードはマーケットプレイス×
> productType で異なるため、本番では `getDefinitionsProductType` のスキーマに合わせて動的生成してください。
