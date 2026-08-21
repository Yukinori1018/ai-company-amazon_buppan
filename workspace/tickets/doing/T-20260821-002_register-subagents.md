---
ticket_id: T-20260821-002
title: サブエージェント9体を .claude/agents/ に実体登録＋委譲チェックフック
status: doing
assignee: it_engineer
priority: high
created_at: 2026-08-21
updated_at: 2026-08-21
requires_approval: false
labels: [tooling, hooks]
parent_ticket: T-20260821-001
next_check_at: 2026-08-22
---

## 要件

「担当に振る」を1コールで実行できる状態にし、振らなかったら気づける仕組みを入れる。

## タスク分解

- [ ] `.claude/agents/<role>.md` を9体作成（researcher/planner/simulator/accounting/legal/general_affairs/content_creator/it_engineer/secretary は不要）
- [ ] 各定義に SUBAGENT_PROTOCOL の要点（成果物の保存先・memory記録義務）を埋め込む
- [ ] UserPromptSubmit フックで「担当宣言」をリマインド
- [ ] 動作確認

## 現在地

未着手

## ログ

- 2026-08-21 doing 起票
