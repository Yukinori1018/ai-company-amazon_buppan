---
ticket_id: T-20260726-001
title: アマゾンセラー運用ナレッジの体系収集 → メモリ化 → 一覧提示
status: done
assignee: researcher
priority: high
created_at: 2026-07-26
updated_at: 2026-07-26
requires_approval: false
labels: [knowledge, research, seller-central, memory, onboarding]
related_tickets: [T-20260715-001, T-20260603-003]
---

## 依頼（社長・2026-07-26）
「あなた（カズヨ）はアマゾンセラーのナレッジが少ない。まずナレッジを集めて記憶して。記憶した内容は後で分かるよう一覧で示して。新規学習分＋既存学習分を合わせて提示して」

## 方針
- 担当＝リサーチャー・サトル（事実収集・構造化）。§4.1非該当＝自律進行。
- 既存メモリ（電脳せどり/メーカー仕入れ/ERESA/NETSEA等）は「仕入れ・ツール寄り」。今回は**Amazonセラー運用の土台**（アカウント/料金/FBA/健全性/規約/リサーチ実務/集客）を補強する。
- 4領域を並行調査 → カズヨが統合 → `memory/` にナレッジファイル化 → MEMORY.md 索引更新 → 社長へ一覧提示。

## 調査4領域
1. Seller Central運用基礎（大口/小口、料金体系、FBA vs FBM、出品/カタログ/ASIN・SKU）
2. アカウント健全性・規約・サスペンド予防（AHR/ODR/ポリシー違反類型/真贋/予防策）
3. せどり/物販リサーチ実務（利益計算・損益分岐・Keepa指標・価格改定・出品制限/危険物・資金繰り）
4. 商品ページ最適化・集客・広告・レビュー（SEO/スポンサー広告/レビュー適法境界）

## 成果物
- `memory/` に新規ナレッジファイル（knowledge_*.md）
- MEMORY.md 索引更新
- 社長向け一覧（新規＋既存）

## 経過
- 2026-07-26 起票。サトルへ4領域並行発注。
- 2026-07-26 完了。4領域すべて収集完了→メモリ4ファイル新規作成＋MEMORY.md索引更新（漏れていた knowledge_maker_extraction_keepa も索引追加）。社長へ新規＋既存の一覧提示。done クローズ。
  - 新規メモリ: knowledge_seller_operations_basics / knowledge_account_health_suspension / knowledge_seller_research_profit / knowledge_listing_ads_reviews
  - 数値・料率は2026年時点の公開値。実発注前にセラーセントラル公式値で都度確認する前提。
- 2026-07-26 追加フェーズ（社長指示「公式ページを実際に見て裏取り」）:
  - Chrome/アプリ内ブラウザで sell.amazon.co.jp を実地巡回し、料金/初心者ガイド/FBA/ブランド登録/新規特典/広告ページの本文を一次情報で取得。
  - カテゴリ別販売手数料の全表・FBA保管料の正確な式・登録要件・IPI・FBA手数料全種・FNSKU/危険物SDS・新規出品者特典の具体額 等を確認 → メモリ knowledge_seller_operations_basics 更新＋新規 knowledge_seller_official_operations 作成。
  - 副次確認: アカウント固有ページ(健全性ダッシュボード等)は「無認可(NCID: A1XUKPMRY27SCQ)」が再現＝同一メール2アカウント問題(電話番号2FA=本物/Authenticator=無認可)が銀行登録後も未解決。ログイン必須ページの原文は社長から資料で受領予定。
  - 巡回メモ原本: scratchpad/official_pages_notes.md（作業用）。
