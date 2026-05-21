---
ticket_id: T-20260520-009
title: 自律運用ルール拡張（§4.3 緩和・夜間自走モード・ルーティン定義）
status: done
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: false
labels: [org, autonomy, routines]
parent_ticket: ""
---

## 要件

社長から「一問一答で進みが遅い。和代の判断で進めてほしい。夜間も自走してほしい。フック・ループ・ルーティンを使って回せるように」との依頼。秘書の自律範囲を拡大し、夜間の自走モードを設計する。

## タスク分解

- [x] CLAUDE.md §4.3 を「迷ったら止まる」→「軽く動いてから聞く」に改訂
- [x] CLAUDE.md §4.2 を「自律推奨」として強化
- [x] `agents/secretary/skills/routines.md` 新設（朝・夕・夜・週次・月次）
- [x] CLAUDE.md §5.1「自律運用とルーティン」を追記
- [x] `agents/secretary/agent.md` に「社長の Do を最小化することを最優先」を明記
- [x] 夜間自走の起動方法を文書化（「今晩は T-XXX を進めて」で起動）

## 現在地

完了。コミット `b624cae` で push 済。フック実装（夜間自走の自動起動）は次回以降の改善候補。

## ログ

- 2026-05-20 社長依頼受領 → 直接作業（遡及起票）
- 2026-05-20 done として遡及記録
