---
ticket_id: T-20260902-001
title: ディープリサーチ用プラグインの導入
status: waiting
assignee: secretary
priority: medium
created_at: 2026-09-02
updated_at: 2026-09-02
requires_approval: false
labels: [tooling, research]
parent_ticket: ""
next_check_at: 2026-09-03
related_tickets: [T-20260831-004, T-20260831-005]
---

## 要件

社長依頼「ディープリサーチのプラグインをインストールして下さい」。公式カタログから該当プラグインを導入し、使える状態にする。

## タスク分解

- [x] 公式カタログ（claude-plugins-official / 291件）を全文検索
- [x] 「deep-research」という名称のプラグインは**存在しない**ことを確認
- [x] 候補3件を特定（exa / tavily / youdotcom-agent-skills）
- [x] 最有力の exa をインストール
- [x] 認証方式の特定（APIキーではなく OAuth。非対話セッションでは起動不可と判明）
- [ ] **社長**: 対話ターミナルで `claude` → `/mcp` → `plugin:exa:exa` → Authenticate
- [ ] 疎通確認（`claude mcp list` が connected になるか）

## 現在地

**waiting（社長の番）。** exa プラグインは導入済みだが、MCP サーバ
`https://mcp.exa.ai/mcp?client=claude-code-plugin` が **`Needs authentication`** を返す。
このアプリのセッションは非対話（non-interactive）のため、**カズヨ側で OAuth フローを起動できない**。
社長が対話ターミナルで `claude` を起動し `/mcp` から認証する必要がある。

### 9/2 の訂正
前回「APIキーの登録は不要・匿名で動く」と報告したが、**この構成では誤り**。
README の「匿名でもレート制限付きで動く」は素の URL の話で、プラグイン同梱の
`?client=claude-code-plugin` 付きエンドポイントは OAuth を要求する
（`claude mcp list` の健全性チェックで確認）。

## 調査結果

| 候補 | 提供元 | 内容 | 料金 |
|---|---|---|---|
| **exa** | Exa | Web検索＋**deep research**＋本文抽出。MCPツール＋リサーチskill | APIキー要。新規$10無料クレジット、以降従量課金 |
| tavily | Tavily | search / extract / crawl / research API | APIキー要。無料枠あり（月次クレジット） |
| youdotcom-agent-skills | You.com | 引用付きリサーチ、各種SDK連携ガイド | APIキー要 |

「ディープリサーチ」の記述があるのは exa のみ。

## ログ

- 2026-09-02 doing 起票。カタログ調査 → exa をインストール
- 2026-09-02 waiting へ。MCP が Needs authentication。非対話セッションでは OAuth 起動不可のため社長の対話ターミナル操作待ち
