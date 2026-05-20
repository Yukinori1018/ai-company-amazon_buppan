# 社長の手動運用メモ（プレイブック）

このファイルは**社長が手で実行する必要があるタスク**のみを集めたチートシートです。スクリプトや秘書カズヨが自動でやる部分は省いてあります。「何をどこまで自分でやるか」が一目で分かるように作っています。

迷ったら、まずこのファイルを開いてください。

---

## 全体像：2つのレイヤー

| レイヤー | 内容 | 発生頻度 |
|---------|------|---------|
| **A. テンプレ自体のフォーク** | GitHub 上で `ai-company-template` から新しい「工場」を作る | ほぼ一度きり（テスト時・ホールディング分割時のみ） |
| **B. テンプレから事業を生む** | 工場から1つの事業リポを量産する | 毎回 |

レイヤー B はスクリプトと `/new-business` コマンドでほぼ全自動。社長の手動タスクは下記の通り。

---

## レイヤー A: テンプレ自体をフォークするときの手動タスク

> 通常は不要。テストや新しいホールディング設立のときだけ。

### A-1. GitHub UI でテンプレからフォーク

1. <https://github.com/Yukinori1018/ai-company-template> を開く
2. 右上 **Use this template → Create a new repository**
3. リポ名を入力（例: `ai-company-template-test2`）→ **Private** 推奨 → **Create repository**

### A-2. ローカルにクローン

```bash
cd ~/"Claude Code"
gh repo clone Yukinori1018/<新リポ名>
```

### A-3. config.env を新テンプレ用に用意

スクリプトは `git remote get-url origin` から自動で `~/.config/<新テンプレ名>/config.env` を見に行きます。3パターン：

**パターン 1: 既存の Notion 設定を流用（推奨・楽）**

```bash
mkdir -p ~/.config/<新テンプレ名>
ln -s ~/.config/ai-company-template/config.env ~/.config/<新テンプレ名>/config.env
```

**パターン 2: 別の Notion 親ページで運用したい場合**

```bash
mkdir -p ~/.config/<新テンプレ名>
read -p "NOTION_PARENT_PAGE_ID を貼り付け（32文字、ハイフン無し）: " NOTION_PARENT_PAGE_ID
read -s -p "NOTION_API_KEY を貼り付け（表示されません）: " NOTION_API_KEY && echo
cat > ~/.config/<新テンプレ名>/config.env <<EOF
NOTION_API_KEY=$NOTION_API_KEY
NOTION_PARENT_PAGE_ID=$NOTION_PARENT_PAGE_ID
GITHUB_OWNER=Yukinori1018
EOF
chmod 600 ~/.config/<新テンプレ名>/config.env
unset NOTION_API_KEY NOTION_PARENT_PAGE_ID
```

**パターン 3: 親テンプレからの改善を取り込みたい場合**

新テンプレが古いコミットからフォークされている場合、最新の親テンプレの変更（例: `/new-business` slash command、スクリプト汎用化）が含まれません。取り込み手順：

```bash
cd ~/"Claude Code/<新テンプレ名>"
git remote add upstream https://github.com/Yukinori1018/ai-company-template.git
git fetch upstream
git merge upstream/main  # コンフリクトが出たら都度解決
git push origin main
```

### A-4. Claude Code で開く

```bash
cd ~/"Claude Code/<新テンプレ名>" && claude
```

→ 新セッションで「自己紹介してください」と打ち、秘書カズヨが立ち上がれば準備完了。

---

## レイヤー B: テンプレから事業を生むときの手動タスク

> 通常運用。社長がやる手動タスクはごくわずか。

### B-1. 事前確認（Notion 側）

- [ ] Notion に「**AI 会社**」親ページが存在する（または該当テンプレの親ページが存在する）
- [ ] Integration `ai-company-template-bot` が作成済み（<https://www.notion.so/my-integrations>）
- [ ] その Integration が親ページに **Connect** されている（ページ右上 … → Connections）
- [ ] `~/.config/<テンプレ名>/config.env` の値が本物（前回のセッションで設定済みなら OK）

確認コマンド：

```bash
TEMPLATE_NAME=$(basename "$(pwd)")
source ~/.config/${TEMPLATE_NAME}/config.env
echo "PAGE: ${NOTION_PARENT_PAGE_ID:0:4}...${NOTION_PARENT_PAGE_ID: -4} (${#NOTION_PARENT_PAGE_ID}文字)"
echo "KEY:  ${NOTION_API_KEY:0:7}...${NOTION_API_KEY: -4} (${#NOTION_API_KEY}文字)"
```

`0000...0000` や `ntn_DRY...LDER` でなければ OK。

### B-2. Claude Code を起動（既に起動済みならスキップ）

```bash
cd ~/"Claude Code/<テンプレ名>" && claude
```

### B-3. スラッシュコマンドを打つ（**社長の入力はこれだけ**）

| 打つもの | 動作 |
|---------|------|
| `/new-business test` | テスト事業を即生成（17文字） |
| `/new-business amazon` | Amazon物販事業を即生成（19文字） |
| `/new-business` | 対話モード。6項目を1問ずつ聞かれる |

確認プロンプト `y/N` に `y` を返すと、スクリプトが Step A〜G を自動進行します（GitHub リポ作成、ローカル clone、プレースホルダー置換、Notion DB 作成、`.mcp.json` 生成、初回コミット & push）。

### B-4. 生成後の動作確認

生成完了後、新リポで Claude Code を起動：

```bash
cd ~/"Claude Code/<新事業リポ名>" && claude
```

以下を順に打って確認：

1. 「自己紹介してください」→ 秘書カズヨが名乗ればOK
2. 「テスト用チケットを起票してください」→ `workspace/tickets/todo/` にファイル + Notion カンバンに "todo" カードが出現
3. 「そのチケットを doing に進めてください」→ ファイル移動 + Notion カラム更新
4. 「外部にメール送信したい」→ §4.1 該当として `waiting/` に出して承認を求めればOK

---

## トラブルシューティング早見表

| 症状 | 原因 | 対処 |
|------|------|------|
| `/new-business` が出てこない | `.claude/commands/new-business.md` が無い | 親テンプレから merge して取り込む（A-3 パターン 3） |
| `config.env が空` でスクリプト終了 | テンプレ名と config 名が不一致 | A-3 を実行 |
| Notion DB 作成で `401 unauthorized` | Integration が親ページに Connect されていない | B-1 の Notion 側確認をやり直す |
| `gh: command not found` | gh CLI 未インストール | `brew install gh && gh auth login` |
| `[y/N]` プロンプトで詰まる | Claude のサブシェル経由 | `/new-business` 経由なら `yes y \|` パイプ込みで自動回避済み |

---

## 参照

- [CLAUDE.md](../CLAUDE.md) — 会社全体ルール
- [scripts/README.md](../scripts/README.md) — スクリプト詳細仕様
- [docs/subsidiary-onboarding.md](subsidiary-onboarding.md) — 手動セットアップの完全ガイド（フォールバック用）
- [docs/notion-setup-guide.md](notion-setup-guide.md) — Notion 側の準備手順
- [.claude/commands/new-business.md](../.claude/commands/new-business.md) — スラッシュコマンド定義
