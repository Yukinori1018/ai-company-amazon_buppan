# スキル：Notion チケット同期（庶務マリエ 運用版）

> **このスキルの責務者は庶務マリエです。** 秘書カズヨはチケットを起票・移動したら、
> ただちに本スキルに従って Notion を更新します（マリエの作業として実行）。
> 大量のリコンサイルは `/sync-notion` でマリエに一括依頼します。

## 0. なぜマリエの責務か

- Notion カンバンは「整理整頓された可視化」そのもの＝庶務の本分。
- 過去、同期を秘書の「片手間」にしていたため漏れが再発（T-20260520-011）。責務を庶務に一本化し、`.claude/hooks/ticket-notion-sync-reminder.sh`（PostToolUse 強制フック）で「未同期で turn を終えない」よう機械的に促す。

## 1. 同期方針

- **真実は `workspace/tickets/` のファイル状態**。Notion はその片方向ミラー（リポジトリ → Notion）。
- Notion 側で直接カードを動かしても、リポジトリには反映されない（次回リコンサイルで Notion 側が上書き）。
- **非破壊原則**：自動同期でカードを削除しない。リポジトリに無い TicketID は社長確認の上でのみアーカイブ。

## 2. 接続先（実値・このリポジトリ専用）

ホスト型 Notion MCP（`notion-*` ツール）経由で操作します。ローカルにトークンは無いので、シェルスクリプトからは書けません。**必ず MCP ツールで操作**します。

| 対象 | 値 |
|------|----|
| データベース名 | `Amazon物販事業 Tickets` |
| Database ID | `366b0a40-44fa-8178-8359-d44b4f807458` |
| Data Source ID（カード作成の parent） | `366b0a40-44fa-81ec-8342-000b6d0a25e0` |
| Table view（全件照会用） | `https://www.notion.so/366b0a4044fa81788359d44b4f807458?v=366b0a4044fa81dcbb14000c73f916c1` |
| Kanban view | グループ化＝Status |
| 親ページ | `クロードコード ToDo進捗`（`365b0a40-44fa-8000-addb-c5404f51685b`） |

## 3. プロパティ対応表と書式の落とし穴

| Notion プロパティ | 型 | frontmatter | 書き込み時の書式（重要） |
|------------------|-----|-------------|------------------------|
| Name | Title | `title` | 文字列。`"T-XXXX タイトル"` 形式推奨（カードでも ID が見える） |
| TicketID | Text | `ticket_id` | 文字列。**同期キー** |
| Status | Select | `status` | `todo`/`doing`/`waiting`/`done` のいずれか |
| Assignee | Select | `assignee` | `secretary`/`researcher`/`planner`/`simulator`/`accounting`/`legal`/`general_affairs`/`content_creator`/`it_engineer`/`owner` |
| Priority | Select | `priority` | `low`/`medium`/`high` |
| RequiresApproval | Checkbox | `requires_approval` | **`"__YES__"` / `"__NO__"`**（true/false ではない） |
| Description | Text | 本文「要件」要約 | 文字列 |
| CreatedAt | Date | `created_at` | **`"date:CreatedAt:start": "YYYY-MM-DD"`**（展開キー） |
| UpdatedAt | Date | `updated_at` | **`"date:UpdatedAt:start": "YYYY-MM-DD"`**、必要なら `"date:UpdatedAt:is_datetime": 0` |
| Labels | Multi-select | `labels` | JSON 配列文字列。未定義ラベルは事前に選択肢追加が必要 |
| ParentTicket | Text | `parent_ticket` | 文字列（空欄＝独立） |

> 日付・チェックボックスは「展開キー／特殊値」を使わないと反映されません。ここが過去の同期失敗の主因。

> **Notion に存在しないリポジトリ専用フィールド**（`next_check_at`・`related_tickets` 等）は同期対象外。これらだけを変更し Status も変わらない編集では Notion 書き込みは不要（PostToolUse フックは保守的に発火するが、同期不要なら「Notion プロパティに変化なし」と判断してスキップしてよい）。

## 4. 呼び出しタイミング（厳守）

| イベント | アクション | 即時性 |
|---------|-----------|---|
| **新規起票**（`todo/` 作成） | `notion-create-pages` でカード作成 | ★ 起票と同じ turn |
| **状態遷移**（todo→doing 等） | 該当カードの Status・UpdatedAt 更新 | ★ 移動と同じ turn |
| 内容更新（タイトル/担当/優先度） | 該当プロパティ更新 | 同じセッション |
| `done` へ移動 | Status=done、UpdatedAt 更新、本文に結果要約 | ★ 完了と同じ turn |

PostToolUse フックが上記イベントを検知してリマインドします。リマインドが出たら**その turn 内で**同期を完了させること。

## 5. 具体レシピ（MCP）

### 5-1. 新規カード作成
`notion-create-pages`:
```
parent: { "type": "data_source_id", "data_source_id": "366b0a40-44fa-81ec-8342-000b6d0a25e0" }
pages: [{
  properties: {
    "Name": "T-20260529-001 タイトル",
    "TicketID": "T-20260529-001",
    "Status": "todo",
    "Assignee": "general_affairs",
    "Priority": "high",
    "RequiresApproval": "__NO__",
    "Description": "要件の1〜2行要約",
    "date:CreatedAt:start": "2026-05-29",
    "date:UpdatedAt:start": "2026-05-29",
    "ParentTicket": ""
  },
  content: "## 結果要約\n（todo時はブロッカー/着手後の流れを3〜10行）"
}]
```

### 5-2. 既存カードの状態更新
1. `notion-query-database-view`（Table view URL）で全件取得し、`TicketID` 一致のカードの `url`（page id）を特定。
2. `notion-update-page`（`command: "update_properties"`）:
```
page_id: <該当カードの page id>
properties: {
  "Status": "doing",
  "date:UpdatedAt:start": "2026-05-29"
}
```
3. `done` 化や waiting 化では本文の `## 結果要約` も `update_content`／`insert_content` で最新化。

### 5-3. カード本文「結果要約」
カンバンのカード面にはプロパティしか出ない。**ページ本文末尾に `## 結果要約`** を置き、社長が開けば状況が一目で分かるようにする（done=成果/コミット、waiting=納品済&待ち事項、doing=現在地&次の手、todo=ブロッカー）。

## 6. リコンサイル（`/sync-notion`）

`workspace/tickets/{todo,doing,waiting,done}/` 全 `.md` を走査 → TicketID で突合 → 無ければ作成・あれば更新。**非破壊**（Notion 専用カードは削除せず社長へ要確認として報告）。手順詳細は `.claude/commands/sync-notion.md`。

朝・夕のルーティンで軽くリコンサイルし、ブランチ分岐由来のドリフトを自己修復する。

## 7. エラー時のフォールバック

1. 失敗内容を `agents/general_affairs/memory/notion-sync-errors.md` に追記（日時・TicketID・エラー）。
2. **チケット処理は止めない**（リポジトリを真実として前進）。
3. その日のうちに「Notion 同期 N 件失敗、リコンサイル要」と秘書経由で社長報告。

## 8. メモリへの記録対象

- 同期失敗パターン（特に日付・チェックボックスの書式ミス）
- Notion 側の手動変更が頻発する箇所
- リコンサイル時の差分傾向（ブランチ分岐由来か、同期漏れか）

→ `agents/general_affairs/memory/` に蓄積。
