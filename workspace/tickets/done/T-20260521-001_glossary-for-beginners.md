---
ticket_id: T-20260521-001
title: Amazon物販・副業 用語集（初心者向け）作成
status: done
assignee: content_creator
priority: high
created_at: 2026-05-20
updated_at: 2026-05-22
requires_approval: false
labels: [glossary, content, foundation, learning]
---

## 要件

社長（副業初心者）が物販・副業の用語を都度迷わず作業を進められるよう、**ある程度のボリュームのある用語集** を作成する。**スプレッドシート（CSV）が第一希望**。電脳せどり等の業界用語、ツールの概要を含む。表形式必須。

## タスク分解

- [x] 収録カテゴリの確定（基礎用語／出品プラン／仕入れ手法／リサーチ／ツール／数字指標／規制・法律／副業税務／Amazon 固有 等）
- [x] 用語の網羅的リサーチ（WebSearch 含む、最新動向を反映）
- [x] 各用語の初心者向け定義作成（1行定義＋必要に応じ補足）
- [x] 関連語・略語・読み方を付与
- [x] CSV 形式で出力（Excel／Google Sheets 直接読込可、UTF-8 BOM 付き）
- [x] 確認用 Markdown 版も併出
- [x] 社長納品 → カズヨが整理して提示
- [x] 社長レビュー OK（2026-05-22）

## 現在地

ヒデアキ納品完了。**150語 / 10カテゴリ**。CSV（RFC4180準拠＋UTF-8 BOM）と Markdown を `workspace/output/agent_output/T-20260520-007/` に格納。社長レビュー待ち。

副次成果（要確認）: 用語集リサーチ過程で **Keepa Pro が 2026年3月に €29（約5,300円）へ値上げ** されている情報を発見。T-003 経理v2 試算は €19 ベースのため、影響可能性あり。

## ログ

- 2026-05-20 todo 起票 → 即 doing（ヒデアキへ発注、承認不要 §4.2）
- 2026-05-20 ヒデアキ納品（150語10カテゴリ・CSV+MD）→ 社長レビュー待ち
- 2026-05-22 社長レビュー OK → doing → done
