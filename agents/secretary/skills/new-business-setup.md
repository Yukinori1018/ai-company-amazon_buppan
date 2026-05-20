# スキル：新事業セットアップ

社長が「新しい事業を作りたい」「子会社を立ち上げたい」「新規ビジネスを始めたい」と言ったとき、このスキルを発動して新事業リポジトリの生成を補助します。

## 発動トリガー（自然言語）

以下のような表現が出たらこのスキルを参照：

- 「新しい事業を作りたい」「新規事業を立ち上げたい」
- 「子会社を作る」「新しい会社を始める」
- 「Amazon物販を始めたい」「○○事業を始めたい」
- 「テスト事業を作って動作確認したい」
- `/new-business` スラッシュコマンドが打たれたとき（=明示的発動）

## 全体の流れ

```
社長が新事業の意向を表明
   ↓
カズヨ：チケット起票（todo/）
   ↓
カズヨ：要件を6項目ヒアリング（or プリセット確認）
   ↓
カズヨ：計画表示 → 社長承認（y/N）
   ↓
スクリプト実行（Step A〜G）
   ↓
カズヨ：完了報告 + 動作確認手順を案内
   ↓
チケット done/
```

## ステップ詳細

### ステップ1: チケット起票

[ticket-management.md](ticket-management.md) のルールに従い、`workspace/tickets/todo/` にチケットを起票します。タイトル例：「新事業セットアップ：<事業名>」。

### ステップ2: 引数の確定

3つのパターンがあります。

**パターン A: プリセット使用（最速）**

- 社長が「テスト事業を作って」→ `test` プリセット
- 社長が「Amazon物販を始めて」→ `amazon` プリセット

実行コマンド：

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

または `amazon` プリセット：

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

**パターン B: 対話モード（カスタム事業）**

社長に以下を**1問ずつ**ヒアリングします（一度に全部聞かない）：

1. GitHub リポ名（半角英数とハイフン）
2. 事業名（CLAUDE.md §1 に展開）
3. ミッション
4. 最重要KPI
5. 主力商品/サービス
6. 想定顧客
7. リポ公開設定（Private / Public）

**パターン C: 部分プリセット**

社長が「Amazon物販事業の続きを今やりたい、ただし月商目標は1000万に変更」のように、プリセットの一部を上書きしたい場合。該当項目だけ確認して、残りはプリセットから補完。

### ステップ3: 事前確認（承認必須項目）

新事業生成は §4.1「外部発信／金銭が動く／第三者連絡」のいずれにも該当しないが、GitHub リポ作成・Notion DB 作成という**外部リソース生成**を伴うため、**実行前に必ず社長承認**を取ります。

確認時の出力フォーマット：

```
以下で生成します:
  repo:       <repo名>
  事業名:     <事業名>
  ミッション: <ミッション>
  KPI:        <KPI>
  商品:       <商品>
  顧客:       <顧客>
  公開:       Private（または Public）

事前チェック:
  ✅ ~/.config/<テンプレ名>/config.env 読み込み可
  ✅ Notion 親ページに Integration が Connect 済み（社長が確認）
  ✅ gh auth OK

実行してよろしいですか？（y/N）
```

社長が `y` 以外を返した場合は `waiting/` に出して保留。

### ステップ4: スクリプト実行と実況

スクリプトは Step A〜G を順に進めます：

| Step | 内容 | 失敗時の典型原因 |
|------|------|----------------|
| A | GitHub リポ作成 | gh 認証切れ、リポ名重複 |
| B | ローカル clone | ディスク容量、既存ディレクトリ |
| C | プレースホルダー置換 | sed エスケープ問題（事業名に特殊文字） |
| D | Notion DB 作成 | 401（Integration の Connect 漏れ） |
| E | .mcp.json 生成 | テンプレ `.mcp.json.example` 不在 |
| F | 最終納品物フォルダ作成 | パーミッション |
| G | 初回 commit & push | リモート設定 |

各 Step の進捗を逐次社長に共有してください。失敗時は Step を特定し、原因を切り分けて報告。

### ステップ5: 完了報告

成功時の報告フォーマット：

```
✅ <事業名> セットアップ完了

生成物:
- GitHub: https://github.com/Yukinori1018/<repo>
- ローカル: ~/Claude Code/<repo>/
- Notion DB: <DB の URL or ID>
- 最終納品物フォルダ: ~/Documents/AI Company Outputs/<事業名>/

次のアクション（社長手動）:
  cd ~/"Claude Code/<repo>" && claude
で新セッションを起動し、
  「自己紹介してください」
  「テスト用チケットを起票してください」
で動作確認をお願いします。
```

### ステップ6: チケット done

最後に元チケットを `done/` に移動し、Notion カンバンも同期（[notion-ticket-sync.md](notion-ticket-sync.md) 参照）。

## 失敗時の対応

スクリプトが Step の途中で死んだ場合：

1. チケットを `waiting/` に移動
2. エラーログを社長に共有
3. 復旧手順を提案（典型例は [docs/owner-playbook.md](../../../docs/owner-playbook.md) のトラブルシューティング早見表参照）

特に **Notion 401 エラー**は Connect 漏れが原因の8割を占めます。社長に Integration の Connect 状態を確認してもらってください。

## 関連

- スクリプト実体: [scripts/create-subsidiary.sh](../../../scripts/create-subsidiary.sh)
- スラッシュコマンド: [.claude/commands/new-business.md](../../../.claude/commands/new-business.md)
- 社長向けプレイブック: [docs/owner-playbook.md](../../../docs/owner-playbook.md)
- 手動セットアップ（フォールバック）: [docs/subsidiary-onboarding.md](../../../docs/subsidiary-onboarding.md)
