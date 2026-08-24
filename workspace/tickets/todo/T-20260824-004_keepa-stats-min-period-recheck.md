---
ticket_id: T-20260824-004
title: Keepa stats.min の期間解釈の取り違えを検証・scan_v13 の「過去1年最安値」列への影響評価
status: todo
assignee: it_engineer
priority: high
created_at: 2026-08-24
updated_at: 2026-08-24
requires_approval: false
labels: [keepa, data-quality, bug-suspect]
parent_ticket: T-20260824-001
next_check_at: 2026-08-25
related_tickets: [T-20260824-001, T-20260824-003, T-20260817-005]
---

## 要件

`agents/it_engineer/memory/knowledge_keepa_product_finder_fields.md` に
「`stats.min[i]` は `stats=N` の N日間の最小値」とあるが、T-20260824-001 の
`keepa-glossary.md` は「`min` は**全期間**の最安値。期間内の最安は `minInInterval`」と確定。
どちらが正しいかを保存済み raw JSON で判定し、`scan_v13.py` の「過去1年最安値」列と
そこから引く**損益分岐仕入れ値の全行**への影響を評価する。

> T-20260824-003 でタカシが発見した申し送り。monthlySold より実害が大きい可能性あり。
> 全期間最安値を「過去1年最安値」として使っていた場合、**仕入れ判断が過度に保守的**に
> 振れている（古い底値に引きずられる）。

## タスク分解

- [ ] 公式定義（keepa-glossary.md）と memory の記述を突合
- [ ] 保存済み raw JSON（T-20260817-005/raw/）で `min` と `minInInterval` の値を比較して実証（Keepa API は叩かない）
- [ ] `scan_v13.py` の該当箇所を特定し、どちらを読んでいるか確認
- [ ] 影響を受けた過去成果物（v13 top100 等）の行数・ズレ幅を定量化
- [ ] memory を修正、必要ならスクリプトを修正

## 現在地

未着手。

## ログ

- 2026-08-24 todo 起票（T-20260824-003 の申し送りから分離）
