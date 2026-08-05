---
ticket_id: T-20260805-001
title: Re-Sale AutoSync（ヤフオク!⇄Amazon 無在庫同期ツール）設計＋コード雛形の開発
status: doing
assignee: it_engineer
priority: medium
created_at: 2026-08-05
updated_at: 2026-08-05
requires_approval: false
labels: [it-engineer, spec, amazon-spapi, yahoo-auction, scaffold]
related_tickets: [T-20260521-005]
next_check_at: 2026-08-06
---

## イシュー

> 社長依頼：ヤフオク!の中古品を Amazon に無在庫（FBM）出品し、ヤフオク!側の在庫状況と
> Amazon 側の出品ステータスを自動同期する「Re-Sale AutoSync」の設計方針と核となるコード
> （Node.js/TypeScript）をステップバイステップで提示・納品する。

## スコープ（今回の納品）

1. アーキテクチャ設計（構成図＋ディレクトリ）
2. DB スキーマ（Prisma）
3. Amazon SP-API 連携（出品 PUT／在庫 PATCH）コード雛形
4. ヤフオク! 監視ロジック（Cheerio/Puppeteer）コード雛形
5. 定期実行タスク（node-cron）コード雛形
6. 開発上の注意点（レート制限・エラーハンドリング・**Amazon ドロップシッピングポリシー**）

## 法務（ハルオ）注意 — 着手前に社長へ共有済み

- ヤフオク!→Amazon の**無在庫転売は Amazon のドロップシッピングポリシーに原則抵触**する
  （「他の小売業者から購入し、その小売業者に直接顧客へ発送させる」形態の禁止）。
  技術的工夫で"回避"できる性質のものではなく、アカウント停止リスクを内包する。
- ヤフオク!のスクレイピングは Yahoo! の利用規約・robots・アクセス負荷の観点で要配慮。
- → §6 と DESIGN.md に**リスクと緩和策を明記**した上で、あくまで「雛形」として納品する。
  本番投入前に社長判断（Go/NoGo）を要する旨を waiting 相当の注意書きで残す。

## 成果物

- `tools/re-sale-autosync/` 一式（設計書 `docs/DESIGN.md`＋TypeScript コード雛形）

## ログ

- 2026-08-05: 起票・設計＋コード雛形を実装しブランチ `claude/resale-autosync-system-m7hgjo` に納品。
