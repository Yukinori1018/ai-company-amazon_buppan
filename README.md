# ai-company-template

ローカルフォルダで動く「AI 仮想会社」を構築するための**親テンプレート**。
GitHub Template repository 機能から複製し、事業ごとの**子会社**リポジトリを作る運用を想定しています。

> このREADMEは「自分（社長）が子会社を作るときに読み返すセルフガイド」として書かれています。

## 全体像

| 役割 | 担当 |
|------|------|
| 社長（あなた） | 意思決定・最終承認 |
| 秘書（カズヨ） | 唯一の窓口・司令塔 |
| 経理（ハジメ）／法務（ハルオ）／庶務（マリエ）／コンテンツ制作（ヒデアキ） | 専門サブエージェント |

社長が話すのは秘書だけ。秘書が4専門に振り、進捗を統合して報告します。

詳細な設計思想は [docs/reference/動画分析.md](docs/reference/動画分析.md) 参照。

---

## 子会社を作る手順

> **⚡ ワンコマンド版: `./scripts/create-subsidiary.sh`**（詳細は [scripts/README.md](scripts/README.md)）
>
> GitHub repo 作成 → clone → プレースホルダー置換 → Notion DB 作成 → `.mcp.json` 生成 → 最終納品物フォルダ作成 → 初回 push までを一括。事前準備（`gh`/`jq` インストールと `~/.config/ai-company-template/config.env` 作成）が必要。
>
> **📘 完全ガイド（手動版・トラブル時のフォールバック）: [docs/subsidiary-onboarding.md](docs/subsidiary-onboarding.md)**
>
> 詰まりポイント・トラブルシューティング・診断スクリプト付きの実機検証済み手順。**初めて子会社を作る／久しぶりに作る時／スクリプトで詰まった時はこちらを開きながら進めてください。**
>
> 以下は概略版（慣れている人向け）。

### Step 1: テンプレートから複製

GitHub のリポジトリページで **"Use this template" → "Create a new repository"** をクリック。
事業名でリポジトリ名をつける（例：`amazon-merchandise`）。

```bash
git clone git@github.com:<your-account>/<new-repo>.git
cd <new-repo>
```

### Step 2: プレースホルダーを埋める

[CLAUDE.md §7](CLAUDE.md) のチェックリスト（§7.1）を上から順に埋めます。

```bash
# 埋め残しを検出（README/CLAUDE/各種docs/.mcp.json.example を全部スキャン）
grep -rn "{{ " . \
  --include="*.md" --include="*.json*" \
  --exclude-dir=docs/reference --exclude-dir=.git
```

セットアップ時に埋めるもの（CLAUDE.md §7.1）：

- `{{ 事業名 }}` — 例：Amazon物販事業
- `{{ ミッション }}` — その事業の存在意義
- `{{ 最重要KPI }}` — 例：月商800万円
- `{{ 主力商品/サービス }}` — 何を扱うか
- `{{ 想定顧客 }}` — 誰のため
- `{{ NOTION_API_KEY }}` / `{{ NOTION_DATABASE_ID }}` — Step 3 で取得

> grep の結果に `{{ チケットタイトル }}` も出ますが、これは **runtime プレースホルダー**（チケット起票のたびに埋める）なのでセットアップ時の対応は不要です。詳細は CLAUDE.md §7.2。

エージェント名（カズヨ・ハジメ・ハルオ・マリエ・ヒデアキ）を事業に合わせて変えたい場合は、各 `agents/<role>/agent.md` を編集。

### Step 3: Notion カンバンをセットアップ

→ [docs/notion-setup-guide.md](docs/notion-setup-guide.md) の手順に従う。

ざっくり：Notion で DB を1つ作り、トークンを取得し、`.mcp.json.example` を `.mcp.json` にコピーして埋める。

### Step 4: 他の MCP を追加（必要なら）

Gmail・Slack・GitHub などの道具を秘書/サブエージェントに持たせたい場合は、`.mcp.json` にサーバを追加。
→ [docs/mcp-setup-guide.md](docs/mcp-setup-guide.md) 参照。

### Step 5: 最終納品物の格納先を準備

リポ外に最終納品物用フォルダを作っておきます（Finder でブックマーク推奨）：

