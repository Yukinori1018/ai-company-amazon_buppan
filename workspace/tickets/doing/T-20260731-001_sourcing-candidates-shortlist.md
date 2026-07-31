---
ticket_id: T-20260731-001
title: 仕入れせどり 初期仕入れ候補ショートリスト作成（スプレッドシート）
status: doing
assignee: secretary
priority: high
created_at: 2026-07-31
updated_at: 2026-07-31
requires_approval: false
labels: [sourcing, shortlist, spreadsheet, deliverable]
next_check_at: 2026-08-01
---

## 要件

社長依頼：「仕入れせどり」（Amazon で売れる商品を仕入れて Amazon で売る）を前提に、蓄積ナレッジから仕入れる商品候補をピックアップし、スプレッドシートにまとめる。

## 重要な前提（正直な状態把握）

- **Amazon SP-API / Keepa API は現時点で未接続**（接続済み外部連携は Notion / GitHub / Google / Canva の4系統のみ）。
- Sato-Scope の各アダプタ（keepa / rakuten / yahoo）は handover 記載のとおり**モック実装**。
- したがって「実売データ（月販・売値・ランキング）に裏付けられた個別 ASIN リスト」は本セッションでは生成不可。
- 本チケットの成果物は、**実データであるナレッジ資産**（制限カテゴリ×初心者推奨度 / 仕入れ先28社×初心者向き度 / 3シナリオ収益シミュレーション）から導いた**商品タイプ単位の候補仮説**。個別 ASIN の実データ検証は Keepa 接続後（§4.1 課金承認事項）に別チケットで実施する。

## 参照ナレッジ（実データ）

- workspace/output/deliverables/T-20260521-002/restricted-categories.csv（制限カテゴリ×初心者推奨度）
- workspace/output/deliverables/T-20260521-002/suppliers-list.csv（仕入れ先28社×初心者向き度）
- workspace/output/deliverables/T-20260521-002/simulation-numbers.csv（3商品×3シナリオ収益）
- workspace/output/deliverables/T-20260521-005/code/app/calc/{profit,score}.py（利益・スコアロジック）

## タスク分解

- [x] ナレッジ棚卸し（制限カテゴリ・仕入れ先・シミュレーション）
- [x] 候補選定ロジックの確定（法務リスク低 × 粗利率 × 回転 × 仕入れ容易性）
- [x] 商品タイプ単位の候補ショートリストを作成
- [x] スプレッドシート（.xlsx）に整形・納品
- [ ] 社長レビュー → Keepa 接続後に個別 ASIN 検証へ展開するか判断

## 成果物

- workspace/output/deliverables/T-20260731-001/sourcing-candidates.xlsx
- ~/Documents/AI Company Outputs/Amazon物販事業/T-20260731-001/（社長確認用・最終納品）
