---
ticket_id: T-20260821-002
title: サブエージェント8体を .claude/agents/ に実体登録＋委譲チェックフック
status: done
assignee: it_engineer
priority: high
created_at: 2026-08-21
updated_at: 2026-08-21
requires_approval: false
labels: [tooling, hooks]
parent_ticket: T-20260821-001
next_check_at: 2026-08-22
---

## 要件

「担当に振る」を1コールで実行できる状態にし、振らなかったら気づける仕組みを入れる。

## タスク分解

- [x] `.claude/agents/<role>.md` を8体作成（secretary はメインセッション自身なので不要）
- [x] 各定義に SUBAGENT_PROTOCOL の要点（成果物の保存先・memory記録義務）を埋め込む
- [x] UserPromptSubmit フックで「担当宣言」をリマインド（`delegation-check.sh`）
- [x] 動作確認
- [x] （追加1）`session-start.sh` の空白入りパス単語分割バグを修正し、実走で29件検出を確認
- [x] （追加2）チケット frontmatter キー契約の機械検証を PostToolUse フックに相乗り
- [x] （追加3）`ticket_id` 一意性検証を追加＋既存90枚の重複を独立経路で全数確認

## 現在地

完了。カズヨの確認待ち（done への移動は秘書の責務のため doing に留置）。

## ログ

- 2026-08-21 doing 起票
- 2026-08-21 タカシ着手。公式仕様（code.claude.com/docs/en/sub-agents.md）を確認のうえ `.claude/agents/` に8体を作成
- 2026-08-21 `delegation-check.sh`（UserPromptSubmit）を新規作成し settings.json へ登録（バックアップ取得済み）
- 2026-08-21 カズヨより追加指示2件を受領（session-start.sh のバグ／frontmatter 検証）。同一チケット内で対応
- 2026-08-21 session-start.sh の単語分割バグを修正。実走で29件検出＝独立集計と一致することまで確認
- 2026-08-21 ticket-notion-sync-reminder.sh に frontmatter 契約検証を追加。全85枚に通し `related:` 誤用12枚を発見
- 2026-08-21 動作確認完了。完了報告を追記

## 成果物

すべてリポ内（Git 追跡対象）。設定ファイルの直接更新が本チケットの成果のため deliverables への複製は行わない。

**新規（サブエージェント定義8体）**
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/researcher.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/planner.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/simulator.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/accounting.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/legal.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/general-affairs.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/content-creator.md`
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/agents/it-engineer.md`

**新規（フック）**
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/hooks/delegation-check.sh`

**修正**
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/settings.json`（UserPromptSubmit 登録。バックアップ `.claude/settings.json.bak.20260821-121217`）
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/hooks/session-start.sh`（空白入りパスの単語分割バグ修正）
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/.claude/hooks/ticket-notion-sync-reminder.sh`（frontmatter 契約検証を追加）

**メモリ**
- `/Users/yukinori/Claude Code/ai-company-amazon_buppan/agents/it_engineer/memory/knowledge_claude_code_subagents_and_hooks.md`

## 完了報告

カズヨさん、タカシです。3項目＋追加2項目、すべて完了しました。

**1. サブエージェント8体を実体登録**
公式仕様（code.claude.com/docs/en/sub-agents.md）を確認してから書きました。frontmatter 必須キーは `name` と `description` の2つ、`tools` はカンマ区切り文字列、省略すると MCP 込みで全ツール継承です。
- **`name` は「小文字＋ハイフン」が公式記法**のため、複数語のロールは `general-affairs` / `content-creator` / `it-engineer` としました。`agents/general_affairs/` などのディレクトリ名（snake_case）とは別物です。本文中の参照パスは snake_case のままなので実害はありません。
- マリエ（Notion）とタカシ（ブラウザ検証等）は **`tools` を意図的に省略**しています。このリポの MCP ツール名はセッションごとに変わる UUID を含み、許可リストに固定名で書けないためです。
- 全8体の本文に、①該当 `agents/<role>/agent.md` と `SUBAGENT_PROTOCOL.md` を最初に読む、②最終納品物は `workspace/output/deliverables/<ticket_id>/` に直納してその場で commit、③完了前に `memory/` へ1ファイル以上必ず記録（省略したら未完了扱い）、④`done/` へ動かさず doing 留置、⑤社長と直接やり取りしない、⑥§4.1 は自分で踏まず差し戻し ―― を明記しました。

**2. 委譲チェックフック `delegation-check.sh`（UserPromptSubmit）**
依頼文から担当を推定し、**担当名を名指しして** Agent ツールでの実発注を促します。ノイズ抑制は3層：短文・スラッシュコマンド・相槌は無音／担当マッチ時のみ発火／状態ファイルでクールダウン（担当特定8分・汎用20分、ただし新しい担当が現れたら即再点火）。状態は `$TMPDIR` にセッション ID で置くのでリポは汚しません。常に exit 0 でブロックしません。

