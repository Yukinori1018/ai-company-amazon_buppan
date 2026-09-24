# 単発カード同期の手順（再利用用）

## 2026-09-25 T-20260925-001（新規 doing・content_creator）
- 手順: notion-search（data_source_url=collection://366b0a40-44fa-81ec-8342-000b6d0a25e0, query=TicketID）で重複なし確認 → notion-create-pages で作成（RequiresApproval="__NO__"、日付は展開キー）。
- リポ外成果物（第三者著作物→素材フォルダ）のチケットは、カード本文の `## 成果物` に localhost URL ではなく素材フォルダのパスをテキストで置く。
- Labels は未同期（translation/document/amazon の選択肢存在が未確認のため省略）。社長タスク発生なし＝owner-tasks.md 変更不要。

## 2026-09-25 T-20260925-001（doing → waiting・納品レビュー待ち・任意）
- 手順: notion-fetch で現状確認 → update_properties（Status=waiting／UpdatedAt／Description を「納品済み・確認任意・目安日」に）→ replace_content で `## 結果要約`（waiting=納品済&待ち事項）と `## 成果物`（リポ外は素材フォルダのパスをテキストで）を差し替え。
- owner-tasks.md は最上段に「更新N」節を足し、**任意の確認は 🔴 ではなく ℹ️ 枠**に置く。他チケットの 🔴 状態は未確認なら「下の更新N-1のまま（未確認）」と明記し、勝手に書き換えない。最終更新行は先頭追記＋「／前: 」でぶら下げ。
- 2,700行超の owner-tasks.md は Read が上限超えで失敗する。grep -n で行番号を取り、Python で行挿入する。
- リポ外成果物（第三者著作物）はカタログ行の追記対象外（カタログは deliverables/ のミラー）。
