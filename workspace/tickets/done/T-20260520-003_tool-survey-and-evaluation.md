---
ticket_id: T-20260520-003
title: Amazon物販ツール網羅調査・評価（軸A）
status: done
assignee: researcher
priority: high
created_at: 2026-05-20
updated_at: 2026-05-25
requires_approval: true
labels: [strategy, tooling, research, ai-integration]
parent_ticket: ""
---

## 要件

利益 × 確度を数値化して商品候補を提示できる既存ツールを網羅的に洗い出し、評価する。社長が読みやすい比較レポートを作成し、導入判断を仰ぐ。

## タスク分解

- [ ] 調査対象ツールの洗い出し（国内外20+）
- [ ] 評価軸の確定（機能 / 価格 / 国内Amazon対応 / 学習コスト / 出力可搬性 等）
- [ ] 各ツールの一次情報収集（公式サイト・料金・トライアル可否）
- [ ] テキスト + HTML 形式の比較レポート作成
- [ ] 推奨案（A/B/C＋推奨）の提示
- [ ] 社長承認 → 導入対象を確定（契約は別チケットで §4.1 承認）

## 現在地

サトル（リサーチャー）が引き継ぎ。**A案承認済**：このまま個票作成タスクを進める。
- 着手対象: Keepa / SellerSprite / アマサーチ / FBA計算機 の4ツール個票
- 各個票の項目: 用途・できること・料金（プラン別）・無料代替・スクショ／公式リンク・国内Amazon対応・学習コストの目安
- 完成後、タケシ（プランナー）へ「導入タイミング戦略」をバトン → マサル（シミュレーター）で仮想 PDCA → 社長に最終提案

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
- 2026-05-20 役割再編に伴い assignee を secretary → researcher（サトル）に変更。事実シートはサトルが、導入判断（戦略部分）はプランナー（タケシ）に引き継ぐ
- 2026-05-20 社長から A案承認＋以後は秘書判断で進行の指示。サトルが個票作成に着手
- 2026-05-20 サトル：4ツールの個票初稿を `workspace/output/deliverables/T-20260520-003/` に納品（Keepa / SellerSprite / アマサーチ / FBA計算機）
- 2026-05-20 doing → waiting に移動。社長レビュー待ち（個票4本の粒度・項目過不足を確認いただきたい）
- 2026-05-22 社長レビュー：**AI連携を前提に再見直し依頼**。カズヨ推奨A（Sato-Scope を中核、外部ツールは"データ源"に格下げ）で確定。waiting → doing に戻し、サトルへ再発注。
  - 再調査スコープ:
    1. AI 内蔵ツールの網羅追加（Helium 10 AI、Jungle Scout AI、新興日本系 AI 物販ツール、Brand Analytics AI 機能、ChatGPT/Claude 連携サービス 等）
    2. 既存4本の AI 連携可否（API 経由で Sato-Scope に取り込めるか）
    3. 「人間が触る AI ツール」vs「Sato-Scope に組み込む AI 機能」の比較
    4. 各ツールの「AI で代替できる作業」「AI で増幅できる作業」の整理
  - 納期: 1〜2日。納品先 `workspace/output/deliverables/T-20260520-003/`（既存4本は v1 として保存、新規 v2 として AI 連携観点を追加）
- 2026-05-25 サトル v2 納品（AI 内蔵13本＋既存4本＝計17本）。社長レビュー＋方針確定（選択肢1）で軸A 調査は役割完了 → doing → done。
  - 確定方針: Sato-Scope を仕入れ発見の中核（唯一の自社資産）に据える。外部 AI ツール（ERESA 等）は別レイヤーの補完で今は保留。
  - 重要訂正: ERESA と Sato-Scope は代替でなく補完（`05_issues-for-decision.md` に訂正ボックス追記済）。
  - 残課題は法務 ToS 確認（T-22-005/003）に引き継ぎ。

## 成果物

- `workspace/output/deliverables/T-20260520-003/README.md` — 個票インデックス
- `workspace/output/deliverables/T-20260520-003/01_keepa.md`
- `workspace/output/deliverables/T-20260520-003/02_sellersprite.md`
- `workspace/output/deliverables/T-20260520-003/03_amasearch.md`
- `workspace/output/deliverables/T-20260520-003/04_fba-calculator.md`

## 次の手

1. 社長レビュー（粒度・項目過不足）
2. タケシ（プランナー）にバトンパス → 導入タイミング戦略（即導入 vs 軸B後 vs 不要）の A/B/C＋推奨を起案
3. マサル（シミュレーター）が仮想 PDCA → 撤退条件・KPI を磨き込み
4. 収束後、社長へ最終提案（実 Do = 契約申し込みは社長アクション）

## 仮想 PDCA（マサル用メモ）

タケシが戦略案を出したら、マサルが以下シナリオで仮想実行：
- **シナリオA：即 Keepa Premium 導入（月¥3,000）** — 軸B未着手のため使いこなせず3ヶ月空回りリスク
- **シナリオB：軸B 1周後に Keepa Premium 導入** — 文脈を持ったまま導入できデータの読みが早い
- **シナリオC：当面アマサーチ無料版＋ FBA計算機のみ** — 初期コストゼロ、ただし市場分析の解像度が低い

撤退条件のヒント：「導入後3ヶ月で売上に貢献するSKU発見ゼロなら撤退」など。
