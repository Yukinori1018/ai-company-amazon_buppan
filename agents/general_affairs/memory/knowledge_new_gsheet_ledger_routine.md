# 新しい台帳シートを作る定型手順（2026-09-30 / T-20260930-001 メーカー連絡先台帳）

同日に「商品判定台帳」に続き2本目。以後この型で10分で終わる。

1. Drive MCP `create_file`（contentMimeType=`application/vnd.google-apps.spreadsheet`・中身なし）→ 社長所有・My Drive 直下に空シート。
2. Drive MCP `share_file` で SA `sheets-writer@claude-session-sheets.iam.gserviceaccount.com` を writer に。**社長の手は不要**（MCP が社長権限で共有できる）。
3. gspread で `update_title`（タブ名）→ `values_update`（USER_ENTERED で HYPERLINK 数式可）→ `batch_update` で 固定行・太字ヘッダ・basicFilter・条件付き書式（TEXT_STARTS_WITH で判定列を色分け）・データ入力規則（ONE_OF_LIST, strict）・列幅。
4. **投入後に元CSVと全セル突合**（USER_ENTERED は先頭0の数字や日付風の文字列を化けさせる）。今回は不一致0。
5. 自動メモリに reference（id・URL・列・運用）＋MEMORY.md の Reference 節に1行。
6. 成果物カタログには「種別=Googleスプレッドシート／公開状態=ローカルのみ／ローカルリンク=シートURLのHYPERLINK／GitHub・パス空欄」で1行。

## 落とし穴
- **Python の csv.writer は既定で CRLF**。LF のマスターCSV に追記すると改行混在になる。`lineterminator="\n"` を指定するか、追記後に `perl -pi -e 's/\r$//'`。今回踏んだ。
- カタログで T-20260930-001 は 01 しか載っておらず 02〜05・README が追記漏れだった → 同時に補完（長期チケットは段ごとの成果物が漏れやすい。knowledge_catalog_gap_longrunning_tickets と同型）。
- Notion「社長タスク」は専用カードが無い（404）。waiting 列への移動＝社長タスク掲示。
