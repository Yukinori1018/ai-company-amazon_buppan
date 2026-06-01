# 成果物カタログ × Google スプレッドシート連携方法まとめ

> 作成: 2026-06-01 / 担当: タカシ（IT）＋マリエ（庶務）/ 関連: T-20260601-001・003・004
> このドキュメント自体が「連携テスト（T-20260601-004）」の題材であり、本文がシートに反映されれば連携成功の証明になります。

---

## 1. ひとことで言うと

**リポジトリ内のマスターCSVを「真実」とし、ワンコマンドで Google スプレッドシート（URL固定）へ全置換ミラーする**仕組み。
成果物が増えるたびに秘書が同期コマンドを1回流すだけで、社長のシートが最新になります。

```
deliverables/ の成果物
      │  マリエが棚卸し・要約
      ▼
deliverables-catalog.csv（リポ内＝真実）
      │  python3 scripts/catalog/sync_catalog_to_sheet.py
      ▼  （HTTPS POST：CSV全文）
Apps Script Web App（シートに紐づくスクリプト）
      │  シートを全クリア→全行書き込み（冪等）
      ▼
Google スプレッドシート「成果物カタログ_Amazon物販事業」（URL固定）
```

---

## 2. なぜこの方式（Apps Script Web App）か

3案を比較し、**社長の手間が最小・認証情報をPCに残さない・URLが変わらない・将来クラウドからも叩ける**点で採用。

| 案 | 初期設定の重さ | 認証情報の保管 | クラウド可 | 採否 |
|---|---|---|---|---|
| **A. Apps Script Web App** | 軽（シート内設定のみ） | 置かない（トークンのみ） | ◯ | ✅ 採用 |
| B. gspread + OAuthクライアント | 重（GCPプロジェクト＋client.json） | client.json をローカル保管 | × | 不採用 |
| C. サービスアカウント＋共有 | 中（SAキー作成＋共有） | SA鍵JSONをローカル保管 | × | 不採用 |

---

## 3. 構成ファイル

| ファイル | 役割 |
|---|---|
| `scripts/catalog/catalog_sync.gs` | シート側に貼る Apps Script。POSTを受けシートを全置換 |
| `scripts/catalog/sync_catalog_to_sheet.py` | ローカルからCSVを読みPOSTするヘルパー（標準ライブラリのみ・`--dry-run`対応） |
| `scripts/catalog/.catalog_sync.env` | 接続情報（URL・トークン）。**gitignore対象＝Gitに載らない** |
| `scripts/catalog/.catalog_sync.env.example` | 設定見本 |
| `scripts/catalog/README.md` | 社長の一度きり初期設定（全10手順） |
| `workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv` | マスターCSV（真実） |

---

## 4. セキュリティ設計

- **共有トークン方式**: Web Appのアクセス権は「全員」だが、書き込みには合言葉 `SHARED_TOKEN` が必須。URLを知られても書き込めない。
- トークンはコードに直書きせず、**Apps Scriptの Script Property** と **ローカルの `.env`**（gitignore）に分離保管。
- POSTするのは社長自身のシートに対してのみ。第三者サービスへは一切送らない。

---

## 5. 運用（成果物が増えたとき）

1. マリエがマスターCSVに行を追記（タイトル・内容要約・GitHubリンク等）。
2. 同期: `python3 scripts/catalog/sync_catalog_to_sheet.py`
   - 事前確認したい時: `python3 scripts/catalog/sync_catalog_to_sheet.py --dry-run`
3. シートが最新化（全置換なので重複なし・冪等）。

> クラウド/夜間自走から流す場合は環境変数 `WEBAPP_URL` / `SHARED_TOKEN` を渡せば可。無ければCSV追記までに留め、次のローカル回で同期。

---

## 6. つまずきポイント（実際に踏んだもの）

| 症状 | 原因 | 対処 |
|---|---|---|
| 「Google hasn't verified this app」警告 | 未審査の個人スクリプト全般に出る定型表示 | Advanced → プロジェクトに移動 → 許可（自作・自分のシートなので安全） |
| HTTP 401（ログインHTMLが返る） | デプロイのアクセス権が「全員」でない | デプロイ管理→編集→アクセス「全員」→再デプロイ |
| 新デプロイでURLが変わる | 「新しいデプロイ」は別URLを発行 | コード修正時は「デプロイ管理→編集→新バージョン」でURL固定 |
| `unauthorized` | `.env` と Script Property のトークン不一致 | 両者を同じ値に揃える |

---

## 7. テスト結果（T-20260601-004）

- 2026-06-01 初回疎通: **HTTP 200 / 56行×12列**（T-20260601-003）。
- 本ドキュメントを成果物として追加し、カタログ行を増やした状態で再同期 → 反映を確認（このテストの合格判定）。

---

## 8. 今後の拡張余地（YAGNIで現状見送り）

- 成果物追加を検知して自動同期するフック（`deliverables/` 監視）。
- 夜間自走ルーティンへの組み込み（環境変数経由）。
- 列の自動フォーマット（種別ごとの色分け等）— Apps Script側で拡張可能。
