
- 2026-09-15 T-20260915-001：新規 doing 起票の同期。SQL で TicketID 重複なしを確認 → create-pages（data_source 366b0a40…、ParentTicket も設定）→ チケットログに URL 付き1行。所要3手。

## 2026-09-15 T-20260915-001 doing→waiting（手順の再利用形）
- frontmatter(status/assignee/updated_at/next_check_at)→やることチェック→ログ1行（`## 成果物` の直前に追記）→`git mv` で waiting/ へ→Notion update_properties（Status・Assignee）→owner-tasks.md 先頭に更新番号を振って追記→最終更新行も差し替え→commit。
- 「無ければ追加」の確認は owner-tasks を grep し、**取り下げ済み（取消線）の行は「無い」扱い**にする（T-20260912-001 返信先⑫は 9/14 に取り下げ済みだったので独立行で立て直した）。
