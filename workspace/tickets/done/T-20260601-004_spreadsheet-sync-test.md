---
ticket_id: T-20260601-004
title: スプレッドシート連携テスト（新規成果物をカタログ追加→同期反映を実証）
status: done
assignee: it_engineer
priority: medium
created_at: 2026-06-01
updated_at: 2026-06-01
completed_at: 2026-06-01
requires_approval: false
labels: [google-sheets, catalog, test, ops]
related_tickets: [T-20260601-001, T-20260601-003]
next_check_at: 2026-06-02
---

## 目的

T-20260601-003 で整備した書き込み連携（Apps Script Web App）が、**新しい成果物が出たときに
カタログへ行を追加 → 同一URLのシートへ反映**まで一気通貫で回ることを、実際の成果物で実証する。

## 成果物

- **連携方法まとめ**（このテストの題材かつ実際のドキュメント）:
  `workspace/output/deliverables/T-20260601-004/sheets-integration-summary.md`（＋ `.html`）
  - 内容＝今回の Google スプレッドシート連携の仕組み・構成・運用・トラブルシュートのまとめ。

## テスト手順（実証）

1. 上記まとめ（md/html）を作成。
2. マスターCSV（`deliverables-catalog.csv`）へ本成果物の行を追記。
3. `python3 scripts/catalog/sync_catalog_to_sheet.py` を実行（全置換ミラー同期）。
4. シート行数が増えて反映されていることを確認（Drive コネクタで読み戻し）。

## 合格基準

- 同期コマンドが HTTP 200 で成功し、書き込み行数がカタログ行数＋ヘッダーと一致。
- 追加した「連携方法まとめ」の行がシートに存在する。

## テスト結果（2026-06-01・合格）

1. 「連携方法まとめ」を md＋html で作成（`T-20260601-004/sheets-integration-summary.md/.html`）。
2. マスターCSVへ本成果物の行を追記（56→57行）。
3. `python3 scripts/catalog/sync_catalog_to_sheet.py` → **HTTP 200・57行×12列**を全置換ミラー書き込み。
4. Drive コネクタでシートを読み戻し、末尾に T-20260601-004 行が存在することを確認。

→ **合格基準を満たす**（書込行数＝カタログ57行＋一致、追加行がシートに反映）。連携の追加更新フローが実証された。

## ログ

- 2026-06-01 起票。社長依頼で連携の実地テストを実施 → 上記手順で実証し合格。**done**。
