---
ticket_id: T-20260904-002
title: ホームページ制作事業リポジトリの雛形生成（本リポの運用ルールを転用）
status: doing
assignee: it_engineer
priority: high
created_at: 2026-09-04
updated_at: 2026-09-04
requires_approval: false
labels: [ops, foundation]
parent_ticket: ""
next_check_at: 2026-09-05
related_tickets: []
---

## 要件

社長から「このリポで決めたルール・運用方法をコピー（必要に応じて修正）して、別プロジェクトに転用できる専用フォルダを作れ」との依頼。作成後は社長が手動でフォルダごと移設する。

- **転用先事業:** ホームページ作成のためのリサーチ・制作事業
- **持ち出す範囲:** 骨格ルール ＋ 汎用ナレッジ（Amazon/Keepa/物販固有のメモリ・成果物・チケットは除外）
- **生成先:** `/Users/yukinori/Claude Code/ai-company-homepage/`（**本リポの外**。本リポは PUBLIC かつ30分毎に `git add -A` → push するため、内側に作ると巨大な複製が公開される）

## タスク分解

- [ ] 生成先フォルダを本リポ外に作成し、ディレクトリ骨格を敷く
- [ ] CLAUDE.md を新事業向けに書き換えて配置（§1 を HP 制作事業に、Amazon 固有の記述を除去）
- [ ] agents/ 9職種の agent.md を移植（Amazon 固有の例示のみ差し替え）
- [ ] 汎用ナレッジのみメモリを選別移植（物販固有は除外）
- [ ] .claude/（hooks / commands / agents / settings）を移植・パス依存の修正
- [ ] workspace/ 骨格（tickets 4状態＋_template.md、output、README、SUBAGENT_PROTOCOL）を移植し中身は空に
- [ ] docs/（notion スキーマ・セットアップ・playbook）と scripts/ を移植
- [ ] .gitignore / .mcp.json.example / README.md を新事業向けに調整
- [ ] 引き継ぎメモ（何を捨てたか・移設後にやること）を新フォルダ直下に置く
- [ ] 秘書が受け入れ確認 → 社長へ報告

## 現在地

2026-09-04 起票、タカシへ発注。

## ログ

- 2026-09-04 doing 起票（社長依頼を受け即着手）
- 2026-09-04 マリエ：Notion カード作成（Status=doing）。labels を [ops, template] → [ops, foundation] に修正。Notion の Labels に `template` オプションが無く、新規オプションを勝手に作らない方針（T-20260904-001 と同じ）に従い、既存の `foundation`（骨格・基盤）へ寄せた。owner-tasks.md も ℹ️ 欄に追記（社長タスクの純増ゼロ）
