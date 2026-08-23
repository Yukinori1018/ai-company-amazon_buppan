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
| Amazon 商品データ | **Keepa 公式 MCP**（下記の専用セクション参照） | IT エンジニア、リサーチャー |

---

## セキュリティ — シークレットの置き方

### 前提：このリポジトリは PUBLIC で、30分ごとに自動 push されます

`.claude/scripts/github-sync.sh` が30分間隔で `git add -A` → commit → push します。**リポジトリ内に平文のキーを置くと、`.gitignore` の1行が消えるか、パスが変わるか、`git add -f` を打った瞬間に全世界へ公開され、Git 履歴に永久に残ります**（履歴からの除去は force push ＝ CLAUDE.md §4.1 該当で、事故後の対処コストが極めて高い）。

したがって方針は「`.gitignore` を信じる」ではなく、**「キーをリポジトリの物理的な外に出し、かつ平文で存在させない」**とします。

### キーを設定に持たせる3つの方法（下ほど安全）

| 方法 | 書き方 | 評価 |
|------|--------|------|
| ① リテラル直書き | `"Authorization": "Bearer sk-xxxx"` | **リポジトリ内では禁止。** `~/.claude.json`（ユーザースコープ）ならリポ外なので許容 |
| ② 環境変数の展開 | `"Authorization": "Bearer ${MY_API_KEY}"` | 可。`.mcp.json` と `~/.claude.json` の両方で `${VAR}` / `${VAR:-default}` が展開される（`command` / `args` / `env` / `url` / `headers` が対象）。ただしキーはシェル設定に平文で残る |
| ③ `headersHelper` | `"headersHelper": "/path/to/auth.sh"` | **推奨。** 接続時に外部コマンドを実行し、stdout の JSON をヘッダとして使う。macOS キーチェーンと組み合わせれば**平文がどこにも存在しない** |

`headersHelper` の契約：stdout に JSON オブジェクトを1個出力。エラーは stderr へ（stdout を汚すと JSON パースが壊れる）。タイムアウト10秒、キャッシュなし、セッション開始時と再接続時に実行。401/403 を受けると自動で再実行＋1回リトライ。**プロジェクト/ローカルスコープでは trust ダイアログ承認後にしか動かないため、ユーザースコープの利用を推奨します。**

### スコープと保存先

| スコープ | 保存先 | リポ外か |
|---|---|---|
| `--scope local`（既定） | `~/.claude.json` の `projects["<path>"].mcpServers` | ○ |
| `--scope project` | リポジトリ直下の `.mcp.json` | **×（リポ内）** |
| `--scope user` | `~/.claude.json` のルート `mcpServers` | ○ |

**シークレットを含む MCP は `--scope user` を既定にしてください。**リポジトリの外に出るため、公開 push の射程から構造的に外れます。

### その他

- `.mcp.json` は **必ず `.gitignore`** に入れる（このテンプレでは既に除外済み。`.gitignore:8`）
- 各種トークンは **最小権限** で発行
- 不要になった MCP は削除し、サービス側のトークンも revoke
- 機密データを扱う MCP（メール本文・契約書 PDF 等）の追加時は、CLAUDE.md §4.1「機密情報の外部送信」該当ケースを再確認
- **キーを Notion 等の第三者 SaaS に保管しないでください。** MCP のヘッダは接続時に上記①②③のいずれかでしか解決できず、「SaaS から読む」経路は存在しません。実現するには人間/AI が毎回コピペするか、別の秘密（SaaS のトークン）を平文で置く必要があり、いずれも安全性と手間の両方で劣ります。詳細は `workspace/output/deliverables/T-20260824-001/keepa-mcp-setup.md` §5。

---

## Keepa 公式 MCP サーバ（`https://keepa.com/mcp`）

Amazon の価格履歴・Buy Box・出品者・Product Finder 等を AI から直接引ける公式ホステッドサーバです。**新規契約・追加課金はありません**（既存 Keepa API サブスクのアクセスキーで認証し、通常の API と同じトークンを消費します）。

**設計・手順の全文は `workspace/output/deliverables/T-20260824-001/keepa-mcp-setup.md`（T-20260824-001 / タカシ）を参照してください。** 以下は要約です。

### 導入（社長のみ。キーを触るのはステップ1の1回だけ）

```bash
# 1. キーをキーチェーンへ（-w を値なしで末尾に置くと非表示プロンプト＝シェル履歴に残らない）
security add-generic-password -s keepa-api-key -a keepa -U -w

# 2. ヘルパースクリプトを配置（キーは含まれない）
mkdir -p ~/.claude/scripts
cp workspace/output/deliverables/T-20260824-001/keepa-auth.sh.template ~/.claude/scripts/keepa-auth.sh
chmod 700 ~/.claude/scripts/keepa-auth.sh

# 3. ユーザースコープで登録（リポ外の ~/.claude.json に入る）
claude mcp add-json --scope user keepa \
  '{"type":"http","url":"https://keepa.com/mcp","headersHelper":"'"$HOME"'/.claude/scripts/keepa-auth.sh"}'
```

キーのローテーションはステップ1の再実行（`-U` が上書き）だけで済み、MCP 設定は触りません。

### 運用上の注意

- **トークンを消費します。** 夜間自走やループ処理から無制限に呼ばせないでください。既存の夜間スキャン（T-20260803-001 系）と食い合います。用途は「対話中の単発調査」に限定するのが安全です。
- **大量取得は従来どおり REST API を直に叩くスクリプト側で。** Keepa 公式も「プログラムから使うなら REST API を直接使え。MCP の応答は言語モデル向けに整形してある」と明記しています。
- **クラウド／モバイルのセッションでは使えません。** Claude Code のクラウド環境には専用のシークレットストアがまだ無く、公式が「環境変数はその環境を使う人なら誰でも読める」と警告しているためです。Keepa MCP は「Mac のローカル回で使う道具」と位置づけます。

---

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| MCP サーバが起動しない | `command` / `args` の typo、Node.js バージョン、`npx` の動作確認 |
| 認証エラー | トークン形式、有効期限、権限スコープ、env 変数名のキー一致 |
| エージェントが MCP を呼ばない | skills 文書で「いつ使うか」を明示しているか確認 |
| Claude Code が `.mcp.json` を認識しない | 再起動、ファイル配置パス（リポジトリルート）、JSON 構文 |
