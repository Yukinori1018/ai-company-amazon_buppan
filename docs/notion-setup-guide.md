# Notion カンバン セットアップ手順

子会社化したリポジトリで Notion 連携を有効化する手順です。所要時間 15〜20 分。

> DB のプロパティ定義（型・選択肢の正式値）は [notion-board-schema.md](notion-board-schema.md) を参照しながら進めてください。

## 全体像（5ステップ）

1. Notion でデータベースを作成
2. プロパティとカンバンビューを整える
3. Integration Token を発行
4. データベースに Integration を接続して Database ID を取得
5. `.mcp.json` に設定を投入して動作確認

---

## Step 1: データベースを作成

1. Notion で新規ページを作成（任意のワークスペース内）
2. 本文の入力欄に `/database` と入力
3. 候補から **Database - Full page** を選択
4. ページタイトルを `{{ 事業名 }} Tickets` 等に設定

## Step 2: プロパティを整える

[notion-board-schema.md §2](notion-board-schema.md#2-必須プロパティ) の表に従い、プロパティを1つずつ追加します。

1. デフォルトで作られている `Name`（Title型）はそのまま使う
2. 表の上から順にプロパティを追加（型に注意：Text / Status / Select / Checkbox / Date / Multi-select）
3. **Status プロパティ**は値を `todo / doing / waiting / done` の順で登録（色は schema 推奨値）
4. **Assignee プロパティ**は `secretary / accounting / legal / general_affairs / content_creator` を登録
5. **Priority プロパティ**は `low / medium / high` を登録

### カンバンビューの設定

1. ページ上部のビュー切替で **+ New view → Board** を選択
2. **Group by** を `Status` に設定
3. 各列に todo / doing / waiting / done が並ぶことを確認

## Step 3: Integration Token を発行

1. ブラウザで [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) を開く
2. **+ New integration** をクリック
3. 名前を `{{ 事業名 }} MCP` 等に設定、ワークスペースを選択、Type は **Internal**
4. **Submit** で作成
5. 表示された **Internal Integration Secret**（`secret_...` で始まる文字列）をコピー
   - **このトークンは一度しか表示されない**ので、安全な場所に控える
6. 必要な権限を確認（Read content / Update content / Insert content）。

## Step 4: Integration を DB に接続し、Database ID を取得

### 接続

1. Step 1 で作った Notion DB ページに戻る
2. 右上の **`...`** メニュー → **Connections** → **+ Add connections**
3. Step 3 で作った Integration を選び **Confirm**

### Database ID の取得

1. DB ページの URL をブラウザのアドレスバーからコピー
   - 形式: `https://www.notion.so/<workspace>/<DATABASE_ID>?v=<VIEW_ID>`
2. `<DATABASE_ID>` 部分（ハイフンなしの32文字）を抽出
   - 例：URL が `.../abc123def4567890abc123def4567890?v=...` なら `abc123def4567890abc123def4567890` が Database ID

## Step 5: `.mcp.json` を設定して動作確認

### 設定ファイルの作成

```bash
cp .mcp.json.example .mcp.json
```

`.mcp.json` をエディタで開き、プレースホルダーを埋めます。

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer ntn_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\", \"Notion-Version\": \"2022-06-28\"}",
        "NOTION_DATABASE_ID": "abc123def4567890abc123def4567890"
      }
    }
  }
}
```

**重要な書き換え方:**
- `OPENAPI_MCP_HEADERS` の値は **JSON 文字列**（クォートエスケープ済み）。`Bearer` の後ろのトークン部分だけを Step 3 でコピーした値に置き換える
- ダブルクオートのエスケープ（`\"`）を消さないこと（消すと JSON パースが壊れる）
- `NOTION_DATABASE_ID` は Step 6 で取得した 32 文字の ID をそのまま

> `.mcp.json` は `.gitignore` 対象です。誤ってコミットしないでください。
> Notion 公式 MCP サーバ（`@notionhq/notion-mcp-server`）は `OPENAPI_MCP_HEADERS` 形式を要求します。`NOTION_API_KEY` 単体では認証されません。

### 動作確認

1. Claude Code を再起動（MCP 設定の読み込みのため）
2. 秘書に依頼：「Notion 連携の動作テストとして、テスト用チケットを1件起票してください」
3. 期待される動き：
   - `workspace/tickets/todo/` に `T-YYYYMMDD-001_test.md` のようなファイルが作られる
   - Notion カンバンの **todo** 列にカードが新規作成される
4. もう一度依頼：「テストチケットを done に動かしてください」
5. 期待：ファイルが `done/` に移動 + Notion カードも `done` 列に移動

---

## トラブルシューティング

| 症状 | 確認ポイント |
|------|------------|
| MCP サーバが起動しない | `npx` の動作確認、Node.js バージョン、`.mcp.json` の JSON 構文 |
| 接続成功するがカードが作られない | DB に Integration が **Connections** で接続されているか |
| 「Database not found」エラー | Database ID の桁数（32文字）と DB の権限を確認 |
| カードは作られるが Status が空 | Status プロパティの値が `todo/doing/waiting/done` に一致しているか（大文字小文字含めて） |
| ファイルと Notion がズレた | 秘書に「リコンサイル実行」を依頼。手順は [agents/secretary/skills/notion-ticket-sync.md](../agents/secretary/skills/notion-ticket-sync.md#リコンサイル手動同期) |

---

## セキュリティ

- `NOTION_API_KEY` は絶対に Git にコミットしない（`.mcp.json` は gitignore 済）
- 不要になった Integration は notion.so/my-integrations から削除
- トークン漏洩疑いがあれば即時 revoke して再発行
