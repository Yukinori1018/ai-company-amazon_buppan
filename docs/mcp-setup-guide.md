# MCP 追加ガイド（Notion 以外を足したいとき）

子会社化したリポジトリで、Notion 以外の MCP（Gmail、Slack、GitHub 等）を追加する手順です。

## MCP とは

**Model Context Protocol** の略。Claude などの AI に「外部の道具」を持たせる仕組みです。MCP サーバは Gmail / Notion / Slack / ローカルファイル等の操作を AI から呼び出せる API として公開します。

各エージェントの `agent.md` や `skills/` に「この道具をいつ・どう使うか」を書き、`.mcp.json` で道具自体を接続します。

> 例えるなら：**スキルがマニュアル、MCP が道具**。秘書に「メールを送って」と頼んだとき、メールという道具（Gmail MCP）と使い方マニュアル（skills 内のドキュメント）の両方が揃って初めて実行できます。

## 親テンプレートと MCP の関係

| 項目 | 親テンプレート | 子会社化時に追加 |
|------|--------------|---------------|
| Notion MCP（チケット同期） | ✓ スタブ同梱 | 認証情報を埋めるだけ |
| Gmail MCP | — | 必要なら子会社側で追加 |
| Slack MCP | — | 必要なら子会社側で追加 |
| その他 | — | 必要なら子会社側で追加 |

**理由:** 事業ごとに必要な道具が違うため。Amazon物販ならスプレッドシート系、コンサル業ならカレンダー系、と最適な組み合わせが異なります。

---

## MCP 追加の基本フロー（5ステップ）

### Step 1: 使いたい MCP サーバを探す

- 公式の MCP サーバリスト（Model Context Protocol の公式ドキュメントを検索）
- コミュニティ実装（GitHub で `mcp-server` を検索）
- 主要ツールはほぼ公式または有志実装あり（Gmail / Slack / GitHub / Linear / Drive 等）

### Step 2: 認証情報を取得

道具に応じて：

| サービス | 必要なもの |
|---------|----------|
| Gmail | Google OAuth Client ID/Secret、または App Password |
| Slack | Bot Token (`xoxb-...`) |
| GitHub | Personal Access Token |
| Linear | API Key |

各サービスの「インテグレーション」「API」設定画面から取得します。**最小権限**で発行するのが原則。

### Step 3: `.mcp.json` にサーバを追加

既存の `.mcp.json` に `mcpServers` 配下にエントリを追加します。

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer ntn_...\", \"Notion-Version\": \"2022-06-28\"}",
        "NOTION_DATABASE_ID": "..."
      }
    },
    "gmail": {
      "command": "npx",
      "args": ["-y", "@example/gmail-mcp-server"],
      "env": {
        "GMAIL_CLIENT_ID": "...",
        "GMAIL_CLIENT_SECRET": "..."
      }
    },
    "slack": {
      "command": "npx",
      "args": ["-y", "@example/slack-mcp-server"],
      "env": {
        "SLACK_BOT_TOKEN": "xoxb-..."
      }
    }
  }
}
```

> 各 MCP サーバの env 名は実装依存です。Notion は `OPENAPI_MCP_HEADERS`（JSON 文字列）を要求。他サーバの正確な env 名は各 README を参照してください。

> `command` と `args` は各 MCP サーバの README に従って正確に書く。env キー名も同様。

### Step 4: 使うエージェントの skills/ にマニュアルを追加

道具を持たせたいエージェントの `skills/` に、その道具の使い方を書きます。例えば「秘書が Gmail で社長宛にレポートを送る」なら：

`agents/secretary/skills/gmail-report.md` を新規作成して、以下を記述：

- どんなタイミングで送るか
- 件名・宛先・本文のフォーマット
- 送信前確認が必要なケース（→ CLAUDE.md §4.1 の外部発信に該当するため、原則 `waiting/` 経由）
- 失敗時のフォールバック

エージェントの `agent.md` の「スキル一覧」セクションにもリンクを追加。

### Step 5: 再起動して動作確認

1. Claude Code を再起動（`.mcp.json` の再読み込み）
2. 該当エージェントに「○○を使ってXXしてください」と依頼
3. 失敗時は `agents/<role>/memory/mcp-errors.md` 等に状況を記録

---

## よく使われる MCP の例

すべて公式または有志実装あり。導入時は各リポジトリの README で最新の起動コマンド・必要権限を確認してください。

| 用途 | サーバ例 | 主な活用エージェント |
|------|---------|------------------|
| メール送受信 | Gmail MCP | 庶務、秘書 |
| チャット通知 | Slack MCP | 庶務、秘書 |
| Issue/PR 管理 | GitHub MCP | コンテンツ制作、庶務 |
| カレンダー | Google Calendar MCP | 庶務、秘書 |
| ファイルストレージ | Google Drive MCP / Dropbox MCP | 全エージェント |
| データベース | Postgres MCP / SQLite MCP | 経理、コンテンツ制作 |
| Webブラウジング | Puppeteer MCP / Playwright MCP | コンテンツ制作（リサーチ） |

---

## セキュリティ

- `.mcp.json` は **必ず `.gitignore`** に入れる（このテンプレでは既に除外済み）
- 各種トークンは **最小権限** で発行
- 不要になった MCP は `.mcp.json` から削除し、サービス側のトークンも revoke
- 機密データを扱う MCP（メール本文・契約書 PDF 等）の追加時は、CLAUDE.md §4.1「機密情報の外部送信」該当ケースを再確認

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| MCP サーバが起動しない | `command` / `args` の typo、Node.js バージョン、`npx` の動作確認 |
| 認証エラー | トークン形式、有効期限、権限スコープ、env 変数名のキー一致 |
| エージェントが MCP を呼ばない | skills 文書で「いつ使うか」を明示しているか確認 |
| Claude Code が `.mcp.json` を認識しない | 再起動、ファイル配置パス（リポジトリルート）、JSON 構文 |
