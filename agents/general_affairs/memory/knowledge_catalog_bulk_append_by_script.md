# カタログへの一括追記はスクリプトで行う


## 2026-10-27 T-20261027-001 / T-20261026-002（17行）
- 手順：`git ls-files deliverables/<id>` で追跡済みを確認 → Python の csv.writer で15列を追記（ローカルリンクは HYPERLINK 数式、パスは urllib.parse.quote、GitHub リンクは現ブランチ）→ `sync_catalog_to_sheet.py` → HTTP 200・1028行で確認。
- 担当は README の記述から取る（評価20=監査役、21=マサル）。推測で「監査担当」と書いて直した。
- コミットは CSV だけを `git add` する（作業ツリーに秘書の未コミット変更があるため `-A` を使わない）。
