# スキル：チケット管理

秘書がチケットを起票・更新・移動する際の手順書です。

## チケットファイル形式

すべてのチケットは Markdown ファイル。frontmatter で構造化情報を持ちます。

```markdown
---
ticket_id: T-20260518-001
title: {{ チケットタイトル }}
status: todo            # todo | doing | waiting | done
assignee: secretary      # secretary | researcher | planner | simulator | accounting | legal | general_affairs | content_creator
priority: medium         # low | medium | high
created_at: 2026-05-18
updated_at: 2026-05-18
requires_approval: false # true なら waiting/ 経由必須
labels: []
parent_ticket: ""        # 親チケットがあればその ticket_id を記載。なければ空文字列
---

## 要件
（社長から受けた依頼を一文で）

## タスク分解
- [ ] サブタスク1
- [ ] サブタスク2

## 現在地
（いま何をしているか / 次は何をするか）

## ログ
- 2026-05-18 todo 起票
```

## ticket_id の命名規則

`T-YYYYMMDD-NNN`

- `YYYYMMDD` — 起票日
- `NNN` — その日の通し番号（001 から）

ファイル名は `<ticket_id>_<短いスラッグ>.md`（例: `T-20260518-001_amazon-listing-review.md`）。

## 状態遷移ルール

```
todo → doing → waiting → done
 ↑                ↓
 └──── 差し戻し（社長判断で）
```

各遷移時に行うこと：

| 遷移 | 必須アクション |
|------|--------------|
| → todo | チケット作成、frontmatter 記入、Notion 同期（新規カード作成） |
| todo → doing | 担当エージェント起動、`status` 更新、`updated_at` 更新、Notion 同期 |
| todo/doing → waiting | 本文に **「## 社長判断待ち」** で待っている内容（何をしてほしいか）を明記、Notion 同期、§4.1 該当なら `requires_approval: true` と理由を記載 |
| waiting → doing | 社長回答・アクションをログに記録、Notion 同期 |
| doing → done | 成果物リンクを本文に追記、`~/Documents/AI Company Outputs/Amazon物販事業/<ticket_id>/` への配置確認、Notion 同期 |

ファイルは物理的に `workspace/tickets/<status>/` に **mv** する（コピーではない）。

### waiting の判断基準（重要・2026-05-29 改訂）

**`waiting` 列 = 社長タスク一覧。** 社長が次に手を動かす必要がある状態は、todo/doing を問わず**すべて waiting に置く**。社長は waiting 列だけ見れば自分の番が分かる（旧「📋 社長タスクまとめ」カードは廃止し、この列が役割を引き継いだ）。

waiting に入れる基準：
- §4.1 該当の承認待ち（`requires_approval: true`）
- 納品物の社長レビュー待ち
- 社長への情報提供・URL 共有などの依頼待ち
- 社長自身の手作業待ち（アカウント開設・API キー取得など）
- 判断に迷い社長に確認したい時

判定の合言葉：**「社長が次に動く必要があるか？」→ Yes なら waiting**。
社長のアクションが済んだら waiting → doing（または done）へ戻す。`requires_approval` は §4.1 専用フラグで、waiting の条件とは独立（情報提供待ち等は `requires_approval: false` でも waiting に入る）。

## 起票タイミング

以下のいずれかが発生したら必ず起票します。

- 社長から新規依頼を受信 — **依頼受領 → ただちにチケット起票 → 作業着手** の順を厳守。「ついでに進める」「軽い依頼だから後で起票」は禁止
- 既存タスクの中から派生タスクが発生
- 自発的なメンテナンス（メモリ整理、定期レビュー等）

「小さすぎるから起票しない」は禁止。**例外なく起票**します（後追いで進捗が見えなくなるため）。

## チケット粒度ルール

**1チケット = 1〜2セッション（数時間〜半日）で完了する規模** を目標。

- 大きい依頼（1週間以上かかるもの）は **親子分割** する：
  - **親チケット**：全体ゴールを記述、`labels: [parent]` を付ける
  - **子チケット**：1〜2セッションで完了する単位、frontmatter の `parent_ticket` に親 ID を記載
  - 子は独立して todo→doing→done で動かす（Notion 上でカードが動いて進捗が見える）
  - 親は子がすべて done になった時点で done に
- 例：「Amazon物販ツール網羅調査」（親）の下に「Keepa 個票作成」「SellerSprite 個票作成」…（子）を並列に立てる
- **「Notion で進んでない感」が出るのは粒度が大きすぎるサイン**。3日以上 doing のままなら子分割を検討

## チケット内に記録する4要素

動画分析.md §3-⑤ より。

1. **要件** — 何を達成したいか（社長の言葉を要約）
2. **タスク分解** — 達成までのサブタスク
3. **現在地** — いまどこまで進んだか／次に何をするか
4. **ログ** — 状態遷移と判断の履歴

## メモリへの記録対象

- チケット起票時の判断（なぜこの分解にしたか）
- ルーティングで迷った件
- 社長からの差し戻し理由

→ [../memory/](../memory/) に蓄積。
