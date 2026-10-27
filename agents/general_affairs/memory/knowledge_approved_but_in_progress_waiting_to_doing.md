# 社長承認が出たが作業が残るチケットは waiting→doing（2026-10-27 T-20261027-001）

- 承認が出た時点で「社長の番」ではなくなる。担当（今回はタカシの CLAUDE.md 差し替え）が作業中なら doing に移す。done にはしない。
- owner-tasks は該当行を取り消し線＋「社長対応済み YYYY-MM-DD（何を承認したか）」にし、残る行（㉛）は残す。最終更新行は「前:」で旧版を残して先頭に追記。
- 「次の自動同期で成功するか確認」系の行は、`workspace/.sync/github-sync.log` の最終時刻と `git reflog` のブランチ切替時刻を比べる。切替が最終同期より後なら、まだ未検証＝「次回の同期で確認」と書く（今回は切替 19:46・最終同期 19:24）。
- Notion は data_source 366b0a40-... を TicketID で search → update_properties（Status・UpdatedAt）だけで足りる。
