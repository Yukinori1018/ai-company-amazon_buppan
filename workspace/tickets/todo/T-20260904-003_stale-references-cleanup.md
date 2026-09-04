---
ticket_id: T-20260904-003
title: 実体が消えたのに参照だけ残った記述の一括是正（まとめカード404ほか6箇所）
status: todo
assignee: it_engineer
priority: medium
created_at: 2026-09-04
updated_at: 2026-09-04
requires_approval: false
labels: [ops, foundation]
parent_ticket: ""
next_check_at: 2026-09-08
related_tickets: [T-20260904-002]
---

## 要件

T-20260904-002（ホームページ制作事業リポの雛形生成）で本リポを横断精査した結果、**実体が既に無いのにルール文・フック・スキルだけが古い参照を保持している箇所**が6件見つかった。雛形側では是正済みだが、本リポには残っている。放置するとマリエが4回目の 404 を踏む。

固有名詞（Amazon/Keepa 等）を含まないため、通常の grep では引っかからない類の不備。

## 是正対象

### A. Notion「社長タスクまとめ」カードの矛盾（実体は404・Status に「まとめ」列なし）

CLAUDE.md §6 は「旧まとめカードは廃止し waiting 列が役割を引き継いだ」と書いているのに、以下がまとめカードの更新を要求し続けている。**waiting 列＝社長タスク一覧に一本化する**（雛形側の文言を流用可）。

- [ ] `CLAUDE.md` §3 鉄則8 — 「Notion『社長タスクまとめ』カード（Status=「まとめ」列）」の記述
- [ ] `.claude/hooks/owner-tasks-sync-check.sh` — `CARD_ID` 変数とリマインド文
- [ ] `workspace/owner-tasks.md` 冒頭 — 「Notion の『まとめ』カードと同じ内容を保つ」
- [ ] `.claude/agents/general-affairs.md` — マリエの責務からまとめカード更新を削除

### B. 存在しない節への参照

- [ ] `agents/secretary/skills/notion-ticket-sync.md` — CLAUDE.md 鉄則7 が指す `§チケット言及時の即時同期確認` が実在しない。**節を新設**する（参照を消すのではなく、鉄則7 が要求する運用を書く）
- [ ] `.claude/hooks/delegation-check.sh` — `routing.md §着手前の可視化` を指すが、実体は `§振り分けの原則` に改題済み

### C. 初回精査で見つかった不備3件

- [ ] `workspace/README.md` — 「最終納品物はリポ外」の旧ルールのまま（CLAUDE.md §6 は3層ルールに移行済み）
- [ ] `docs/notion-setup-guide.md` — Assignee 選択肢が5職種のまま（実態は9職種＋owner）
- [ ] `agents/general_affairs/agent.md` — `skills/owner-tasks-summary-ownership.md` へのリンク切れ（実体は `memory/` 配下）

## 完了条件

- 上記9箇所を是正し、Markdown 相対リンク切れ 0 件
- シェルスクリプトは `bash -n` ＋ 実行スモークテストを通す
- 是正後、雛形リポ（`ai-company-homepage`）との規範差分が「事業固有の記述」だけになっていること

## 参考

雛形側の是正済みファイルが手本になる: `/Users/yukinori/Claude Code/ai-company-homepage/` の同名ファイル（commit `1557aa0`）。
知見は `agents/it_engineer/memory/knowledge_repo_scaffold_distillation.md` に記録済み。

## ログ

- 2026-09-04 todo 起票（T-20260904-002 の副産物として発見）
