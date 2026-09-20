---
ticket_id: T-20260921-001
title: 書籍『Amazon国内メーカー直取引完全ガイド（増補改訂版）』の読み込みとナレッジ化
status: waiting
assignee: owner
requires_approval: false
created_at: 2026-09-21
updated_at: 2026-09-21
next_check_at: 2026-09-22
due_date: 2026-09-28
priority: high
labels: [knowledge, maker-shiire, research]
related_tickets:
  - T-20260915-002
  - T-20260903-001
  - T-20260831-004
  - T-20260912-002
---

## 依頼

社長より Kindle リンク（ASIN B09G9J9SYF）を共有。「全て読んでナレッジにして」。

## 対象書籍

| 項目 | 内容 |
|---|---|
| 書名 | Amazon国内メーカー直取引完全ガイド（増補改訂版） |
| 著者 | 中村 裕紀（Amazon物販コンサルタント／転売で月利100万→アカウント閉鎖→メーカー取引一本で月利200万） |
| 出版 | standards / 2021-09-21 |
| 形式 | Kindle版・**固定レイアウト**（文字列の検索・引用・ハイライト不可＝画像ページ）/ 134.9MB |
| 読み放題 | Kindle Unlimited 対象表示あり |

## ロードマップ上の位置づけ

本丸＝「ネット販売に疎い中小メーカー → 独占販売」（[project_strategy_core_offline_makers]）。
本書の著者は**その手法の国内における originator 格**。§feedback「一から組むな・成功者を真似よ」に最も直接に効く一次資料。
アウトプットは T-20260903-001（メーカー取引条件）・T-20260831-004（抽出設計）・T-20260915-002（成功者の型）へ流す。

## 制約（重要）

1. **本リポジトリは PUBLIC・30分ごと自動 push**。書籍本文の全文・長文引用は**一切リポに置かない**。
   成果物は自分の言葉で書いた要約・手順・判断基準に限る（出典は書名＋章で示す）。
2. 固定レイアウトのためテキスト抽出不可。**Kindle Cloud Reader を1ページずつ画面で読む**必要がある。
3. read.amazon.co.jp は未ログイン。**社長のログイン（ID/PW・2FA）が必須**＝本人にしかできない一手（CLAUDE.md §4.4）。

## 進め方

1. 社長に read.amazon.co.jp へログインしてもらう（この1手のみ）
2. カズヨがブラウザで本書を開き、章単位で読み進めて要点をメモ（agent_output へ）
3. サトル（researcher）が構造化 → ヒデアキ（content_creator）が読み物に整形
4. `deliverables/T-20260921-001/` へ納品＋ memory へ knowledge_* を1本追加

## 成果物

- [01_中村裕紀_国内メーカー直取引_読解ノート.md](../../output/deliverables/T-20260921-001/01_中村裕紀_国内メーカー直取引_読解ノート.md) — 全10章の読解ノート（当社の言葉による要約。本文の引用なし）
- [02_当社への適用と差分.md](../../output/deliverables/T-20260921-001/02_当社への適用と差分.md) — 当社への適用・既定との衝突点・社長判断が要る論点

## ログ

- 2026-09-21 起票。書誌情報を Amazon 商品ページで確認。Kindle Cloud Reader が未ログインのため社長依頼。
- 2026-09-21 社長の Chrome にログイン済みと判明。Claude in Chrome 経由で Kindle Cloud Reader を開き、**全336ページ（位置347/347）を通読完了**。固定レイアウトのため1見開きずつ画面で読み取り。
- 2026-09-21 読解ノートと適用メモを deliverables へ納品。memory に knowledge を1本追加。
- 2026-09-21 doing → waiting（社長判断3件：資金1,000万の壁のロードマップ反映／接触基準の二段構え整理／交渉道具の整備着手）。
- 2026-09-21 マリエ：Notion カンバンへ新規カードを作成（doing 列 / page 3e1b0a40-44fa-81fe-ac5b-d2d7120f0fa3）。workspace/owner-tasks.md を更新59で最新化し、🔴 に「Kindle Cloud Reader へのログイン（期限の目安 9/22）」を1件追加。
- 2026-09-21 マリエ：完了同期。Notion カードを **doing → waiting**（Assignee=owner／UpdatedAt=2026-09-21）へ移し、本文の `## 結果要約` と `## 成果物` 節を納品内容（読解ノート＋適用メモの2本・社長判断3件）で書き換え。`workspace/owner-tasks.md` を更新60で最新化し、**Kindle ログインの依頼を削除**（社長の Chrome に既にログイン済みだったため解消）、代わりに社長判断3件を 🔴 に追加（🔴 2件 → 4件）。成果物カタログへ2行追記し、スプレッドシートへ同期（849行）。
