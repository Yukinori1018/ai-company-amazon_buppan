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
next_check_at: 2026-09-16
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
- 2026-08-05: 社長方針最終確定。**FBAはアプリ化しない**（Keepa＋Claude検索→社長選定→メーカー仕入れ→FBA
  の手動運用。※メーカー仕入れ系チケット T-20260705-002/T-20260612-002 の領域）。**アプリはFBM(無在庫)一本**。
  - FBAアプリコード撤去（pipelineService削除、FBAボード/エンドポイント/pipelineStage/PipelineLog削除）。
  - スキーマをFBM専用に。核心=「Amazonで売れたのに仕入れられない」リスク低減を強化：
    損益分岐仕入れ価格 `maxSourcePrice` を導入し、現在価格>maxSourcePrice でも在庫0（利益で仕入れ不能）。
    終了/取消/消滅は即在庫0。UNKNOWNは触らない。判定理由をSyncLog.reasonに記録。
  - UIをFBM単一(リサーチ&出品＋監視一覧に状態/現在価格/損益分岐/在庫を表示)に。DESIGN/README全面刷新。
- 2026-08-05: 社長が要件を精緻化＋実装形態を決定。核心=「Amazonで売れたのに仕入れられない」をアプリ/拡張で防ぐ。
  必要機能: ①ヤフオクで先に売れたらAmazon在庫0 ②Amazon注文が入ったらヤフオク購入を確定。
  社長決定(AskUserQuestion): アーキ=**Chrome拡張のみ** / 自動購入=**半自動(1クリック確認)**。
  → まず「どう改善し・どんな結論か」を提示し、承認後に制作。以下を実装しpush:
  - 新規 `tools/re-sale-autosync-extension/`（Manifest V3・拡張のみ・常駐サーバー無し）。
    background(監視alarm+注文受信+タスク統括)、lib(pricing/decide/store)、content(yahoo半自動購入/seller注文読取+在庫変更)、popup、options。
  - 安全弁: DRY_RUN既定ON、上限価格ガード(maxSourcePrice)、1日購入上限、二重購入防止、購入失敗アラート。
  - サーバーアプリ版(tools/re-sale-autosync)は参照実装として残置（SP-API書込の確実化に将来再利用）。
  - 制約明記: 監視はChrome起動中のみ/セラーセントラル・ヤフオクのDOMセレクタは実画面で要調整。
- 2026-08-21 棚卸し（マリエ／T-20260821-007）: next_check_at 2026-08-06 → 2026-09-16 に再設定。仕分け=A。理由: ④無在庫の探索。T-20260812-004 と同じプロジェクトなので同日に揃えて一体レビュー
