# scripts/

ai-company-template 用の運用スクリプト置き場。

## create-subsidiary.sh — 子会社ワンコマンド生成

`docs/subsidiary-onboarding.md` の 7 ステップ（GitHub テンプレ複製 → clone → プレースホルダー置換 → Notion DB 作成 → `.mcp.json` 生成 → 最終納品物フォルダ作成 → 動作確認）のうち **Step 1〜6 を自動化**します。Step 7（動作確認の 4 テスト）は人間がやる前提でチェックリストを出力します。

### できること

| 項目 | 自動 | 備考 |
|------|:----:|------|
| GitHub リポジトリ作成（テンプレ複製） | ✓ | `gh repo create --template` |
| ローカルへ clone（`~/Claude Code/<repo>`） | ✓ | 既存ディレクトリがあれば中断 |
| プレースホルダー一括置換 | ✓ | `*.md` / `*.json*`（`docs/reference/`, `.git/` 除外） |
| Notion カンバン DB 作成 | ✓ | `docs/notion-board-schema.md` 準拠 |
| `.mcp.json` 生成 + token/db-id 埋め込み | ✓ | gitignore 対象なので push されない |
| `~/Documents/AI Company Outputs/<事業名>/` 作成 | ✓ | |
| 初期コミット & push | ✓ | `.mcp.json` 抜きで push |
| 動作確認 4 テスト | — | チェックリストを表示するのみ |

---

## 1. 事前準備

### 1.1 必要なコマンド

```bash
brew install gh jq
gh auth login           # HTTPS → ブラウザ認証
```

### 1.2 Notion 側の準備

#### A. 「AI 会社」親ページを作る

1. Notion ワークスペース内に **新規ページ**を作成（タイトル例: `AI 会社`）
2. このページの **URL から Page ID を抽出**:
   - URL 例: `https://www.notion.so/myws/AI-Company-1234567890abcdef1234567890abcdef?pvs=4`
   - **末尾 32 文字**（タイトル直後の `-` 以降、`?` より前）が ID
   - **ハイフンを除いた 32 文字**を `NOTION_PARENT_PAGE_ID` に貼る
3. このページ配下に、生成される全子会社の Tickets DB がぶら下がる

#### B. Integration を作って親ページに Connect

1. <https://www.notion.so/my-integrations> → **+ New integration**
2. Name: `ai-company-template-bot`（任意）/ Type: **Internal**
3. 作成後、**Internal Integration Token**（`ntn_...` または `secret_...`）をコピー
4. A で作った親ページを開き、右上 **... → Connections → 上記 Integration を追加**
   - これを忘れると Step D（DB 作成）が permission エラーになる

### 1.3 `config.env` を置く

```bash
mkdir -p ~/.config/ai-company-template
cp scripts/config.env.example ~/.config/ai-company-template/config.env
chmod 600 ~/.config/ai-company-template/config.env
$EDITOR ~/.config/ai-company-template/config.env
```

中身：

```bash
NOTION_API_KEY=ntn_xxxxxxxxxxxxxxxxxxxxxx
NOTION_PARENT_PAGE_ID=1234567890abcdef1234567890abcdef
GITHUB_OWNER=                                # 空なら gh から自動取得
```

> このファイルは Git にも iCloud にも置かない。`~/.config/` は同期対象外であることが多い。

---

## 2. 使い方

### 2.1 引数で全部指定（ワンライナー）

```bash
./scripts/create-subsidiary.sh \
  --repo amazon-merchandise \
  --business-name "Amazon物販事業" \
  --mission "国内未進出のニッチ良品を発掘・販売し、月商800万を達成する" \
  --kpi "月商800万円、利益率20%以上、SKU数100" \
  --products "アジア圏のセレクト雑貨" \
  --customers "30〜45歳女性" \
  --private
```

### 2.2 対話モード

```bash
./scripts/create-subsidiary.sh
```

足りない引数は順番に聞かれます。

### 2.3 dry-run（副作用なしで計画を確認）

