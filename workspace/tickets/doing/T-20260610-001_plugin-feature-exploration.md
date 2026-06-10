---
ticket_id: T-20260610-001
title: Claude Code プラグイン機能の検証（社内ツールのプラグイン化）
status: doing
assignee: it_engineer
priority: medium
created_at: 2026-06-10
updated_at: 2026-06-10
requires_approval: false
labels: [dev, tooling, plugin, exploration]
parent_ticket: ""
---

## 要件

社長依頼: 「プラグインの機能を使ってみたい。何か試してほしい」（2026-06-10）。

Claude Code のプラグイン機能を実地で試すため、会社の既存資産（スラッシュコマンド・SessionStart フック・エージェント運用）と同系統の社内ツールを **Claude Code プラグイン `ai-company-toolkit`** として束ね、リポジトリ直下のローカル marketplace 経由で実際に install できる形にする。§7「子会社リポジトリ生成」で各子会社が `/plugin install` だけで会社の道具一式を導入できる布石も兼ねる。

## タスク分解

- [x] プラグイン正式仕様の確認（claude-code-guide エージェントで公式ドキュメント照合）
- [x] `ai-company-toolkit` プラグイン本体を作成
  - [x] `.claude-plugin/plugin.json`（マニフェスト）
  - [x] `commands/ticket.md`（新規チケット起票コマンド）
  - [x] `skills/kpi-check/SKILL.md`（KPI 現状スナップショット）
  - [x] `hooks/hooks.json` + `scripts/greeting.sh`（起動バナー、${CLAUDE_PLUGIN_ROOT} 検証）
  - [x] `agents/ticket-router.md`（依頼ルーティング用サブエージェント）
  - [x] `README.md`（install 手順）
- [x] リポジトリ直下に `.claude-plugin/marketplace.json`（ローカル marketplace）
- [x] JSON 妥当性・スクリプト実行権限の検証
- [ ] 社長に install 手順を提示し、実機で `/plugin marketplace add ./` → `/plugin install` を試してもらう
- [ ] 動作確認後フィードバックを反映、不要なら撤去

## 現在地

プラグイン一式 + ローカル marketplace を作成済み。社長の実機での install テスト待ち。

## ログ

- 2026-06-10 todo 起票 → 即 doing（社長同席の実験タスクのため）
- 2026-06-10 公式プラグイン仕様を確認し、`ai-company-toolkit` プラグイン + ローカル marketplace を実装
