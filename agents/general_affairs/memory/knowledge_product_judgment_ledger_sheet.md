# 商品判定台帳（Googleシート）の作り方と運用 — 2026-09-30 / T-20260920-003

## 依頼の型（再利用可能）

社長「**表はスプレッドシートに貯めていって下さい。新しいスプレッドシートを作って下さい。**」
= ①Drive MCP で社長所有の空シートを作る → ②`share_file` で SA に編集者共有 → ③`gspread` で投入＋書式。

**今回の発見：SA への共有は社長の手を借りずに Drive MCP の `share_file` で完了できる。**
memory の `reference_gsheets_service_account.md` は「②社長がそのシートをSAへ共有（1回だけ）」と書いてあるが、
`mcp__…__share_file(fileId, emailAddress=sheets-writer@…, role="writer")` で自動化できた。
**社長にお願いする一手ではない**（[[feedback_never_make_owner_run_commands]]）。

手順（4コール）:
1. `create_file(title, contentMimeType="application/vnd.google-apps.spreadsheet", parentId="root")` → file id
2. `share_file(fileId, "sheets-writer@claude-session-sheets.iam.gserviceaccount.com", "writer")`
3. `gspread.open_by_key(id)` → `ws.update_title` / `ws.resize` / `ws.update(values=...)`
4. `sh.batch_update({"requests":[...]})` で 固定行・`setBasicFilter`・列幅・条件付き書式

## 書式の勘どころ（次回そのまま使える）

- **固定行**: `updateSheetProperties` + `gridProperties.frozenRowCount=1`（`fields` 指定を忘れると無視される）
- **フィルタ**: `setBasicFilter` に `startRowIndex:0` と `endColumnIndex` を必ず入れる
- **条件付き書式**: `addConditionalFormatRule` を `index` 0,1,2 で3本。`TEXT_EQ` は完全一致なので GO と NO-GO は衝突しない
- **長文列は `wrapStrategy:"WRAP"` ＋ `verticalAlignment:"TOP"`**。判定理由・確認方法は300〜400px 幅にすると読める
- 列幅は `updateDimensionProperties` を列ごとに1リクエスト。32列でも1回の `batch_update` に同梱できる

## PUBLIC リポとの切り分け（重要）

**リポ内にミラーCSVは作らない**と判断した。理由2つ：
1. 卸率・購入先URL は会員限定の取引条件で PUBLIC リポに書けない（`source-terms-guard`）。マスキングしたミラーは**判定に使えない表**になり、置いた意味がない
2. 二重管理は実際に事故っている（2026-08-26 T-20260817-004：同一チケットの2ファイルで内容が食い違った）

→ **シートが正**。リポ側に置くのは**所在だけ**（memory の reference ＋ CLAUDE.md §3.2 の2行）。
「可視性」と「公開」は別の軸（[[knowledge_deliverables_gitignore_allowlist_trap]] と同じ教訓）。

## 成果物カタログには載せない

deliverables/ にファイルが出ていないため、カタログCSV の追記対象外。
**シートは「成果物」ではなく「運用中の台帳」**。カタログ（`1xXfKbgbb…`）と本台帳（`1ppyXCnp2S…`）は別物で、混ぜると両方が信用を失う。

## 反映確認は必ず画面で

書き込みレスポンス（`OK <url>`）だけで完了と言わない。今回は
①`get_all_values` で API 読み返し（4行32列・frozen/filter/CF 3本）→ ②社長の Chrome で実際に開き、
**NO-GO が赤・GO が緑に付いていること**を目視した。[[feedback_verify_where_owner_looks]]。
