# ai-company-toolkit

Amazon物販事業 AI 会社の **社内運用ツールを束ねた Claude Code プラグイン**です。
秘書カズヨの日常運用（チケット駆動・KPI 管理・依頼ルーティング）を補助します。

> このプラグインは「Claude Code のプラグイン機能を実地で試す」ための検証物でもあります（チケット T-20260610-001）。

## 同梱物（プラグイン機能ツアー）

| 種類 | 名前 | 呼び出し | 役割 |
|---|---|---|---|
| コマンド | `ticket` | `/ai-company-toolkit:ticket <タイトル>` | 会社の雛形に沿って新規チケットを `workspace/tickets/todo/` に起票 |
| スキル | `kpi-check` | 自動（「KPI どう」等で起動）/ `/ai-company-toolkit:kpi-check` | 月商800万・利益率20%・SKU100 の現状スナップショット |
| フック | SessionStart | 自動 | 起動時に会社のミッション/KPI を 1 ブロック注入（`${CLAUDE_PLUGIN_ROOT}` 検証込み） |
| エージェント | `ticket-router` | `/agents` に `ai-company-toolkit:ticket-router` として出現 | 依頼を §5 ルーティング表で担当に割り振り、§4.1 承認要否を判定 |

## インストール方法（ローカル marketplace から）

このリポジトリ直下に marketplace 定義（`.claude-plugin/marketplace.json`）があります。

```
# 1) リポジトリをローカル marketplace として登録
/plugin marketplace add ./

# 2) プラグインをインストール
/plugin install ai-company-toolkit@ai-company

# 3) 変更を反映（開発中に編集した場合）
/reload-plugins
```

インストール後:

- `/ai-company-toolkit:ticket Keepa の料金体系を再調査` のようにコマンドを実行
- 新規セッション開始時に起動バナーが注入される
- 「KPI まとめて」と言えば `kpi-check` スキルが起動
- `/agents` に `ai-company-toolkit:ticket-router` が並ぶ

## ディレクトリ構成

```
plugins/ai-company-toolkit/
├── .claude-plugin/
│   └── plugin.json          # マニフェスト（name 必須・hooks パス指定）
├── commands/
│   └── ticket.md            # /ticket スラッシュコマンド
├── skills/
│   └── kpi-check/
│       └── SKILL.md         # KPI スナップショットスキル
├── agents/
│   └── ticket-router.md     # 依頼ルーティング用サブエージェント
├── hooks/
│   └── hooks.json           # SessionStart フック定義
├── scripts/
│   └── greeting.sh          # フックが呼ぶ起動バナースクリプト
└── README.md
```

## 子会社展開（§7 との接続）

CLAUDE.md §7 の「子会社リポジトリ生成」時、各子会社は本 marketplace を登録して
`/plugin install ai-company-toolkit@ai-company` するだけで、会社共通の道具一式を導入できます。
ファイルをコピーして回るより、プラグイン更新が全子会社に伝播しやすくなります。

## 既存の `.claude/` との関係

- 親リポの `.claude/commands/`（`/handover` `/resume` `/new-business`）と
  `.claude/hooks/session-start.sh`（チケットリマインダー）は**そのまま維持**。
- 本プラグインは**重複しない新規機能**（`/ticket` 起票・`kpi-check`・KPI バナー・`ticket-router`）のみを足しています。
