---
ticket_id: T-20260529-001
title: Notion 同期をマリエ責務化＋起票/移動の即時同期を強制する仕組み
status: done
assignee: general_affairs
priority: high
created_at: 2026-05-29
updated_at: 2026-05-29
requires_approval: false
labels: [notion, infrastructure, workflow, general_affairs]
parent_ticket: ""
---

## 要件

社長指摘「Notion の To Do がチケット起票しても更新されていない。マリエをきちんと働かせて、起票/移動のたびに即座に Notion を更新せよ」。同期漏れの再発（T-20260520-011 で一度ドキュメント対応済だが再発）を、責務の明確化＋強制フックで根治する。

## タスク分解

- [x] Notion 同期の責務を「秘書」→「庶務（マリエ）」に変更（CLAUDE.md §0.1/§2/§5/§6、schema doc、agent.md）
- [x] マリエ用の運用スキル `agents/general_affairs/skills/notion-ticket-sync.md` を新設（DB ID・MCP 呼び出しレシピ含む実戦版）
- [x] 秘書側スキルはマリエへのポインタに縮約（既存リンク維持）
- [x] PostToolUse フックで「チケットファイル変更を検知→即時 Notion 同期を促す」強制機構を追加（`.claude/hooks/ticket-notion-sync-reminder.sh`、settings.json 登録、発火確認済）
- [x] `/sync-notion` リコンサイルコマンドを新設（マリエ実行、非破壊）
- [x] ルーティン（朝・夕）にリコンサイルを組み込み、ドリフト自己修復
- [x] 現状ドリフトの調査と本チケットの Notion 即時反映
- [x] 社長へ根本原因（ブランチ分岐）の判断仰ぎ → **A 採択**（現状維持＋朝夕 /sync-notion で自己修復、Notion 専用カードは温存）

## 現在地

完了。仕組みは実装・実機発火確認済。社長は原因②（ブランチ分岐）対応として A を採択。本チケットも状態遷移のたびに Notion へ即同期（todo→doing→done）し、強制フックの動作を実証した。

## 根本原因（調査結果）

1. **ホスト型 MCP のためシェルから直接 Notion を書けない** → 同期はエージェントが MCP を呼ぶ手動作業。秘書の「片手間」だったため漏れが再発。
   → 対策：責務をマリエに一本化＋ PostToolUse 強制フックで「未同期で turn を終えない」よう機械的に促す。
2. **ブランチ分岐（クラウドセッションごとに別ブランチ）** → チケットファイルの真実が複数ブランチに散在。Notion は各ブランチの更新を累積するため、どの単一ブランチとも一致しない。実際、本ブランチ（05-22 main 基点）は 05-25/05-27 の更新（T-003/005/21-001/22-004 の進行、T-20260527-001/002 の新規）を持たず、Notion の方が「先行」していた。
   → 対策：`/sync-notion` を朝夕ルーティンに組み込み非破壊リコンサイル。ただし「どのブランチを正にするか」は社長判断が必要。

## ログ

- 2026-05-29 todo 起票（社長指摘を受領、ただちに起票）
- 2026-05-29 doing 着手。原因2点を特定。責務移管・スキル新設・強制フック・/sync-notion・ルーティン組込を実装。フック発火を実機確認。本チケットを Notion へ即時同期。
- 2026-05-29 社長が原因②対応に A を採択。done クローズ、Notion カードも done へ同期。
