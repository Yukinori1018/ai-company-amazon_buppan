# Notion カンバンボード DB スキーマ仕様

`workspace/tickets/` と同期する Notion データベースの正式仕様です。子会社化時、子会社オーナーはこの仕様通りに Notion 側にデータベースを作成してください。

## 1. データベース概要

- **タイプ:** データベース（カンバンビューを有効化）
- **デフォルトビュー:** カンバン、グループ化＝Status
- **用途:** `workspace/tickets/` の状態を可視化するミラー

## 2. 必須プロパティ

| Notion プロパティ名 | 型 | 必須 | チケット frontmatter | 備考 |
|------------------|------|------|-------------------|------|
| Name | Title | ✓ | `title` | カードのタイトル |
| TicketID | Text | ✓ | `ticket_id` | 一意。同期キー |
| Status | Status | ✓ | `status` | カンバンの列分け |
| Assignee | Select | ✓ | `assignee` | 担当エージェント |
| Priority | Select | ✓ | `priority` | 優先度 |
| RequiresApproval | Checkbox | ✓ | `requires_approval` | 社長承認必須フラグ |
| Description | Text | — | 本文「要件」 | 要件の要約 |
| CreatedAt | Date | ✓ | `created_at` | 起票日 |
| UpdatedAt | Date | ✓ | `updated_at` | 最終更新日 |
| Labels | Multi-select | — | `labels` | 任意のラベル |

## 3. 選択肢の値

### Status（必須・固定値）

| 値 | 色（推奨） |
|----|----------|
| todo | gray |
| doing | blue |
| waiting | yellow |
| done | green |

### Assignee（固定値、子会社化時に追加可）

| 値 | 対応エージェント |
|----|---------------|
| secretary | 秘書（カズヨ） |
| accounting | 経理（ハジメ） |
| legal | 法務（ハルオ） |
| general_affairs | 庶務（マリエ） |
| content_creator | コンテンツ制作（ヒデアキ） |

### Priority（固定値）

| 値 | 色（推奨） |
|----|----------|
| low | gray |
| medium | blue |
| high | red |

## 4. Notion 側での作成手順（参考）

1. Notion でワークスペース内に新規ページを作成
2. `/database` で「Database - Full page」を挿入
3. データベース名を `{{ 事業名 }} Tickets` 等に設定
4. 上記「必須プロパティ」を1つずつ追加（型と選択肢を正確に揃える）
5. 新規ビューで「Board」を選択 → グループ化を `Status` に設定
6. Notion インテグレーション（Internal Integration Token）を発行し、このデータベースに「接続」
7. Database URL から Database ID を抽出（URL の `https://www.notion.so/<workspace>/<DATABASE_ID>?v=...` の `<DATABASE_ID>` 部分）
8. ルートの `.mcp.json.example` を `.mcp.json` にコピーし、`OPENAPI_MCP_HEADERS` 内の Bearer トークンと `NOTION_DATABASE_ID` を埋める（公式 MCP サーバは JSON 文字列形式のヘッダー指定を要求します）

詳細な手順は [docs/notion-setup-guide.md](notion-setup-guide.md) を参照。

## 5. 同期の真実

- **真実は `workspace/tickets/` のファイル状態**。Notion はミラー（片方向同期）。
- 同期プロトコル: [agents/secretary/skills/notion-ticket-sync.md](../agents/secretary/skills/notion-ticket-sync.md)
- ドリフト発生時のリコンサイル手順も同上ファイル参照
