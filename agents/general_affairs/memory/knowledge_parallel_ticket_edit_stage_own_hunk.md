# 並列編集中のチケットに1行足すとき — index には「自分の1行だけ」を載せる

記録日: 2026-09-12（マリエ / T-20260912-002〜005 の Notion 同期）

## 状況

カズヨが同日に4枚起票（commit 4b7c1b6）。同期依頼を受けた時点で、
`T-20260912-003` は**サトルが並列で編集中**（working tree に「現在地」「ログ」への追記が未コミットで乗っていた）。
私の仕事はそのファイルの `## ログ` に1行（Notion カード URL）を足すだけ。

## 落とし穴

`git add <file>` すると、**サトルの未コミット編集も私のコミットに巻き込まれる**。
壊れはしないが、「マリエの同期コミット」にサトルの作業内容が混ざり、履歴が読めなくなる。
`git add -A` 禁止（deliverables に書き込み中）と同じ理由で、**ファイル単位の add でも巻き込みは起きる**。

## 採った手順（再利用可）

1. **書き込み直前にファイルを読み直す**（Python で open → 挿入 → 書く。Edit ツールの古いスナップショットで上書きしない）
2. 挿入位置は `## ログ` 節の**最初の箇条書き（起票行）の直後**に固定。サトルの `###` 小節の中には入れない
3. index には HEAD + 自分の1行だけを載せる：
   ```
   git show HEAD:<file> | python3 -c '（同じ挿入）' > /tmp/x.md
   BLOB=$(git hash-object -w /tmp/x.md)
   git update-index --cacheinfo 100644,$BLOB,<file>
   ```
   working tree はそのまま（サトルの編集＋私の1行）。サトルが後で `git add` すれば彼の分だけが彼のコミットに入る。
4. `git commit` は `-m` でファイルを列挙せず、index に載せたものだけを commit する（パス指定すると working tree が使われて巻き込む）

## ついでの学び

- **発注文のラベル一覧を信用せず、frontmatter と Notion スキーマを自分で突き合わせる。** 「`blue-ocean` `master-plan` `plan` が無ければ追加」と指示されたが、-005 の `simulation` も未登録だった。1枚だけ Labels が黙って落ちるところだった（multi-select はスキーマ外の値をエラー無しで無視する）。
- `ALTER COLUMN "Labels" SET MULTI_SELECT(...)` は全置換だが、**同名を渡せば既存の option ID は保持される**（51→55 で既存 URL 不変を確認）。色も既存どおりに写すこと。
- 4枚同時作成は `notion-create-pages` の `pages` 配列1回で済む。`allow_async: false` にすると URL がその場で返る。
- 社長タスク増減ゼロの回でも、owner-tasks.md は「最終更新」行の更新⑯＋ ℹ️ 節に1ブロックの2点セット。todo/doing は 🔴🟡🟢 に入れない（`knowledge_stale_reference_404.md` の型）。
