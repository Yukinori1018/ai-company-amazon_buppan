---
ticket_id: T-20260821-006
title: SUBAGENT_PROTOCOL §3（納品先）を deliverables 直納に一本化して整合させる
status: todo
assignee: content_creator
priority: medium
created_at: 2026-08-21
updated_at: 2026-08-21
requires_approval: false
labels: [docs]
parent_ticket: T-20260821-001
next_check_at: 2026-08-23
---

## 要件

`workspace/SUBAGENT_PROTOCOL.md` §3 は納品先をローカル/クラウドで分岐させているが、
T-20260821-004 の発注テンプレと `.claude/agents/` 8体の定義は
「`workspace/output/deliverables/<ticket_id>/` に直納＋その場で commit」に一本化した。
保存先がバラけるのが社長の指摘の本体なので、プロトコル本体を後者に揃える。

## タスク分解

- [ ] §3 を deliverables 直納＋commit に一本化（ローカルは必要に応じて秘書が Documents へ複製、の順に）
- [ ] `.claude/agents/*.md` 8体の記述と齟齬がないか確認
- [ ] CLAUDE.md §6「成果物の保管ルール」との整合も確認

## 現在地

未着手

## ログ

- 2026-08-21 todo 起票（T-20260821-004 でヒデアキが範囲外と申告した項目）
