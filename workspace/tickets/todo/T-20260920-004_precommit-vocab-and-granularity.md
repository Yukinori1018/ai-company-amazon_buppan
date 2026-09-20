---
ticket_id: T-20260920-004
title: pre-commit フックの穴3つを埋める（会員限定の取引条件・2列時系列・散文中の金額）
status: todo
assignee: it_engineer
requires_approval: false
created_at: 2026-09-20
updated_at: 2026-09-20
next_check_at: 2026-09-22
priority: high
labels: [ops, security, tooling]
related_tickets:
  - T-20260920-003
---

## 背景

2026-09-20、SD 会員限定の取引条件（卸値・SD品番・上代・ロット・卸価格の分布）が PUBLIC リポに push された（T-20260920-003 の是正記録を参照）。pre-commit フックは通り抜けた。ハルオの [08_Keepa由来データの公開基準](../../output/deliverables/T-20260920-003/08_Keepa由来データの公開基準.md) §5-4 が穴を3つ特定している。

## タスク

- [ ] 検出語彙に `90日平均` `在庫切れ率` `上代` `卸単価` `SD品番` `最小ロット` `卸率` を追加
- [ ] md の表判定が「5列以上の表ヘッダ」しか見ておらず、**2列の時系列表**（項目｜値）が通る問題を直す
- [ ] 散文中の「卸値 ◯◯◯円」のような**金額つきの文**を捕まえる（現在は表のみ判定）
- [ ] ハルオの ABCD 分類（A=Amazonの現在スナップショット可／B=Keepa固有の履歴・派生／C=会員限定の取引条件＝Hard NO／D=認証情報）を、フックの判定と1対1に対応させる
- [ ] **ゲートを緩める方向の変更はしない。**語彙と粒度の問題として直す
- [ ] 誤検知時の逃げ道（`--no-verify`）に頼らず通せるか、法務の成果物自身で回帰テストする

## 参照

- [08_Keepa由来データの公開基準.md](../../output/deliverables/T-20260920-003/08_Keepa由来データの公開基準.md)
- `agents/legal/memory/knowledge_public_data_release_standard_ABCD.md`
