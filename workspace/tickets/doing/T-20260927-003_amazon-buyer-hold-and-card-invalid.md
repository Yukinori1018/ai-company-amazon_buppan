---
ticket_id: T-20260927-003
title: 【緊急】Amazon購入アカウント一時保留＋北米セラーの課金方法無効（2026-09-27）の状況整理と対応
status: doing
assignee: secretary
priority: high
created_at: 2026-09-27
updated_at: 2026-09-27
requires_approval: false
labels: [compliance, ops, payment]
parent_ticket: ""
next_check_at: 2026-09-28
related_tickets: [T-20260920-001, T-20260909-001, T-20260726-003]
---

## 要件

2026-09-27、社長より「また、Amazonのアカウントがおかしくなっています。状況を確認し、整理して、対応に当たって下さい。」

## 事実（Gmail satoyukinori1018 実物確認・2026-09-27）

| 受信(JST) | 送信元 | 件名 | 対象 |
|---|---|---|---|
| 19:18 | auto-confirm@amazon.co.jp | 注文済み:「マーフィー100の成功法則」 | 購入アカウント（書籍注文） |
| 19:19 | no-reply@amazon.co.jp | サインインして解決してください：Amazon アカウントは一時保留中です | **購入アカウント**。「異常なお支払いアクティビティ」で保留、未完了の注文・サブスクはキャンセル。サインイン→画面指示→支払方法に応じた書類提出→24時間以内に審査 |
| 19:19 | donotreply@amazon.com | Es necesario actualizar la tarjeta de crédito…（スペイン語） | **メキシコ**セラー `CREDIT_CARD_INVALID` |
| 19:19 | donotreply@amazon.com | Credit card update required to resume Amazon seller account payments | **カナダ**セラー `CREDIT_CARD_INVALID`（リンク先 sellercentral.amazon.ca） |
| 19:23 | prime@amazon.co.jp | プライムへようこそ（30日トライアル開始） | 購入アカウント |

- 送信元ドメイン・リンク先はいずれも amazon.co.jp / amazon.com / sellercentral.amazon.ca（正規）。
- 4通が同じ1分に集中＝**書籍注文の決済を起点に、Amazon の決済リスク判定が同じカードを使う全アカウントに波及**した可能性が高い（推定。画面確認で裏取りする）。

## ログ
- 2026-09-27 カズヨ: 起票。メール5通を確認。次に購入アカウントとセラーセントラル（日本の出品ステータス・課金方法）を実画面で確認する。
- 2026-09-27 カズヨ: 台帳照合。CA/MX の `CREDIT_CARD_INVALID` は 9/11 にも発生し、9/12 に社長が CA を別カードへ更新済み（T-20260726-003）。**今回は更新後のカードでも再発**＝新事象。購入アカウントの一時保留は記録上初出。出品者通知も購入も同じ satoyukinori1018 宛に届いている＝**北米セラーと購入アカウントが同じログインである可能性**（未確認）。
- 2026-09-27 カズヨ: 内蔵ブラウザで sellercentral.amazon.com を開いたが未ログイン。**社長のログイン（本人にしかできない一手）待ち**。
- 2026-09-27 マリエ: Notion カード新規作成（Status=doing・page `3e8b0a40-44fa-81c7-a2ee-d2f0100bc51a`・fetch で読み返し確認）。ラベル `payment` は選択肢に無いため Notion 側は `seller-central` で代替。owner-tasks.md に更新66（社長ログイン・期限 9/28）を追加。

## 対応方針（カズヨ判断）
1. 購入アカウントの保留解除が最優先（24時間審査・書類提出）。出品用の課金カード判定もこれに連動している可能性が高い
2. セラーセントラルで日本ストアの出品ステータスが巻き込まれていないか確認（9/20 復活済み）
3. CA/MX の課金方法は、1 の解除後に再判定されるかを見てから触る（先にカードを差し替えると判定を複雑にする）
4. 書籍注文・プライム30日トライアルは保留でキャンセル扱い。トライアルは解除後に社長の意思確認（不要なら自動更新前に停止）
