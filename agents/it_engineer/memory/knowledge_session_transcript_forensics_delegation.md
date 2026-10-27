# セッション履歴で「秘書の振る舞いの変化」を調べる手順（T-20261026-002・2026-10-26）

## 結論（この調査で分かったこと）
- 10/19 午後から社長の会話は「フォルダなし」で始まっていた（23本中22本）。この形では CLAUDE.md が自動で読まれず、`.claude/agents/` の担当（経理・法務など）も Agent の一覧に出ない。Agent 発注は 100回あたり 3.9 → 0.4
- **本リポの Claude Code フック9本は 8/21 以降、一度も正常に動いていない。** `settings.json` の `$CLAUDE_PROJECT_DIR` が引用符なしで、パスの空白（`Claude Code`）で切れて exit 127。non-blocking error なので誰も気づかない。委譲チェック・Notion 同期リマインド・Stop の社長タスク同期・order-gate-guard・source-terms-guard（Claude 側）すべて同じ。git の pre-commit（`.githooks`）は別経路
- 「仕組みにした」と書く前に、フックが実際に文脈を差し込んだ記録（attachment type=`hook_additional_context`）があるかを見る。エラーは type=`hook_non_blocking_error` に `stderr` 付きで残る

## 再利用できる手順
1. 履歴は `~/.claude/projects/<cwd をハイフン化>/*.jsonl`。**本リポのフォルダだけを見ない。** フォルダなしの会話は `-Users-yukinori-Library-Application-Support-Claude-scratch-workspaces-*` に入る。途中でフォルダに移した会話は移動先にも複製が残る（開始時刻＋ツール数で重複を除く）
2. 始まり方の判定：最初の user メッセージに `without choosing a project folder` があればフォルダなし、`<scheduled-task` があれば予約タスク
3. 担当が選べたかは attachment `agent_listing_delta` の `addedTypes` に `accounting` 等が現れた時点で分かる
4. サブエージェントの中身は `<session>/subagents/` にあり、トップの jsonl は `isSidechain` で除く
5. 比率は「1日の回数」ではなく「100ツール呼び出しあたり」「1ターンあたり」で見る。社長の会話量が減ると回数は勝手に減る
6. 対照を必ず置く：同じ期間・同じ CLAUDE.md で、始まる場所だけが違う予約タスク（夜間）は発注を続けていた → 場所が効いている
7. フック不調の再現：`CLAUDE_PROJECT_DIR="$PWD" /bin/sh -c '$CLAUDE_PROJECT_DIR/.claude/hooks/x.sh'`（127）と、引用符つき（0）を並べる

スクリプト：`workspace/output/agent_output/T-20261026-002/parse.py` `parse_all.py`（Git 対象外。消えたら上の手順で書き直せる規模）
