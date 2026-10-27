
- 2026-09-15 T-20260915-001：新規 doing 起票の同期。SQL で TicketID 重複なしを確認 → create-pages（data_source 366b0a40…、ParentTicket も設定）→ チケットログに URL 付き1行。所要3手。

## 2026-09-15 T-20260915-001 doing→waiting（手順の再利用形）
- frontmatter(status/assignee/updated_at/next_check_at)→やることチェック→ログ1行（`## 成果物` の直前に追記）→`git mv` で waiting/ へ→Notion update_properties（Status・Assignee）→owner-tasks.md 先頭に更新番号を振って追記→最終更新行も差し替え→commit。
- 「無ければ追加」の確認は owner-tasks を grep し、**取り下げ済み（取消線）の行は「無い」扱い**にする（T-20260912-001 返信先⑫は 9/14 に取り下げ済みだったので独立行で立て直した）。

## 2026-10-26 T-20261026-002（新規 doing・IT）
- 手順：notion-search を data_source_url=collection://366b0a40-44fa-81ec-8342-000b6d0a25e0 に絞って TicketID 検索 → 未存在を確認 → notion-create-pages（parent=data_source_id）で1回作成。重複作成を防ぐため「検索→作成」の2手を省かない
- 本文は `## 結果要約`（doing＝現在地と次の手）＋ `## 成果物`（なし＋理由）の2節。§9 の「欄ごと省略しない」を守る
- 結果：page 405b0a40-44fa-81d9-b6e3-dc2f0c9040d7 作成成功・書式エラーなし

## 2026-10-27 T-20261027-001 新規カード作成（doing）
- 既存確認は `notion-query-data-sources` の rows モード（data_source_url=collection://366b0a40-44fa-81ec-8342-000b6d0a25e0、TicketID string_is）で1発。0件を確認してから create。
- `notion-create-pages` は parent=data_source_id、allow_async=false で即 page id を取得（後続更新に使える）。
- Labels（process/claude-md/hooks）は選択肢未定義の恐れがあるため今回は未設定。必要になったら選択肢追加後に付ける。
- カード: https://app.notion.com/p/405b0a4044fa81dc833df915fc2e8304
