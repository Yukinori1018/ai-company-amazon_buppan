# 子会社セットアップガイド（完全版）

親テンプレート（`ai-company-template`）から **新しい子会社リポジトリを作って稼働開始するまで**の手順です。

> **⚡ 自動スクリプトあり:** Step 1〜6 は `./scripts/create-subsidiary.sh` で自動化できます。詳細は [scripts/README.md](../scripts/README.md)。
> 本ドキュメントは **手動版／スクリプトで詰まった時のフォールバック** として残しています。
>
> **所要時間:** 40分〜1時間（初回）／2回目以降は20〜30分
> **前提:** Mac（zsh/bash）、Git、Homebrew、Notion アカウント、GitHub アカウント

---

## 全体像（7ステップ）

| Step | やること | 所要時間 |
|------|---------|---------|
| 1 | GitHub Template から複製 | 2分 |
| 2 | ローカルに clone | 3分 |
| 3 | プレースホルダー穴埋め | 5分 |
| 4 | Notion セットアップ | 15〜25分 |
| 5 | `.mcp.json` 設定 | 5分 |
| 6 | 最終納品物フォルダ作成 | 1分 |
| 7 | 動作確認（4テスト） | 10分 |

最後に **完成のチェックリスト** で全項目を確認します。

---

## Step 1: GitHub Template から複製

