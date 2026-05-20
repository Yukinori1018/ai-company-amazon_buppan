# スキル：Notion チケット同期

秘書が Notion カンバンボードと `workspace/tickets/` を同期する際のプロトコルです。

## 同期方針

- **真実は `workspace/tickets/` のファイル状態**。Notion はその可視化（ミラー）。
- **片方向同期**：リポジトリ → Notion。Notion 側で直接カードを動かしても、リポジトリには反映されない（次回リコンサイル時に Notion 側が上書きされる）。
- 同期は **秘書の責務**。MCP 経由で Notion API を直接呼び出す。

## Notion 側の前提

子会社化時、子会社オーナーが Notion に以下を用意します（詳細は Phase 6 で `docs/notion-setup-guide.md` に整備）。

- Notion データベース 1 つ（カンバンビュー）
- 必須プロパティ：

| Notion プロパティ | 型 | チケット frontmatter |
|------------------|-----|-------------------|
| Name | Title | `title` |
| TicketID | Text（一意） | `ticket_id` |
| Status | Status（todo / doing / waiting / done） | `status` |
| Assignee | Select | `assignee` |
| Priority | Select | `priority` |
| RequiresApproval | Checkbox | `requires_approval` |
| Description | Text | 本文の「要件」セクション |
| CreatedAt | Date | `created_at` |
| UpdatedAt | Date | `updated_at` |

MCP 設定（API トークン、Database ID）も子会社側で `.mcp.json` に注入。親テンプレートにはスタブのみ置きます（Phase 5 で配置）。

## 呼び出しタイミング

| イベント | Notion 側のアクション |
|---------|---------------------|
| チケット新規起票（`todo/` に作成） | カード新規作成、TicketID で一意性確保 |
| 状態遷移（todo → doing 等） | Status プロパティ更新 |
| チケット内容更新（タイトル・担当・優先度等） | 該当プロパティ更新 |
| `done` に移動 | Status を done、`UpdatedAt` 更新 |
| チケット削除（基本しない） | カード削除 |

## エラー時のフォールバック

MCP 呼び出しが失敗した場合：

1. 失敗内容を [../memory/](../memory/) の `notion-sync-errors.md` に追記（タイムスタンプ・チケットID・エラー内容）
2. **チケット自体の処理は止めない**（リポジトリ側を真実として進める）
3. その日のうちに社長に「Notion 同期 N 件失敗、リコンサイル要」と報告
4. 次の機会にリコンサイル実行

## リコンサイル（手動同期）

`workspace/tickets/` 全体を走査して Notion 側を上書き更新する操作。

**実行タイミング:**
- 同期エラーが蓄積した時
- 社長から「Notion とズレてる気がする」と指摘された時
- 月次の定期メンテナンス

**手順:**
1. `workspace/tickets/{todo,doing,waiting,done}/` 配下の全 `.md` を走査
2. 各チケットの frontmatter を読み取り
3. TicketID で Notion 側カードを検索
4. あれば更新、なければ作成
5. Notion 側に存在するが リポジトリにない TicketID は、社長確認の上でアーカイブ
6. 結果サマリ（更新N件・作成M件・要確認K件）を社長に報告

## メモリへの記録対象

- 同期失敗パターン（どのフィールドで何が起きやすいか）
- Notion 側の手動変更が頻発する箇所（同期方針見直しの材料）
- リコンサイル時の差分傾向

→ [../memory/](../memory/) に蓄積。
