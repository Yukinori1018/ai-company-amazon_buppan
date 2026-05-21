---
ticket_id: T-20260520-008
title: シミュレーター（マサル）新設＋仮想 PDCA 運用設計
status: done
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: false
labels: [org, agent-setup, pdca]
parent_ticket: ""
---

## 要件

社長から「Do は私しかできないのでボトルネックになる。実行前にシミュレートして PDCA を仮想で回したい」との依頼。シミュレーター役を新設し、タケシ⇄マサルの往復で仮想 PDCA を回す運用を設計する。

## タスク分解

- [x] シミュレーター人選（羽生善治風・マサル）と根拠の明示（10候補から選定）
- [x] `agents/simulator/agent.md` 新設
- [x] CLAUDE.md §2 に「意思決定パイプライン（仮想 PDCA 込み）」を追記
- [x] `agents/secretary/skills/pdca-with-simulator.md` 新設
- [x] `agents/secretary/skills/routing.md` にシミュレーター行を追加
- [x] CLAUDE.md §5 にシミュレーター行を追加
- [x] `workspace/SUBAGENT_PROTOCOL.md` を更新

## 現在地

完了。コミット `b624cae` で push 済。

## ログ

- 2026-05-20 社長依頼受領 → 直接作業（遡及起票）
- 2026-05-20 done として遡及記録
