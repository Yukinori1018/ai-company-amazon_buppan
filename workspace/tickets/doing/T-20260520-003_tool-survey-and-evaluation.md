---
ticket_id: T-20260520-003
title: Amazon物販ツール網羅調査・評価（軸A）
status: doing
assignee: secretary
priority: high
created_at: 2026-05-20
updated_at: 2026-05-20
requires_approval: true
labels: [strategy, tooling, research]
---

## 要件

利益 × 確度を数値化して商品候補を提示できる既存ツールを網羅的に洗い出し、評価する。社長が読みやすい比較レポートを作成し、導入判断を仰ぐ。

## タスク分解

- [x] 調査対象ツールの洗い出し（国内外20+）
- [x] 評価軸の確定（機能 / 価格 / 国内Amazon対応 / 学習コスト / 出力可搬性 等）
- [x] 各ツールの一次情報収集（公式サイト・料金・トライアル可否）
- [x] テキスト + HTML 形式の比較レポート作成（PC ローカル `~/Documents/AI Company Outputs/Amazon物販事業/T-20260520-003/report.html`）
- [x] 推奨案（A/B/C＋推奨）の提示
- [x] **各推奨ツールの個票作成**（Keepa / SellerSprite / アマサーチ / FBA計算機）→ `workspace/output/agent_output/T-20260520-003/tool-profiles.md`
- [ ] 社長承認 → 導入対象を確定（契約は別チケットで §4.1 承認）

## 現在地

個票作成（2026-05-20 cloud セッション）完了。各ツールの用途・できること・料金・代替・画面構成・採用タイミング・注意点を1ツール1枚で整理し、横並び比較表＋ A/B/C＋推奨を再提示。社長判断待ち：
1. A（即フル） / B（段階導入・秘書推奨） / C（無料のみ） のどれで進めるか
2. B を選ぶ場合、SellerSprite（中国発SaaS）の法務確認発注を Yes / No
3. 店舗仕入れの可能性が高ければアマサーチを前倒し導入するか

## 候補ツール（初期リスト・拡張予定）

**海外発（Amazon US 中心、JP も対応するもの多い）**
- Keepa / Helium 10 / Jungle Scout / SellerSprite / AMZScout / Viral Launch / DataDive

**国内発（Amazon JP 特化）**
- DELTA tracer / ERESA / Amasia / マカド！ / プライスター / セラースケット / セドリスト / Amzcockpit

**価格改定・在庫管理系**
- プライスター / マカド / セラースプライト等

**SP-API + 自社実装の選択肢**
- Amazon SP-API + Keepa API 直叩き

## ログ

- 2026-05-20 doing 起票（高優先・社長承認必須）
- 2026-05-20 社長 FB「ツール詳細不足」→ 各ツール個票作成タスクを追加
- 2026-05-20 cloud セッションで個票作成完了（`workspace/output/agent_output/T-20260520-003/tool-profiles.md`、cloud 由来のため force-add でコミット）。社長 A/B/C 判断待ち
- 2026-05-20 更新日付: 2026-05-20
