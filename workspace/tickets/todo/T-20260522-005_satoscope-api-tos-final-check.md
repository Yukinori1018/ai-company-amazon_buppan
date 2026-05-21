---
ticket_id: T-20260522-005
title: Sato-Scope 公式 API 利用規約 最終確認（Keepa／楽天／Yahoo!）
status: todo
assignee: legal
priority: medium
created_at: 2026-05-22
updated_at: 2026-05-22
requires_approval: false
labels: [legal, sato-scope, tos-review]
related_tickets: [T-20260521-005]
parent_ticket: T-20260521-005
---

## イシュー

> Sato-Scope Phase 2 で実 API 接続する前に、Keepa／楽天市場／Yahoo!ショッピング の各公式 API の **2026 年最新版 ToS** を確認し、Sato-Scope の利用形態が規約範囲内であることを最終確認する。

## 確認対象 API

1. **Keepa API** Power-User Plan（€49/月）
   - 商用利用範囲
   - データ二次配信の可否（個人ツール内表示のみなので OK のはず）
   - レート制限と適切な再試行間隔
2. **楽天市場 商品検索 API**
   - ApplicationID の個人利用範囲
   - 商品データの内部利用範囲
   - 表示要件（楽天バナー/クレジット表記）
3. **Yahoo!ショッピング Web API**
   - ClientID 個人利用範囲
   - データの再利用範囲
   - 表示要件

## 確認項目（各 API 共通）

| 項目 | 期待アウトプット |
|---|---|
| 個人専用ツール内利用 | OK / NG / 条件付き OK |
| クレジット表記要件 | バナー必須 / リンク必須 / 不要 |
| データ保存（SQLite ローカル） | OK / 期間制限あり / NG |
| 利用規約違反時のペナルティ | アカウント停止 / API キー無効化 |

## 打ち切り条件

- 各 API について規約該当条文を抜粋し、Sato-Scope の利用形態が OK / 要修正 を判断できた時点

## バトン

ハルオ完了 → タカシが必要なら表示要件を Sato-Scope に組み込み（楽天バナー等）→ Phase 2 着手

## 現在地

todo。ハルオ発注待ち。

## ログ

- 2026-05-22 起票（Phase 2 §4.1 承認前の最終確認）
