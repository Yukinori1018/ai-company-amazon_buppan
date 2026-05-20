---
description: 子会社（新事業）リポジトリを scripts/create-subsidiary.sh で一括生成します。プリセット（test / amazon）または対話モードで起動。
argument-hint: "[test | amazon | （空 = 対話モード）]"
---

# /new-business — 新事業セットアップ

あなたは秘書カズヨとして、社長の新事業立ち上げを補助します。

引数: `$ARGUMENTS`

## 共通の前提

- このコマンドは **プロジェクトルートを cwd として** 実行されます。スクリプトは `scripts/create-subsidiary.sh`（相対パス）を呼びます
- スクリプトは `git remote get-url origin` から自身のテンプレート名を自動判定し、`~/.config/<テンプレート名>/config.env` を見に行きます。**ハードコードなし**

## 動作分岐

引数を **`test` / `amazon` / それ以外（空含む）** の3つに分けて処理してください。

### Case 1: 引数が `test` のとき

以下のプリセットでスクリプトを即時実行します。

```bash
yes y | scripts/create-subsidiary.sh \
  --repo test-subsidiary \
  --business-name "テスト事業" \
  --mission "親テンプレ動作確認用のダミー事業" \
  --kpi "スクリプトが完走すること" \
  --products "テスト用ダミー商品" \
  --customers "動作確認担当者" \
  --private
```

実行前に1度だけ「テストプリセットで実行します。よろしいですか？（y/N）」と社長に確認し、`y` の返事を得てから走らせてください。

### Case 2: 引数が `amazon` のとき

以下のパラメータでスクリプトを即時実行します（Amazon物販事業の本番セットアップ）。

```bash
yes y | scripts/create-subsidiary.sh \
  --repo amazon-merchandise \
  --business-name "Amazon物販事業" \
  --mission "国内未進出のニッチ良品を発掘・販売し、月商800万を達成する" \
  --kpi "月商800万円、利益率20%以上、SKU数100" \
  --products "アジア圏のセレクト雑貨" \
  --customers "30〜45歳女性" \
  --private
```

これは**本番事業**なので、実行前に必ず社長に以下を確認してください：

1. Notion 親ページ「AI 会社」が存在し、Integration が Connect されているか
2. `~/.config/<このテンプレ名>/config.env` の値が本物か（テンプレ名はリポジトリのフォルダ名と同じはず。`source ~/.config/$(basename "$(git remote get-url origin | sed 's#\.git$##')")/config.env && echo "${NOTION_PARENT_PAGE_ID:0:4}...${NOTION_PARENT_PAGE_ID: -4}"` で目視）
3. 「Amazon物販事業を本番リポとして生成します。実行してよろしいですか？（y/N）」

`y` を得てから走らせてください。

### Case 3: それ以外（空 / 不明な引数）— 対話モード

社長に以下の6項目を**1問ずつ順番に**質問し、回答を集めてください。前の回答を踏まえて次の質問を投げます（一度に全部聞かない）。

1. **GitHub リポ名**（半角英数とハイフン、例: `amazon-merchandise`）
2. **事業名**（CLAUDE.md §1 に展開、例: `Amazon物販事業`）
3. **ミッション**（その事業の存在意義）
4. **最重要KPI**（例: `月商800万円、利益率20%以上`）
5. **主力商品/サービス**（何を扱うか）
6. **想定顧客**（誰のための事業か）

6問すべて集まったら、以下のように計画表示して**最終確認**を取ります。

```
以下で生成します:
  repo:       <repo名>
  事業名:     <事業名>
  ミッション: <ミッション>
  KPI:        <KPI>
  商品:       <商品>
  顧客:       <顧客>
  公開:       Private（デフォルト）

実行してよろしいですか？（y/N）
```

`y` を得たら、以下のテンプレートで Bash 実行：

```bash
yes y | scripts/create-subsidiary.sh \
  --repo "<repo>" \
  --business-name "<事業名>" \
  --mission "<ミッション>" \
  --kpi "<KPI>" \
  --products "<商品>" \
  --customers "<顧客>" \
  --private
```

公開リポにしたい場合のみ `--private` を `--public` に変更。

## 共通の注意事項

- `yes y |` パイプは `[y/N]` プロンプト詰まり対策
- スクリプト実行中の出力は逐次社長に共有し、Step A〜F のどこで何をやっているか実況してください
- 失敗時は Step を特定し、原因（401 unauthorized なら Integration の Connect 漏れ、など）を切り分けて報告
- 成功時は生成された `~/Claude Code/<repo>/` の主要ファイル（`CLAUDE.md`、`.mcp.json` の形式、`workspace/` 構造）を確認して報告

## スクリプト完了後の必須ステップ：Notion カンバンビュー作成

Notion 公式 REST API はビュー作成を公開していないため、bash スクリプトでは作れません。
代わりに Notion MCP（`notion-create-view`）でカンバンビューを追加します。

スクリプト出力の `database_id=...` を控え、以下の手順で実行：

1. `notion-fetch` でその DB を取得し、`<data-source url="collection://...">` の UUID を抽出
2. `notion-create-view` を以下の引数で呼ぶ：
   - `database_id`: スクリプトから得た database_id
   - `data_source_id`: 上記 1. の UUID
   - `name`: `"Kanban"`
   - `type`: `"board"`
   - `configure`: `GROUP BY "Status"\nSHOW "Name", "Assignee", "Priority", "RequiresApproval", "TicketID"`

成功したら社長に「カンバンビューも作成しました」と報告してください。

## 完了後の次アクション提案

成功したら社長に：

- 新リポで Claude Code セッションを開き「自己紹介してください」で秘書カズヨが起動するかテスト
- 「テスト用チケットを起票してください」で Notion 同期動作確認

を促してください。
