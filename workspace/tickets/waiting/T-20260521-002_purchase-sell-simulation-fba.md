---
ticket_id: T-20260521-002
title: 初心者向け「仕入れ〜販売」シミュレーション資料作成（FBA 前提）
status: waiting
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-29
next_check_at: 2026-08-24
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
- 2026-05-29 waiting へ移動（新基準＝社長タスク一覧化）。playbook 納品済、社長レビュー待ち

## 社長判断待ち

**納品済みのシミュレーション資料（playbook-final）に目を通し、一言フィードバックをください。** 問題なければ done にします。
- 2026-08-21 next_check_at=2026-08-24 を付与（マリエ／T-20260821-005）: 納品済・社長レビュー待ち。初回FBA納品が近づき再浮上する内容のため今週中

## 成果物

- 📁 **[T-20260521-002/](../../output/deliverables/T-20260521-002/)** — 成果物フォルダ（10件）
  - [`SOURCE.md`](../../output/deliverables/T-20260521-002/SOURCE.md) — 出所カード — 仕入れ先一覧（サトルの手集め）（1.5KB）
  - [`accounting-simulation.md`](../../output/deliverables/T-20260521-002/accounting-simulation.md) — 仕入れ〜販売シミュレーション（経理ハジメ担当範囲）（23.6KB）
  - [`legal-fba-compliance.md`](../../output/deliverables/T-20260521-002/legal-fba-compliance.md) — Amazon FBA 出品 — 法務コンプライアンス・マトリクス（26.8KB）
  - [`playbook-final.html`](../../output/deliverables/T-20260521-002/playbook-final.html) — Amazon物販 仕入れ〜販売 完全プレイブック（FBA・小口・予算10万円） — T-20260520-008（49.9KB）
  - [`playbook-final.md`](../../output/deliverables/T-20260521-002/playbook-final.md) — Amazon物販 仕入れ〜販売 完全プレイブック（FBA・小口・予算10万円）（37.3KB）
  - [`purchase-log-template.csv`](../../output/deliverables/T-20260521-002/purchase-log-template.csv) — 1行 × 17列（﻿仕入れ日・仕入れ先名・カテゴリ番号・商品名 ほか）（495B）
  - [`restricted-categories.csv`](../../output/deliverables/T-20260521-002/restricted-categories.csv) — 25行 × 6列（﻿カテゴリ・制限内容・必要免許・申請・関連法令 ほか）（6.7KB）
  - [`simulation-numbers.csv`](../../output/deliverables/T-20260521-002/simulation-numbers.csv) — 10行 × 20列（﻿商品・ジャンル・シナリオ・仕入単価_円 ほか）（1.8KB）
  - [`suppliers-list.csv`](../../output/deliverables/T-20260521-002/suppliers-list.csv) — 30行 × 11列（﻿カテゴリ番号・カテゴリ名・仕入れ先名・URL ほか）（6.7KB）
  - [`suppliers-list.md`](../../output/deliverables/T-20260521-002/suppliers-list.md) — Amazon物販 — 仕入れ先カタログ「ときめき仕入れ帳」（20.5KB）
- 社長の閲覧口（Finder）：`~/Documents/AI Company Outputs/Amazon物販事業/T-20260521-002/`