```bash
./scripts/create-subsidiary.sh --dry-run \
  --repo amazon-merchandise \
  --business-name "Amazon物販事業" \
  --mission "..." --kpi "..." --products "..." --customers "..."
```

`gh repo create` や `git push`、Notion API 呼び出しは **全部スキップ**して、何をする予定かだけを表示します。

### 2.4 ヘルプ

```bash
./scripts/create-subsidiary.sh --help
```

---

## 3. やっていること（内部）

| Step | 内容 |
|------|------|
| A | `gh repo create $OWNER/$REPO --template Yukinori1018/ai-company-template --private` |
| B | `~/Claude Code/$REPO/` に clone |
| C | `find . -type f \( -name "*.md" -o -name "*.json*" \)`（`.git`, `docs/reference` 除外）で対象を列挙し、`{{ 事業名 }}` `{{ ミッション }}` `{{ 最重要KPI }}` `{{ 主力商品/サービス }}` `{{ 想定顧客 }}` を `sed -i ''` で置換。`{{ チケットタイトル }}` は runtime プレースホルダーなのでスキップ。`{{ NOTION_API_KEY }}` `{{ NOTION_DATABASE_ID }}` は Step E でやるのでスキップ |
| D | `POST https://api.notion.com/v1/databases` に `scripts/notion-db-schema.json` の properties を送って DB 作成。レスポンスから `id` を抽出 |
| E | `.mcp.json.example` を `.mcp.json` にコピーし、Notion token / DB ID を埋め込み（`chmod 600`） |
| F | `~/Documents/AI Company Outputs/<事業名>/` を `mkdir -p` |
| G | `.mcp.json` を含めずに `git add -A && git commit && git push`（gitignore のおかげで token は push されない） |
| H | ターミナルに動作確認チェックリストと Notion カンバン URL を表示 |

---

## 4. トラブルシューティング

### `gh: command not found`

```bash
brew install gh
gh auth login
```

### `gh auth status` で `not logged in`

```bash
gh auth login
# → HTTPS → Login with a web browser
```

### Notion API が `unauthorized` / `restricted`

親ページに Integration を Connect し忘れている可能性大。

1. 親ページを Notion で開く
2. 右上 `...` → `Connections` → 1.2-B で作った Integration を追加

その上で再実行（Step A/B はもう完了しているので、別 repo 名でやり直すか、手動で Step D 以降だけ走らせる）。

### Notion API が `object_not_found`

`NOTION_PARENT_PAGE_ID` のコピペミス。URL 末尾 32 文字（ハイフン除去）を再確認。

### `clone 先が既に存在`

```bash
rm -rf ~/Claude\ Code/<repo>
# または別の --repo 名で再実行
```

### macOS の bash が古い（3.2）

このスクリプトは bash 3.2 互換で書いています。`brew install bash` などは不要。

### 途中で止まったら？

各 Step は冪等ではありません。失敗位置に応じて手動リカバリ：

| 失敗 Step | リカバリ |
|----------|---------|
| A 失敗 | GitHub 側に repo ができていないので再実行 |
| B 失敗 | `gh repo delete $OWNER/$REPO --yes` してから再実行 |
| C 失敗 | clone 先で `git restore .` してから手動置換 or 再 clone |
| D 失敗 | Notion 側で DB が中途半端にできているかチェック。あれば削除して再実行 |
| E〜G | clone 先で続きを手動実行（`docs/subsidiary-onboarding.md` 参照） |

---

## 5. 関連ドキュメント

- 手動版手順（フォールバック）: [../docs/subsidiary-onboarding.md](../docs/subsidiary-onboarding.md)
- Notion DB スキーマ仕様: [../docs/notion-board-schema.md](../docs/notion-board-schema.md)
- Notion セットアップ詳細: [../docs/notion-setup-guide.md](../docs/notion-setup-guide.md)
- プレースホルダー一覧: [../CLAUDE.md](../CLAUDE.md) §7
