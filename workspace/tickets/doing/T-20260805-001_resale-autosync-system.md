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
- 2026-08-05: SP-API認証スモークテスト（auth:test）追加、ヤフオク取得にジッタ＋429/503バックオフ強化。
- 2026-08-05: 社長が運用モデルを確定＝「即時仕入れ→検品→ラベル貼替(外注)→FBA」でポリシー非抵触。
  - 設計インプリケーション: FBA有在庫のため「ヤフオク在庫→Amazon在庫0/1自動切替」の前提が消失。
  - 対応: putListingをFBA既定(AMAZON_JP)に、pricingをFBA手数料モデルに更新。DESIGN冒頭を確定モデルに改訂。
  - 次: ツールの重心を「仕入れ判断＋仕入れ〜FBA納品パイプライン管理＋FBA在庫/価格監視」へ寄せる方向で
    スコープ再設計を社長にA/B/C提示（waiting相当）。
- 2026-08-05: 社長「無在庫ではFBAはしない方がいい」＝A方向で確定。ツールをFBAパイプラインへ再設計。
  - スキーマをProduct(pipelineStage)/PipelineLogへ刷新（Auction/SyncLog廃止）。
  - pipelineService新設（SOURCED→INSPECTED→RELABELED→INBOUND→LISTED→SOLD_OUT の段階遷移＋FBA出品）。
  - 無在庫用syncService削除、monitorJobはFBA在庫/価格監視のPhase2スタブへ。
  - UIをかんばんボードへ、API刷新（/api/products, /advance, /list）。DESIGN/README全面更新。
- 2026-08-05: 社長「無在庫もやる」＝FBM＋FBAハイブリッドへ再々設計（当初コアのヤフオク監視を復活）。
  - schema両対応: Product.fulfillmentType(FBM/FBA)、Auction/SyncLog(FBM用)復活＋PipelineLog(FBA)併存。
  - fbmService新設(FBM出品＋Auction紐付け)、syncService復活(ヤフオク状態→Amazon在庫同期)、monitorJobはFBM同期ループへ。
  - UIをFBM監視一覧＋FBAボードの2パネル＋方式切替に。API: /api/fbm/list, /api/monitor/run 追加。
  - DESIGN/README全面更新。FBMパスのポリシー抵触リスクは明記のうえ社長判断で進行。
