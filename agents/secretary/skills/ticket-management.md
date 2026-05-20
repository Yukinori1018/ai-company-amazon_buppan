# スキル：チケット管理

秘書がチケットを起票・更新・移動する際の手順書です。

## チケットファイル形式

すべてのチケットは Markdown ファイル。frontmatter で構造化情報を持ちます。

```markdown
---
ticket_id: T-20260518-001
title: {{ チケットタイトル }}
status: todo            # todo | doing | waiting | done
assignee: secretary      # secretary | accounting | legal | general_affairs | content_creator
priority: medium         # low | medium | high
created_at: 2026-05-18
updated_at: 2026-05-18
requires_approval: false # true なら waiting/ 経由必須
labels: []
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
| doing → waiting | 社長への質問内容を本文に記載、Notion 同期、`requires_approval: true` の場合は理由を明記 |
| waiting → doing | 社長回答をログに記録、Notion 同期 |
| doing → done | 成果物リンクを本文に追記、`~/Documents/AI Company Outputs/{{ 事業名 }}/<ticket_id>/` への配置確認、Notion 同期 |

ファイルは物理的に `workspace/tickets/<status>/` に **mv** する（コピーではない）。

## 起票タイミング

以下のいずれかが発生したら必ず起票します。

- 社長から新規依頼を受信
- 既存タスクの中から派生タスクが発生
- 自発的なメンテナンス（メモリ整理、定期レビュー等）

「小さすぎるから起票しない」は禁止。**例外なく起票**します（後追いで進捗が見えなくなるため）。

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
