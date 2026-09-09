# Notion カード本文へ「成果物」欄を入れる手順

対象：庶務マリエ（Notion 同期の責務者）

## 前提

- 真実は `workspace/tickets/` のファイル。Notion はその片方向ミラー。
- Notion への書き込みは**ホスト型 MCP（`notion-update-page`）でしか行えない**。
  ローカルにトークンが無いため、シェルスクリプトからは書けません。
- したがって「変換はスクリプト、書き込みは MCP」の2段構えになります。

## 手順

### 1. 配信サーバを起動する

```bash
python3 scripts/catalog/serve_deliverables.py --status   # 起動確認
python3 scripts/catalog/serve_deliverables.py            # 起動（前景。Ctrl-C で停止）
```

### 2. 変換してリンク切れを潰す

```bash
python3 scripts/notion/build_deliverable_blocks.py --check-links
python3 scripts/notion/build_deliverable_blocks.py --json /tmp/payload.json
```

`--check-links` が non-200 を1本でも出したら、そこで止めて原因を直します。
リンク切れのまま Notion に貼ると、社長のクリックが空振りします。

### 3. Notion のカード ID を引く

`notion-query-data-sources`（view モード）で Table view を読み、`TicketID` → `url` の対応表を作ります。

- Data Source: `collection://366b0a40-44fa-81ec-8342-000b6d0a25e0`
- Table view: `https://www.notion.so/366b0a4044fa81788359d44b4f807458?v=366b0a4044fa81dcbb14000c73f916c1`

> **SQL モードはワークスペースの利用上限に当たります**（2026-09-09 に実際に当たった）。
> view モードは上限なしなので、全件列挙は view モードで行うこと。
> 1ページ100行なので、`next_cursor` で2ページ目を取ります。

### 4. 書き込む

各カードに `notion-update-page` を投げます。

```
page_id: <カードの page id>
command: "insert_content"
position: {"type": "end"}
content: <build_deliverable_blocks.py の出力>
```

- **`insert_content` を使う。** `replace_content` は既存本文を消すので使わない。
- 10件前後を1メッセージにまとめて並列で投げると速い（138枚で12ラウンド程度）。
- **既に `## 成果物` ブロックがあるカードに `insert_content` すると重複します。**
  更新時は先に `notion-fetch` で本文を読み、`update_content`（old_str / new_str）で置き換えること。

### 5. 読み返して検証する

**書き込み API の成功レスポンスを根拠に「完了」と書かないこと。**
`notion-fetch` で実物を読み返し、次の3点を確認します。

1. `## 成果物` ブロックが存在する
2. リンクが1本以上ある（成果物ありのチケットの場合）
3. 重複していない

## 以後の運用（恒久ルール）

チケットの `## 成果物` 節を更新したら、**同じ turn で Notion カード本文も更新する**。
節だけ直して Notion を放置するのは、社長から見れば「やっていない」と同じです。
