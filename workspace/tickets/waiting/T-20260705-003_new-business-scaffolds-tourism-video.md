---
ticket_id: T-20260705-003
title: 観光・動画投稿の2事業向けClaudeCode雛形をローカル生成（部分コピー）
status: waiting
assignee: it_engineer
priority: high
created_at: 2026-07-05
updated_at: 2026-07-05
requires_approval: false
labels: [infra, new-business, scaffold]
parent_ticket: ""
---

## 要件

社長が「このAmazon物販事業のチーム体制・運用（会社の枠組み）」を、①観光事業（訪日外国人向け東京ツアー）と②動画投稿事業でも使いたい。Amazon物販リポを**部分コピー**して、両事業用のClaudeCode作業フォルダをローカルに生成する。社長がフォルダを任意の場所へ移動して使う。GitHub/Notionは触らない（純ローカル雛形）。

## タスク分解

- [x] コピー対象/初期化対象の切り分け（枠組みは流用・Amazon固有/秘匿/肥大物は除外）
- [x] 2フォルダ生成（rsync + 構造リセット）
- [x] CLAUDE.md 事業名置換・§1/§6 のAmazon固有値を初期化
- [x] handover.md / owner-tasks.md を初期状態にリセット
- [x] agent memory・チケット実体・deliverables・秘匿ファイルを除外
- [ ] 社長がフォルダを移動 → 各リポで初回セットアップ（.mcp.json / Notion DB / KPI確定）

## 現在地

生成完了。社長のレビュー＋移動待ち（waiting へ）。

## ログ

- 2026-07-05 doing 起票（社長依頼・IT エンジニア タカシ担当）
- 2026-07-05 2フォルダ生成→waiting（社長のフォルダ移動＋初回セットアップ待ち）
- 2026-07-06 社長方針確認: タスク管理/成果物管理の「やり方」は踏襲、ただし**更新先Notion DB・スプレッドシートは各事業で新規**とする。雛形からAmazon固有ID（Notion Database/Data Source ID・Drive file id）を全除去しプレースホルダー化（残存0件検証）。両scaffoldのhandoverを「移動後セッション向け起動チェックリスト（新規DB/新規シート作成を明記）」に更新。
- 2026-07-06 社長方針: 2事業を順番に立ち上げ、**第1弾＝動画投稿事業**。§1（事業内容・KPI）はフォルダ移動後の新規セッションで調査から確定する。