```bash
mkdir -p ~/Documents/"AI Company Outputs"/{{ 事業名 }}
```

### Step 6: 初回起動と動作確認

Claude Code でこのリポジトリを開いて：

1. セッション開始時に `CLAUDE.md` が読み込まれることを確認（秘書「カズヨ」が起動）
2. 秘書に「テスト用チケットを1件起票して Notion にも反映して」と依頼
3. `workspace/tickets/todo/` にファイルが作られ、Notion カードも作られることを確認
4. 何か納品物のあるタスクを試して、`~/Documents/AI Company Outputs/{{ 事業名 }}/` に最終物が置かれることを確認

ここまで動けば運用開始可能です。

---

## 日々の使い方

### 1. 社長は秘書（カズヨ）にだけ話す

経理・法務・庶務・コンテンツ制作に直接話しかけないでください。秘書経由で振ります（その方が全体最適化されます）。

### 2. 進捗は2箇所で見える

| 見る場所 | 用途 |
|---------|------|
| Notion カンバン | スマホ・出先からの確認に最適 |
| [workspace/tickets/](workspace/tickets/) | リポジトリ内での詳細確認・履歴 |

### 3. 確認するのは最終納品物だけ

**`~/Documents/AI Company Outputs/{{ 事業名 }}/`** に置かれたものを見ます。Finder でこのフォルダをブックマークしておくのがおすすめ。途中経過（リポ内の `workspace/output/agent_output/`）は問題発生時の監査用。

### 4. 承認が必要な依頼は `waiting/` に来る

外部発信・課金・契約・削除など [CLAUDE.md §4.1](CLAUDE.md) のリスク項目は、必ず `tickets/waiting/` に出されます。チェックして「承認」または「差し戻し」を秘書に伝えれば、その通り動きます。

### 5. 育てる場所は memory/

各エージェントの `agents/<role>/memory/` に、好み・判断理由・失敗が蓄積されます。3ヶ月運用すれば、あなたの分身のように先回りできるようになります。

---

## フォルダ構成（要点）

```
.
├── CLAUDE.md                          # 会社の憲法（自動読込）
├── README.md                          # このファイル
├── .mcp.json.example                  # Notion MCP スタブ（コピーして使う）
├── agents/
│   ├── secretary/         (カズヨ)    # 唯一の窓口
│   ├── accounting/        (ハジメ)    # 経理
│   ├── legal/             (ハルオ)    # 法務
│   ├── general_affairs/   (マリエ)    # 庶務
│   └── content_creator/   (ヒデアキ)  # コンテンツ制作
├── workspace/
│   ├── tickets/{todo,doing,waiting,done}/   # カンバン（Notion同期）
│   └── output/agent_output/                 # 作業中の途中経過のみ（gitignore）
                                              # 最終納品物は ~/Documents/AI Company Outputs/{{ 事業名 }}/
│   ├── README.md                            # workspace 運用ハブ
│   └── SUBAGENT_PROTOCOL.md                 # サブ共通プロトコル
└── docs/
    ├── reference/動画分析.md          # 設計の出典
    ├── notion-board-schema.md         # Notion DB 仕様
    ├── notion-setup-guide.md          # Notion セットアップ手順
    └── mcp-setup-guide.md             # 任意MCP追加ガイド
```

---

## 参考

- 📘 **子会社セットアップ完全ガイド: [docs/subsidiary-onboarding.md](docs/subsidiary-onboarding.md)**（トラブルシューティング・診断スクリプト付き）
- 設計の出典: [docs/reference/動画分析.md](docs/reference/動画分析.md)
- 会社の憲法: [CLAUDE.md](CLAUDE.md)
- workspace 運用詳細: [workspace/README.md](workspace/README.md)
- 秘書のスキル: [agents/secretary/skills/](agents/secretary/skills/)
- Notion セットアップ単独詳細: [docs/notion-setup-guide.md](docs/notion-setup-guide.md)
- 他の MCP（Gmail 等）追加: [docs/mcp-setup-guide.md](docs/mcp-setup-guide.md)
- 親テンプレ自体の管理: [docs/template-repository-setup.md](docs/template-repository-setup.md)
