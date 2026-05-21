---
ticket_id: T-20260520-007
title: リサーチャー（サトル）＋プランナー（タケシ）新設で役割分担を明確化
status: done
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: false
labels: [org, agent-setup]
parent_ticket: ""
---

## 要件

社長から「リサーチが秘書に集中しているので役割分担を整理したい」との依頼。商品リサーチ・市場/競合分析・ツール調査・業界ウォッチを担当するリサーチャー、および調査結果をもとに戦略立案するプランナーを新設する。

## タスク分解

- [x] リサーチャー人選（安宅和人風・サトル）と根拠の明示
- [x] プランナー人選（森岡毅風・タケシ）と根拠の明示
- [x] `agents/researcher/` 新設（agent.md + memory/ + skills/）
- [x] `agents/planner/` 新設（agent.md + memory/ + skills/）
- [x] CLAUDE.md §2（組織図）・§5（ルーティング）を更新
- [x] `agents/secretary/skills/routing.md` の一次判断テーブル更新
- [x] `agents/secretary/agent.md` の連携先を更新
- [x] `workspace/SUBAGENT_PROTOCOL.md` を更新
- [x] 既存リサーチ系チケット（T-003／T-005／T-006）の assignee を `researcher` に付け替え

## 現在地

完了。コミット `cee1619` で push 済。

## ログ

- 2026-05-20 社長依頼受領 → 直接作業に着手（チケット駆動違反、遡及起票）
- 2026-05-20 done として遡及記録

## 反省

CLAUDE.md §3 鉄則 #2「チケット駆動」に反し、依頼を直接作業してチケット化を後回しにしてしまった。今後は依頼受領 → ただちにチケット起票 → 作業着手の順を厳守する。
