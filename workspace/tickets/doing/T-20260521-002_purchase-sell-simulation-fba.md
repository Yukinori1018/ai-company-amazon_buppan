---
ticket_id: T-20260521-002
title: 初心者向け「仕入れ〜販売」シミュレーション資料作成（FBA 前提）
status: doing
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-21
requires_approval: false
labels: [research, simulation, foundation, learning]
---

## 要件

社長依頼: **Amazon物販で最も購入率が高い商品をリサーチし、仕入れ先・経費を含めた仕入れから販売までのシミュレーションを作成**する。素人でも資料だけで進められる形に仕上げる。**前提: FBA 利用**。

## タスク分解

### Phase 1（並列、3エージェント）

- [x] 経理ハジメ: 商品ジャンル5案＋代表商品3点＋収支シミュレーション → `accounting-simulation.md` + `simulation-numbers.csv`
- [x] 庶務マリエ: 仕入れ先30件8カテゴリ＋選定フロー＋仕入れ記録テンプレ → `suppliers-list.md` + `suppliers-list.csv` + `purchase-log-template.csv`
- [x] 法務ハルオ: FBA出品規制マトリクス＋ブラックリスト＋古物商判定 → `legal-fba-compliance.md` + `restricted-categories.csv`

### Phase 2

- [x] ヒデアキ統合: Day 1〜Day 75 操作マニュアル化、3者整合性チェック、HTML 併出 → `playbook-final.md` + `playbook-final.html`
- [ ] 社長レビュー → §4.1 該当事項（実仕入れ・古物商申請・特商法住所登録）の承認

## 現在地

ヒデアキ統合完了。社長レビュー待ち。**整合性チェックで経理推奨商品①シャンプーが法務 NG（化粧品扱い・出品許可申請必須）と判明。ヒデアキ推奨は「文房具・収納雑貨」への差替え**。商品②③は条件付き可で残置。

## ログ

- 2026-05-21 todo 起票 → 即 doing（承認不要 §4.2、Phase 1 3エージェント並列発注）
- 2026-05-21 Phase 1 完了（経理・庶務・法務）
- 2026-05-21 Phase 2 ヒデアキ統合完了（playbook-final.md/html）。社長レビュー待ち
- 2026-05-21 重要差分: 商品①シャンプー → 法務NG → 文房具/収納雑貨へ差替え推奨