**3. 追加1: `session-start.sh` は確かに一度も動いていませんでした**
ご指摘のとおりです。配列化して修正し、**実走で29件のリマインダーが出ることを確認**しました。独立に awk で数えた実数も29件で一致します。
- 33件との差4件は、`T-20260821-001〜004`（今日起票分）が `next_check_at: 2026-08-22` の**未来日**のためです。明日から出ます。
- **別件の残課題:** doing/waiting の**8枚に `next_check_at` 自体がありません**。この8枚は修正後も永遠にリマインドされません。マリエの棚卸し範囲だと思うので回します（T-20260520-012 / T-20260522-003 / T-20260522-005 / T-20260520-005 / T-20260520-006 / T-20260521-002 / T-20260705-003 / T-20260816-003）。

**4. 追加2: frontmatter 契約の機械検証**
独立フックは増やさず、既存の `ticket-notion-sync-reminder.sh`（PostToolUse）に相乗りさせました。`ticket_id` の有無と形式、`assignee` の有無と固定語彙10種、エイリアス誤用（`id`/`owner`/`assigned_to`/`related`/`next_check`/`due`）を警告します。ブロックしません。`_` 始まりのファイルは対象外です。
- **既存85枚に通した結果:** `ticket_id`・`assignee` の誤りはゼロでした（マリエの修復が効いています）。ただし **`related:`（正: `related_tickets:`）が12枚残存**しています。私が一括編集すると Notion 同期が大量に走るので手を出していません。マリエへ回してください。

**確認できたこと / できなかったこと（正直に）**
- 確認できた: 全 .sh の `bash -n`、settings.json の JSON 妥当性、delegation-check の11ケースの発火/抑制、frontmatter 検証の正常/異常/テンプレ除外、既存3フックの回帰（挙動不変）、**すべて空白入りの実パスで実走**。
- **確認できなかった: サブエージェント8体が実際にロードされるかの実測**。`claude --agent <name> -p` で試しましたが `401 OAuth access token has been revoked` で認証段階に阻まれ、存在しない名前でも同じ 401 になるため比較試験も成立しませんでした。だから公式記法（ハイフン）に寄せる判断を取っています。**次のセッション開始時に Agent ツールの選択肢へ8体が出ているかを目視確認してください。** 出ていなければ真っ先に疑うべきはハイフン/アンダースコアの名前解決です。

**メモリ記録:** `agents/it_engineer/memory/knowledge_claude_code_subagents_and_hooks.md`
サブエージェント仕様、空白入りパスの地雷と「`bash -n` が通ることは動く証明にならない」という教訓、フック実装の型、ノイズ抑制の設計、frontmatter＝機械が読む契約、の5点を残しました。


## 追補（2026-08-21）: ticket_id 一意性検証の追加

> done 移動後の追補です。カズヨさんの追加指示（重複がバリデータの穴を抜けて実害化）に対応しました。

カズヨさんのご指摘どおり、初版バリデータの穴でした。形式検証（`T-\d{8}-\d{3}`）を通っても、
同じ値が2枚あれば同期キーとして破綻します。**「値が妥当か」と「値が衝突していないか」は別の軸**で、
後者を見ていませんでした。

**実装**（`.claude/hooks/ticket-notion-sync-reminder.sh` / +53行・削除0行）
- チケット .md の Write/Edit 時に `workspace/tickets/` 全階層を1回走査し `ticket_id` の重複を検出
- **重複時は必ず全パスを列挙**（片方だけ出す実装は、事故を3ヶ月隠した `head -1` と同じ見落としを再生産するため）
- 今編集したチケットが該当する場合は「← 今編集したチケット」と明示
- 従来どおりブロックしない（exit 0）
- コスト: 90枚の全走査で **20ms**（frontmatter は先頭にあるため冒頭4096バイトのみ読む）。
  フック全体183msの大半は python 起動コストで、走査は誤差レベル

**独立経路での全数確認**（カズヨさんとは別の数え方）
`grep '^ticket_id:' | uniq -d` と同じ発想では同じ穴を踏むため、frontmatter ブロックの厳密パース
＋ `os.walk` 全階層走査 ＋ ファイル名 ID との突き合わせ、で数えました。

- 改番前: 90枚 / **重複2組**（`T-20260603-003`, `T-20260706-001`）→ カズヨさんの報告と一致。**3組目以降なし**
- 副次的に判明: `ticket_id` 欠落 **0枚**、ファイル名 ID と frontmatter ID の不一致 **0枚**
- マリエさん改番後に再走査: **90枚 / ユニーク90件 / 重複0組** ✅

**検証**: 実リポで警告消滅を確認／隔離環境で意図的な重複を作り確実に検知することを確認／
既存チェック（エイリアス誤用・語彙外・テンプレ除外・チケット以外は無音）の回帰も確認済み。
`workspace/tickets/` 配下のファイル本体には一切触れていません。
