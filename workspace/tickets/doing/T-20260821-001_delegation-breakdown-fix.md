---
ticket_id: T-20260821-001
title: 「カズヨの抱え込み」再発の原因究明と構造的改善（親）
status: doing
assignee: secretary
priority: high
created_at: 2026-08-21
updated_at: 2026-08-21
requires_approval: false
labels: [organization, routing, meta]
parent_ticket: ""
next_check_at: 2026-08-22
---

## 要件

社長指摘：「最近、依頼をするとカズヨが一人で何でもやってしまう。簡単な作業でもサブエージェントを使わないと、アウトプットの保存先がバラけ、サブエージェントのナレッジが溜まらない」。
原因を特定し、文書ルールではなく**構造**で再発を止める。

## 調査結果（カズヨ／2026-08-21）

1. **【最大】ハーネス側の指示が社内ルールを上書きしていた**
   デスクトップセッションのシステムプロンプトに `Do not call the AgentTool unless the user requested it`（社長が明示的に頼まない限り Agent ツールを使うな）が入っている。
   CLAUDE.md §5「専門領域は必ず担当に発注」と真っ向から衝突し、ハーネス側が優先される。
   → 社長の常時許可（standing authorization）を CLAUDE.md に明文化して解消する。

2. **サブエージェントが「実体」として存在しない**
   `.claude/agents/` が未作成。Agent ツールで選べるのは `general-purpose` 等の汎用型のみで、
   `researcher` / `general_affairs` 等は**呼び出せない**。毎回長いプロンプトを手書きする高コスト作業になり、
   「自分でやった方が速い」が常に勝つ。さらに汎用エージェントには SUBAGENT_PROTOCOL が注入されないため
   **成果物の保存先がバラける**（社長の指摘そのもの）。

3. **チケット frontmatter から `assignee` が消えていた**
   2026-08-11 以降の13枚が `assignee:` を持たず `owner: secretary` に化けている（テンプレは `assignee:`）。
   担当を書く欄が消えれば振り分けは起きない。副次被害として
   - `session-start.sh` は `ticket_id:` を読むが実ファイルは `id:` → リマインダーのID欄が空
   - Notion の Assignee 列が同期されない

4. **強制力（フック）が無い**
   守られているルール（Notion同期・社長タスクまとめ）には PostToolUse / Stop フックがある。
   振り分けルールだけ文書のみ。長いセッションでは文書ルールは薄まる。

5. **結果：ナレッジが溜まっていない（実測）**
   memory件数 = content_creator 0 / legal 0 / planner 0 / simulator 0 / researcher 1 / accounting 1 /
   general_affairs 2 / it_engineer 2 に対し secretary 3。社長の懸念は数字で裏付けられた。

> 補足：2026-05-27・2026-06-01 にも同じ指摘を受け `owner-routing-discipline.md` に記録済み。
> 文書追記だけで対処したため**3回目の再発**。今回は構造（実体＋フック）で止める。

## タスク分解

- [ ] 子: T-20260821-002（タカシ）`.claude/agents/` に9体を登録＋委譲チェックフック
- [ ] 子: T-20260821-003（マリエ）frontmatter 13枚の修復＋Notion/社長タスク同期
- [ ] 子: T-20260821-004（ヒデアキ）CLAUDE.md §5 / routing.md の改訂文
- [ ] カズヨ: 3子の統合・品質確認・社長報告

## 現在地

子チケット3枚を並行発注済み。

## ログ

- 2026-08-21 doing 起票・原因究明完了・子3枚を並行発注
