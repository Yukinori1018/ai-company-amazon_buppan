# メモリ：Notion 同期（マリエ）

## 責務移管（2026-05-29 / T-20260529-001）

- 社長指摘「チケット起票しても Notion To Do が更新されない。マリエをきちんと働かせろ」を受け、**Notion 同期の責務を秘書→庶務マリエに移管**。
- 運用本体は `agents/general_affairs/skills/notion-ticket-sync.md`。

## 同期漏れの根本原因（2点）

1. **ホスト型 MCP**：シェル/フックから直接 Notion API を叩けない（ローカルにトークン無し）。同期はエージェントが MCP を呼ぶ手動作業 → 秘書の片手間で漏れが再発（T-20260520-011 でドキュメント対応したが再発した）。
   - 対策：責務一本化＋ PostToolUse 強制フック（`.claude/hooks/ticket-notion-sync-reminder.sh`）。チケットファイル変更を検知し「未同期で turn を終えるな」と additionalContext で促す。**完全自動化は原理的に不可、強制関数が最善手**。
2. **ブランチ分岐**：クラウドセッションごとに別ブランチ。チケットの真実が複数ブランチに散在し、Notion は累積するためどの単一ブランチとも一致しない。
   - 対策：`/sync-notion`（非破壊リコンサイル）を朝夕ルーティンに組込。Notion 専用カードは削除せず社長に要確認報告。

## 書式の落とし穴（失敗主因）

- 日付：`date:CreatedAt:start` / `date:UpdatedAt:start`（展開キー）。`is_datetime` は 0。
- チェックボックス RequiresApproval：`"__YES__"` / `"__NO__"`（true/false ではない）。
- カード作成の parent は data_source_id `366b0a40-44fa-81ec-8342-000b6d0a25e0`。

## 接続先メモ

- DB「Amazon物販事業 Tickets」= `366b0a40-44fa-8178-8359-d44b4f807458`
- Table view（全件照会）= `?v=366b0a4044fa81dcbb14000c73f916c1`
