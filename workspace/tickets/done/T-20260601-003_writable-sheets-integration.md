---
ticket_id: T-20260601-003
title: 書き込み可能な Google Sheets 連携の整備（カタログをURL固定で増分反映）
status: done
assignee: it_engineer
priority: high
created_at: 2026-06-01
updated_at: 2026-06-01
completed_at: 2026-06-01
requires_approval: false
labels: [google-sheets, integration, catalog, ops, it]
related_tickets: [T-20260601-001]
next_check_at: 2026-06-02
---

## 背景

T-20260601-001 で成果物カタログのGoogleスプレッドシートを作成済み
（id `1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY`）。
ただし現状の Google Drive コネクタは **新規作成専用でセル追記・更新APIを持たない**ため、
既存シートへ URL を変えずに増分反映できない。社長は B（今すぐ整備）を選択（2026-06-01）。

## ゴール

- **同じスプレッドシート（URL固定）に行を追記・更新できる**仕組みをタカシが整備する。
- マスターCSV（`workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`）を真実に、
  そこからシートへ同期する**ワンコマンドのヘルパー**を用意する。
- **社長の手間は一度きりの初期設定を最小**に。以後の更新はエージェント側で完結。

## 検討した手段（タカシが最適案を選定）

| 案 | 概要 | 社長の手間 | ローカル/クラウド | 備考 |
|---|---|---|---|---|
| A. Apps Script Web App | シートに紐づくスクリプトを deploy、POSTで追記 | スクリプト貼付＋認可＋deploy（一度） | **両方可** | 認証情報をローカルに置かない・URL固定。**推奨候補** |
| B. gspread + OAuthクライアント | GCPプロジェクト＋OAuth client.json | GCPコンソール設定が多い | ローカルのみ | 標準だが初期設定が重い |
| C. サービスアカウント + 共有 | SAキー作成しシートを共有 | SA作成＋共有（一度） | ローカルのみ | JSONキーをローカル保管 |

> レジストリに書き込み可能な Sheets コネクタは存在せず（2026-06-01 確認）、ローカル実装が必要。

## 成果物（予定）

- 採用案の選定理由（A/B/C＋推奨）
- 連携コード／Apps Script／ヘルパースクリプト（`scripts/` 配下）
- **社長の一度きり初期設定手順**（クリック数最小・スクショ相当の手順書）
- 動作確認（テスト1行 append → 反映確認 → 取り消し）

## ログ

- 2026-06-01 起票。社長が B 採択。レジストリに Sheets 書込コネクタ無しを確認、ローカル実装方針。タカシに設計＋実装を発注。
- 2026-06-01 タカシが Apps Script Web App 案（A）で実装（`scripts/catalog/` 一式・社長設定10手順README・dry-run確認）。
- 2026-06-01 社長が一度きり設定を実施。初回は未審査アプリ警告（Advanced→移動→許可で通過）、次にアクセス権「全員」未設定で HTTP 401 → デプロイ設定を「全員」に修正し再デプロイ。`.catalog_sync.env`（gitignore）に URL・トークン設定。
- 2026-06-01 **実通信テスト成功（HTTP 200・56行×12列を全置換ミラー書き込み）**。URL固定の書き込み連携が稼働。CLAUDE.md §6＋庶務スキルを「稼働中」に更新。**done**。
