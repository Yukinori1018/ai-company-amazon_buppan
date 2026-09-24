---
ticket_id: T-20260925-001
title: Amazon「Ready to Sell Checklist」(AGS) を日本語化しPDF化（同レイアウト・写真差し替え）
status: doing
assignee: content_creator
priority: medium
created_at: 2026-09-25
updated_at: 2026-09-25
next_check_at: 2026-09-26
requires_approval: false
labels: [translation, document, amazon]
related_tickets: []
---

## 依頼（社長・2026-09-25）

`~/Downloads/AGS-Ready_To_Sell_Checklist.pdf`（Amazon Global Selling 配布・2ページ・Letter）を
- 日本語に翻訳し、日本語話者に分かりやすい表現へ直す
- 同じレイアウトで、写真はリアルなイメージ写真（フリー素材 or 生成）に差し替える
- PDF で Amazon のフォルダに保存し、フォルダを開く

## 置き場の判断（秘書）

原本は Amazon の著作物（第三者著作物）。リポは PUBLIC のため deliverables には置かず、
§6 ③ `~/Documents/AI Company 素材/Amazon物販事業/ags-ready-to-sell-checklist-20260925/` に README 付きで保存する。

## 現在地

- 制作完了（3稿）。秘書の確認待ち。PDF はリポ外の素材フォルダに保存済み。

## ログ

- 2026-09-25 起票・doing。担当＝コンテンツ制作ヒデアキ（翻訳・紙面制作）。
- 2026-09-25 ヒデアキ着手。原本を pdftoppm/pdftotext で確認。Unsplash の無料写真（Unsplash License）を選定。
- 2026-09-25 1稿：直訳寄り・見出し別行。2ページ目の5番・11番が次の帯に潜る／ヒーロー写真に他社ブランド名が写り込む／1ページ目の下端に白帯（transform:scale の印刷不具合）。
- 2026-09-25 2稿：見出し語＋説明を1段落に流す（原本と同じ組み方）、ヒーロー写真を差し替え、zoom 方式に変更。全項目が収まる。
- 2026-09-25 3稿：受け手目線で通し読み。字間の間延び・1文字の泣き別れ・「ピッキング」の用語・SPN説明の語順を修正。2ページ・Letter で完成。

## 成果物

- （リポ外）`~/Documents/AI Company 素材/Amazon物販事業/ags-ready-to-sell-checklist-20260925/01_出品準備チェックリスト_日本語版.pdf`
- （リポ外）同フォルダ `README.md`（原本の所在・写真の出典とライセンス・リポ外の理由）／`_src/`（組版 HTML・写真・原本の写し）
- 親 README `~/Documents/AI Company 素材/Amazon物販事業/README.md` の「収蔵物」に追記済み
- ※第三者著作物の翻訳のため deliverables には置いていない（リポは PUBLIC）

## 完了報告

完了しました。確認をお願いします。

- 完成度：原本と同じ2ページ・Letter。3稿まで回し、100dpi で原本と左右に並べて比較済み。文字切れ・はみ出しなし
- 写真：Unsplash License の2枚（Mimi Thian / blue sky）。有料版（Unsplash+）は除外し、写真ページごとにライセンス表示を確認
- 妥協点：ロゴは画像ではなく文字で組んだ近似（Amazon のロゴデータは使っていない）。ヒラギノは Chrome の仕様で Type 3 形式で埋め込まれる（表示・印刷・検索に支障なし）
- 引き継ぎ：資料は米国 Amazon.com 向けの2017年版。「FBA輸出」など日本から直接当てはまらない項目がある旨を README に記載
- 「フォルダを開く」は秘書側で実施してください（サブエージェントからは社長の画面操作をしていません）
