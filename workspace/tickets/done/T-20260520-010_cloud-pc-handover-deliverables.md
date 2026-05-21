---
ticket_id: T-20260520-010
title: クラウド⇔PC 引き継ぎ：deliverables/ 配置ルール追加
status: done
assignee: secretary
priority: medium
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: false
labels: [infrastructure, workflow]
parent_ticket: ""
---

## 要件

クラウドセッションでは社長 PC の `~/Documents/AI Company Outputs/` に書き込めないため、成果物が引き継げない問題があった。リポ内に Git追跡される `workspace/output/deliverables/<ticket_id>/` を新設し、クラウドからは Git 経由で社長 PC へ届ける運用に統一。

## タスク分解

- [x] `workspace/output/deliverables/` 新設
- [x] `workspace/SUBAGENT_PROTOCOL.md` に「セッション環境に応じた配置先」を明記
- [x] T-003 の個票4本（Keepa／SellerSprite／アマサーチ／FBA計算機）を新ルールで配置

## 現在地

完了。コミット `521eec9` で push 済。

## ログ

- 2026-05-20 T-003 個票作成時に問題発覚 → 新ルール起案・実装（遡及起票）
- 2026-05-20 done として遡及記録
