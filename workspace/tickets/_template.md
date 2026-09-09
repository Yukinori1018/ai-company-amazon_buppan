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
> `parent_ticket`（`parent` ではない）、
> `next_check_at`（`doing/` と `waiting/` の日次リマインダーが読む）。
> `assignee` の値は固定語彙：`secretary` / `researcher` / `planner` / `simulator` /
> `accounting` / `legal` / `general_affairs` / `content_creator` / `it_engineer` / `owner`。
> **綴りに注意：ここは snake_case。`.claude/agents/` のエージェント名はハイフン（`general-affairs` 等）で別物です**
> （置き換えると Notion 同期が落ちる／Agent が解決されない。詳細は [docs/notion-board-schema.md](../../docs/notion-board-schema.md) §Assignee）。

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

## 成果物

> **この節は必須です。空欄にしない・節ごと消さない。** 位置は本文の**末尾**（`## ログ` の後）、1チケットに1つだけ。
> 形式の正は [agents/secretary/skills/ticket-management.md](../../agents/secretary/skills/ticket-management.md) §`## 成果物` 節の運用。
> **相対パスの基準は配置後のチケット（`workspace/tickets/<todo|doing|waiting|done>/`）** なので `../../output/deliverables/...` と書きます。
> この雛形は `workspace/tickets/` 直下にあるため、**この記入例のリンクは雛形の状態では解決しません**（`todo/` 等へコピーした時点で正しく解決します）。
> 書いたら**必ず実パスが解決するか確かめること**（リンク切れを作らない）。
> 成果物を `deliverables/<ticket_id>/` に置いて commit したら、**同じ turn でこの節に行を追加**します。「後でまとめて」は必ず忘れます。

**記入例（成果物があるとき）** — 下の3点セットで書く。

- 📁 **[T-YYYYMMDD-NNN/](../../output/deliverables/T-YYYYMMDD-NNN/)** — 成果物フォルダ（N件）
  - [`01_◯◯.html`](../../output/deliverables/T-YYYYMMDD-NNN/01_◯◯.html) — 1行説明（社長はまずこれ）
  - [`01_◯◯.md`](../../output/deliverables/T-YYYYMMDD-NNN/01_◯◯.md) — 同内容のテキスト版
  - [`README.md`](../../output/deliverables/T-YYYYMMDD-NNN/README.md) — 索引
  - [`out/`](../../output/deliverables/T-YYYYMMDD-NNN/out/) — 金額明細など 〔Git除外・ローカルのみ〕
  - ほか N 件（上記フォルダを参照）
- 社長の閲覧口（Finder）：`~/Documents/AI Company Outputs/Amazon物販事業/T-YYYYMMDD-NNN/`

補足:
- 主要ファイルが多いときは、上位数件＋`ほか N 件（上記フォルダを参照）`にとどめる。
- `.gitignore` で除外している成果物には `〔Git除外・ローカルのみ〕` を添える（GitHub 上ではリンクが 404 になるため）。
- 社長の閲覧口は symlink 先なので**リンクにはせず**、バッククォートのテキスト表記にする。

**記入例（成果物が無いとき）** — 節を消さず、理由を1行で書く。

```
## 成果物

（なし — 社長判断のチケットのため成果物ファイルなし）
```

理由の例：`社長判断のチケットのため` / `リポジトリ側の更新そのものが成果のため` / `外部での手続き・作業が成果のため` / 単に `成果物ファイルなし`。**無理に断定しない**（分からなければ `成果物ファイルなし` でよい）。