1. ブラウザで [親テンプレート（ai-company-template）](https://github.com/Yukinori1018/ai-company-template) を開く
2. 右上の緑色 **"Use this template"** → **"Create a new repository"**
3. 設定：
   - **Repository name:** 事業名を kebab-case で（例：`amazon-merchandise`、`note-creator-business`）
   - **Description:** 一文で事業内容
   - **Private** を推奨（事業ノウハウや顧客情報を扱うため）
4. **Create repository** をクリック

---

## Step 2: ローカルに clone

### 2.1 ターミナル起動

Spotlight（Cmd+Space）→ `terminal` → Enter。

### 2.2 親フォルダに移動して clone

```bash
cd "/Users/yukinori/Claude Code"
git clone https://github.com/<your-account>/<new-repo>.git
cd <new-repo>
ls
```

`CLAUDE.md` `README.md` `agents` `docs` `workspace` が並べばOK。

### 2.3 認証で詰まったら

| エラー | 対処 |
|-------|------|
| `Repository not found` | Private リポなので gh CLI 認証が必要：`gh auth login`（HTTPS → ブラウザ認証） |
| `Permission denied` | 同上 |
| `command not found: gh` | `brew install gh` してから `gh auth login` |

---

## Step 3: プレースホルダー穴埋め

`CLAUDE.md` 内の `{{ }}` 形式のプレースホルダーを実際の値に置き換えます。

### 3.1 置換する値を決める

| プレースホルダー | 例（Amazon物販事業の場合） |
|---------------|--------------------------|
| `{{ 事業名 }}` | Amazon物販事業 |
| `{{ ミッション }}` | 国内未進出のニッチ良品を発掘・販売し、月商800万を達成する |
| `{{ 最重要KPI }}` | 月商800万円、利益率20%以上、SKU数100 |
| `{{ 主力商品/サービス }}` | アジア圏のセレクト雑貨（並行輸入） |
| `{{ 想定顧客 }}` | 30〜45歳の女性、ライフスタイル感度の高い層 |

### 3.2 一括置換（推奨：`sed` でワンライナー）

ターミナルで以下を**1行ずつ**実行（値は上記で決めたものに置換）：

```bash
sed -i '' 's/{{ 事業名 }}/Amazon物販事業/g' CLAUDE.md
sed -i '' 's/{{ ミッション }}/国内未進出のニッチ良品を発掘・販売し、月商800万を達成する/g' CLAUDE.md
sed -i '' 's/{{ 最重要KPI }}/月商800万円、利益率20%以上、SKU数100/g' CLAUDE.md
sed -i '' 's/{{ 主力商品\/サービス }}/アジア圏のセレクト雑貨（並行輸入）/g' CLAUDE.md
sed -i '' 's/{{ 想定顧客 }}/30〜45歳の女性、ライフスタイル感度の高い層/g' CLAUDE.md
```

### 3.3 ⚠️ よくある間違い

**置換は `{{ }}` の波括弧ごと**消すこと。

```
❌ 誤: - **事業:** {{ Amazon物販事業 }}    （波括弧が残っている）
✅ 正: - **事業:** Amazon物販事業
```

エディタの検索＆置換を手動で使う場合も、**検索文字列に `{{` と `}}` を含める**こと。

### 3.4 残存チェック

```bash
grep -n "{{ " CLAUDE.md
```

§7（プレースホルダー説明表）と §3 鉄則6項目の説明文だけが残ればOK（説明文として意図的）。§1（ミッション）に `{{ }}` が残っていたら置換漏れ。

### 3.5 他ファイルも軽くチェック

README.md / workspace/README.md / docs/ 配下にも `{{ 事業名 }}` が散らばっています。気になるなら同様に sed で全置換：

```bash
grep -rl "{{ 事業名 }}" . --include="*.md" --exclude-dir=docs/reference | xargs sed -i '' 's/{{ 事業名 }}/Amazon物販事業/g'
```

エージェント名（カズヨ・ハジメ・ハルオ・マリエ・ヒデアキ）を事業色に合わせて変えたい場合は、各 `agents/<role>/agent.md` を編集してください。

---

## Step 4: Notion セットアップ

カンバンボードと Integration（MCP 用）を整えます。

### 4.1 データベース作成

1. Notion で新規ページを作成（任意のワークスペース内）
2. 本文に `/database` と入力 → **Database - Full page** を選択
3. ページタイトル：**`<事業名> Tickets`**（例：`Amazon物販事業 Tickets`）

### 4.2 プロパティを10個追加

DB 上部のプロパティ列の **+** ボタンで1つずつ追加。**型と選択肢の名前を完全一致**させること。

| プロパティ名 | 型 | 選択肢の値 |
|------------|-----|----------|
| Name | Title | （既存・そのまま） |
| TicketID | Text | — |
| Status | **Status** | `todo`, `doing`, `waiting`, `done` |
| Assignee | Select | `secretary`, `accounting`, `legal`, `general_affairs`, `content_creator` |
| Priority | Select | `low`, `medium`, `high` |
| RequiresApproval | Checkbox | — |
| Description | Text | — |
| CreatedAt | Date | — |
| UpdatedAt | Date | — |
| Labels | Multi-select | （空でOK） |

> **重要:** Status は「Status型」（Select型ではない）。値の名前は **大文字小文字も含めて完全一致**（`Todo` ではなく `todo`）。

詳細仕様は [notion-board-schema.md](notion-board-schema.md) も参照。

### 4.3 カンバンビュー追加

1. ページ上部の **+ Add view** → **Board**
2. ビュー名は `カンバン` 等
3. **Group by** = `Status`
4. 列に `todo / doing / waiting / done` が並べばOK

### 4.4 Integration Token を発行

1. ブラウザで [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations) を開く
2. **+ New integration** をクリック
3. 設定：
   - **Name:** `<事業名> MCP`（例：`Amazon物販 MCP`）
   - **Associated workspace:** DB を作ったのと同じワークスペース
   - **Type:** **Internal**
4. **Save**
5. **Internal Integration Secret** をコピー
   - `ntn_` または `secret_` で始まる長い文字列
   - **⚠️ このトークンは一度しか完全表示されない**。メモ帳など安全な場所に控える

### 4.5 Integration を DB に接続

1. Notion で「<事業名> Tickets」DB ページに戻る
2. 右上 **`...`** → **コネクト** → **+ コネクトを追加**
3. `<事業名> MCP` を検索 → 追加
4. 確認ダイアログで **承認**

> 「共有」メニュー（人間ユーザーのアクセス管理）とは別物です。Integration は必ず**コネクト**メニューから追加します。

### 4.6 Database ID を取得

1. DB ページの URL をブラウザのアドレスバーからコピー
2. URL の構造：
   ```
   https://www.notion.so/<workspace>/<32文字のDB_ID>?v=<view_id>&source=copy_link
                                     └─ ここだけ ─┘
   ```
3. **`?` より後ろは全部不要**。`/` の直後にある **32文字の英数字**だけが Database ID

### 4.7 ⚠️ 注意：ボット user ID と DB ID は別物

Integration の bot user ID と DB ID は**ぱっと見似ている**ことがあります（先頭8文字が偶然同じになる等）。混同しないこと。

判別法：
- DB ID は **DB ページの URL** から取る
- bot user ID は **my-integrations の Integration 詳細画面** か API レスポンスにある

---

## Step 5: `.mcp.json` 設定

### 5.1 雛形をコピー

```bash
cp .mcp.json.example .mcp.json
```

### 5.2 設定値を埋める

`.mcp.json` をエディタで開き、以下の2箇所を埋めます。

```bash
open -e .mcp.json
```

雛形の中身：

```json
{
  "mcpServers": {
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "OPENAPI_MCP_HEADERS": "{\"Authorization\": \"Bearer {{ NOTION_API_KEY }}\", \"Notion-Version\": \"2022-06-28\"}",
        "NOTION_DATABASE_ID": "{{ NOTION_DATABASE_ID }}"
      }
    }
  }
}
```

**書き換え方:**
- `{{ NOTION_API_KEY }}` → Step 4.4 でコピーしたトークン（`ntn_...` または `secret_...`）に置換
- `{{ NOTION_DATABASE_ID }}` → Step 4.6 で取得した 32 文字に置換
- **ダブルクオートのエスケープ（`\"`）は消さないこと**（消すと JSON が壊れる）

### 5.3 ⚠️ よくある間違い

**`NOTION_API_KEY` という env 名は使わないこと。**

公式 MCP サーバ（`@notionhq/notion-mcp-server`）は **`OPENAPI_MCP_HEADERS`**（JSON 文字列）形式でしか認証を受け付けません。`NOTION_API_KEY` 単独で渡しても **401 Unauthorized** になります。

### 5.4 動作前の自己診断

設定が正しいか、Claude Code 起動前に確認できます：

```bash
python3 -c "
import json, urllib.request, urllib.error
d = json.load(open('.mcp.json'))
hdrs = d['mcpServers']['notion']['env']['OPENAPI_MCP_HEADERS']
token = json.loads(hdrs)['Authorization'].replace('Bearer ', '')
dbid = d['mcpServers']['notion']['env']['NOTION_DATABASE_ID']
print(f'Token: prefix={token[:4]}, length={len(token)}')
print(f'DBID: length={len(dbid)}, has_query_chars={\"?\" in dbid or \"&\" in dbid}')
for path, label in [(f'users/me', 'auth'), (f'databases/{dbid}', 'db access')]:
    req = urllib.request.Request(
        f'https://api.notion.com/v1/{path}',
        headers={'Authorization': f'Bearer {token}', 'Notion-Version': '2022-06-28'}
    )
    try:
        r = urllib.request.urlopen(req)
        print(f'{label}: SUCCESS {r.status}')
    except urllib.error.HTTPError as e:
        print(f'{label}: FAILED {e.code} {e.reason}')
"
```

出力すべて `SUCCESS` なら準備完了。

---

## Step 6: 最終納品物フォルダ作成

リポ外に最終納品物用フォルダを作ります。**Finder でブックマーク必須**。

```bash
mkdir -p ~/Documents/"AI Company Outputs"/<事業名>
open ~/Documents/"AI Company Outputs"/<事業名>
```

`open` コマンドで Finder が開くので、サイドバーにドラッグしてブックマーク化しておくと毎回のアクセスが楽。

> なぜリポ外か：worktree のサイクル（作成 → 作業 → マージ → 削除）に左右されず、全 worktree から同じ場所で最終物が見えるため。詳細は CLAUDE.md §6。

---

## Step 7: 動作確認（4テスト）

### 7.1 Claude Code セッション起動

ターミナルで（子会社リポフォルダ内で）：

```bash
claude
```

### 7.2 Test 1: 秘書の人格確認

```
こんにちは、自己紹介してください。
```

**期待:** **カズヨ** が名乗り、です・ます調＋簡潔で自己紹介。

> もし「Claude Code です」と返ってきたら CLAUDE.md §0.1 が読み込まれていない。リポの CLAUDE.md を確認。

### 7.3 Test 2: チケット起票＋Notion 同期

```
動作確認のためのテスト用チケットを1件起票してください。
要件: Notion 連携の動作確認、優先度: medium、担当: secretary。
起票後、Notion カンバンの todo 列にもカードを作成してください。
```

**期待:**
- `workspace/tickets/todo/T-YYYYMMDD-001_*.md` 作成
- Notion カンバンの todo 列にカード追加

### 7.4 Test 3: 状態遷移＋同期

```
先ほどのチケットを doing に動かしてください。
```

**期待:** ファイルが `doing/` に移動 + Notion カードも doing 列に移動。

### 7.5 Test 4: ルーティング＋納品

```
新規依頼です。来月の広告予算を試算してほしいです。
月商目標は100万円、想定 ROAS は3倍とします。
適切な担当に振ってチケット起票し、納品まで進めてください。
```

**期待:**
- カズヨが「経理（ハジメ）に振ります」と応答
- 新規チケット作成（`assignee: accounting`）
- 経理が試算し、`~/Documents/AI Company Outputs/<事業名>/<ticket_id>/` に納品物配置
- チケットが done に
- Notion カードも done に

すべて通れば運用開始可能です。

---

## トラブルシューティング

| 症状 | 原因と対処 |
|------|----------|
| `401 unauthorized: API token is invalid` | `.mcp.json` の env 名が `OPENAPI_MCP_HEADERS` になっているか確認（NOTION_API_KEY 単独は NG）。Step 5.4 の診断スクリプトで切り分け |
| `Database not found` / `object_not_found` | Database ID の桁数（32文字）と URL クエリパラメータ混入を確認。Step 5.4 の診断 |
| Notion カード作成は成功するが Status が空欄 | Notion 側 Status プロパティの値が `todo/doing/waiting/done`（小文字）で完全一致しているか |
| ファイル作ったはずなのに Finder で見えない | worktree（`<repo>/.claude/worktrees/<name>/`）の中にある可能性。`git worktree list` で確認 |
| 秘書が「Claude Code です」と名乗る | CLAUDE.md §0.1 が抜けている／プレースホルダー未置換でセッション初期化失敗。手動で「あなたはこのリポの秘書カズヨです」と指示 |
| Integration がない／コネクト追加できない | my-integrations で Internal Integration を作成。Public/OAuth 型は別仕様 |
| gh auth で失敗 | `gh auth status` で確認、必要なら `gh auth login`（HTTPS → ブラウザ認証） |

---

## 完成のチェックリスト

セットアップ完了の判定に使ってください。

### リポ側
- [ ] GitHub Template から子会社リポを作成
- [ ] ローカルに clone 済み
- [ ] CLAUDE.md §1 のプレースホルダー全埋め
- [ ] `grep "{{ " CLAUDE.md` の結果が §7 と §3 の説明文のみ
- [ ] `.mcp.json` 作成、`OPENAPI_MCP_HEADERS` 形式で記述、`NOTION_DATABASE_ID` 埋め込み
- [ ] Step 5.4 の自己診断スクリプトが両方 SUCCESS

### Notion 側
- [ ] DB 作成、タイトル `<事業名> Tickets`
- [ ] 10プロパティ追加、Status の選択肢が正しい
- [ ] カンバンビュー（Group by Status）
- [ ] Internal Integration 作成、DB にコネクト追加済み

### ローカル環境
- [ ] `~/Documents/AI Company Outputs/<事業名>/` 作成、Finder ブックマーク済み

### 動作確認
- [ ] Test 1（秘書人格）合格
- [ ] Test 2（チケット起票＋Notion 同期）合格
- [ ] Test 3（状態遷移）合格
- [ ] Test 4（ルーティング＋納品）合格

すべてチェックが付けば、事業の本格運用に入れます。

---

## 参照

- [README.md](../README.md) — 概要・日々の使い方
- [CLAUDE.md](../CLAUDE.md) — 会社の憲法
- [notion-setup-guide.md](notion-setup-guide.md) — Notion セットアップ単独詳細
- [notion-board-schema.md](notion-board-schema.md) — DB スキーマ正式仕様
- [mcp-setup-guide.md](mcp-setup-guide.md) — Notion 以外の MCP 追加方法
- [template-repository-setup.md](template-repository-setup.md) — 親テンプレ自体の管理（オーナー向け）
