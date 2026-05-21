---
ticket_id: T-20260520-011
title: Notion 粒度問題対応＋同期ルール／テンプレ更新
status: done
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: false
labels: [notion, infrastructure, workflow]
parent_ticket: ""
---

## 要件

社長から「Notion の ToDo 粒度が大きすぎて進捗が見えない。依頼したタスクが反映されてない」との指摘。原因は2点：(1) チケット粒度が大きすぎる（1チケットが1〜2週間規模）、(2) 本日の依頼分が直接作業されチケット化されていなかった。チケット粒度ルール・テンプレ・Notion 同期の三方を立て直す。

## タスク分解

- [x] チケット粒度ルールを `_template.md` に明記（1チケット=1〜2セッション、親子分割）
- [x] `parent_ticket` フィールドをテンプレに追加
- [x] 本日の再編4件（T-007〜T-010）を遡及チケット化
- [x] T-003 を `doing → waiting`（個票4本納品済、社長レビュー待ち）に移動
- [x] T-005 を `doing → waiting`（レポート納品済、社長レビュー待ち）に移動
- [x] Notion Assignee 選択肢に researcher / planner / simulator を追加
- [x] Notion に未登録の T-005／T-006／T-007〜T-011 を新規作成
- [x] Notion 上の T-003／T-004 のステータス・Assignee を最新化
- [x] `docs/notion-board-schema.md` を更新（新 Assignee 値、parent_ticket 拡張案）
- [x] `agents/secretary/skills/notion-ticket-sync.md` を更新（粒度ルール・同期タイミング強化）

## 現在地

完了。Notion 上に11カードが正しく出現、状態も最新化済み（done 6 / waiting 2 / doing 1 / todo 1 → push 後 done 7 になる予定）。

## ログ

- 2026-05-20 社長指摘受領、ただちにチケット起票（今回は鉄則通り）
- 2026-05-20 ローカルファイル更新完了、Notion 同期実行
- 2026-05-20 Notion Assignee に researcher/planner/simulator 追加、ParentTicket 列追加
- 2026-05-20 T-005／T-006／T-007〜T-011 を Notion に新規作成、T-003 を waiting に更新
- 2026-05-20 done として完了
