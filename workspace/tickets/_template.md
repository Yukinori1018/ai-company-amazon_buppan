---
ticket_id: T-YYYYMMDD-NNN
title: {{ チケットタイトル }}
status: todo
assignee: secretary
priority: medium
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
requires_approval: false
labels: []
parent_ticket: ""
next_check_at: YYYY-MM-DD
related_tickets: []
---

> ⚠️ **frontmatter のキー名は変更しないこと（機械が読む契約です）。**
> `ticket_id` は `.claude/hooks/session-start.sh` が awk で直読みし、
> `ticket_id` / `title` / `status` / `assignee` / `priority` / `requires_approval` /
> `created_at` / `updated_at` / `labels` / `parent_ticket` は Notion カンバンの各列に
> 1対1でマップされます（[docs/notion-board-schema.md](../../docs/notion-board-schema.md)）。
> 過去に `ticket_id`→`id` / `assignee`→`owner` と勝手に別名を使った13枚が、
> フックのID表示欠落と Notion の担当欄空白を引き起こしました（T-20260821-003 で修復）。
> **省略は可、リネームは不可。** 表記ゆれ注意：`related_tickets`（`related` ではない）、
> `next_check_at`（`doing/` と `waiting/` の日次リマインダーが読む）。
> `assignee` の値は固定語彙：`secretary` / `researcher` / `planner` / `simulator` /
> `accounting` / `legal` / `general_affairs` / `content_creator` / `it_engineer` / `owner`。

> このファイルは雛形です。`_` 始まりのファイルは秘書のチケットスキャン対象外です。
> 新規起票時はコピーして `<ticket_id>_<短いスラッグ>.md` にリネームし、`todo/` 配下に配置してください。
> `next_check_at` はリマインダー不要なら行ごと削除して構いません。

## チケット粒度の目安

**1チケット = 1〜2セッション（数時間〜半日）で完了する規模**を目標。それより大きい依頼は親子分割する：

- **親チケット**: 全体ゴール（例：「Amazon物販ツール網羅調査・評価」）
- **子チケット**: 1〜2セッションで完了する単位（例：「Keepa 個票作成」「SellerSprite 個票作成」…）
  - 子チケットの `parent_ticket` に親の ticket_id を記載
  - 子は独立して `todo → doing → done` で動かす
  - 親は子がすべて done になった時点で done

> 1枚で抱え込まないこと。Notion カンバン上の「進んでない感」は、粒度が大きすぎることが主な原因。

## 要件

（社長から受けた依頼を一文で。秘書が「何を達成したいか」を要約する）

## タスク分解

- [ ] サブタスク1
- [ ] サブタスク2
- [ ] サブタスク3

## 現在地

（いま何をしているか／次は何をするか。進捗とともに上書き更新）

## ログ

- YYYY-MM-DD todo 起票
