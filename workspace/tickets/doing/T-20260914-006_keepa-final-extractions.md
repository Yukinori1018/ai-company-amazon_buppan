---
ticket_id: T-20260914-006
title: Keepa 解約前の最終抽出（T-3 ブランド未登録メーカー／S-3 展示会の残り952社）期限 10/2
status: doing
assignee: it_engineer
priority: high
created_at: 2026-09-14
updated_at: 2026-09-14
requires_approval: false
labels: [pipeline, sourcing]
parent_ticket: T-20260912-002
next_check_at: 2026-09-21
related_tickets: [T-20260912-002, T-20260914-002, T-20260914-005]
---

## 要件

統合報告 v3（T-20260912-002/07）の最良案は「ブランド未登録メーカー（P2）への打診＋Keepa を必要な月だけ」。論点③で Keepa API の解約（次回更新 10/4 の前）を推奨している。支払い済みの期間（9/4〜10/4）は解約後も API が動く（タカシ棚卸し 08）。**その期間内に、打診先の抽出を済ませておく。** 費用は0円（支払い済み）で取り消しもきくため、社長判断を待たずに進める（§4.2）。送信・発注・解約はしない。

| # | 担当 | 内容 | token | 期限 |
|---|---|---|---|---|
| T-3 | タカシ | T-1 の打診母数1,394 ASIN から P2（`brandStoreName` なし・第三者出品）を抽出。ブランド・メーカー単位で集計 | 約4,900 | 9/21 |
| S-3 | サトル（T-3 の後） | 展示会の残り952社の Keepa 検証（`/search`） | 9,520 | 9/28 |

2本同時は残高を取り合うので、T-3 → S-3 の順。

## 現在地

2026-09-14 起票。T-3 を発注。

### タカシ（T-3）

2026-09-14 着手。スコープ宣言:
- 入れる: T-1 打診母数 1,394 ASIN・1,006社の P2/P1/判定不能の分類（ブランドストア＝T-1 の raw 流用 0 token、出品者構成＝ストアなし分だけ `buybox=1`＋`/seller`）、メーカー単位の集計、S-1 上位60社との一致率、S-3 の開始可能時刻
- 入れない: 全オファーの取得（`offers=`・7 token/ASIN）、ストアありの ASIN への `buybox=1`、連絡先の収集、打診文、送信（§4.1）
- 10:20 S-1 の目視25社と `brandStoreName` が 25/25 一致。ストアなし829 ASIN の `buybox=1` 取得中（`agent_output/T-20260914-006/fetch_t3.py`・再開可）

## ログ

- 2026-09-14 doing 起票（カズヨ）。
- 2026-09-14 マリエ：Notion カード新規作成（doing・it_engineer・high・labels pipeline/sourcing・ParentTicket T-20260912-002）。owner-tasks の ℹ️ と handover に追加。

### タカシ（T-3）

- 2026-09-14 着手。Keepa 残高 1,200/1,200・消費0（list-builder は STOP のまま）。T-1 の raw（今朝取得）に `brandStoreName` が入っていたので、ストア判定は 0 token（1,394中 ストアあり565・なし829）。
- 2026-09-14 10:18 `buybox=1` の試験5件＝15 token（3/ASIN）。`stats.buyBoxStats` に90日のカート獲得者と獲得率が入る。829件の取得を nohup で開始。S-1 との一致 25/25。
- 2026-09-14 10:30 S-1 と社単位でも矛盾0（25社中 一致21・一部の ASIN だけストア4）。未目視34社の空欄を Keepa で埋めた（out/t3_s1_check.csv）。本文 §1・§2 を書いた。

## 成果物

（作業中）
