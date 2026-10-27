# フォルダなし会話にはリポのルールもフックも届かない／英語の問いは決まりが無いから出る

記録：2026-10-27 / T-20261026-002（タカシ・再調査）

## 事実（会話記録で数えた）
- 社長の会話は 10/20〜10/27 に25本中22本が「フォルダなし」（`~/.claude/projects/-Users-yukinori-Library-Application-Support-Claude-scratch-workspaces-*`）。
- フォルダなしの会話では、リポの CLAUDE.md・.claude/settings.json のフック・リポの memory が**どれも読まれない**。途中で change_directory でリポへ移っても同じ（22本で CLAUDE.md の読み込み0件・フック記録0件）。
- 一方 **~/.claude/settings.json のフックはフォルダなしでも発火する**（セッション記録フックのログ `~/.config/claude-session-sheets/hook.log` に scratch の会話 ID が出る）。→ 届ける経路はユーザー全体のフック。
- フック exit 127（引用符なし `$CLAUDE_PROJECT_DIR`）は 10/27 08:28〜08:46 の間に直った（commit a5a15360）。worktree 3本には古い settings.json が残っている。
- 英語は「日本語で書く」という決まりがどこにも無いことが根。CLAUDE.md が届くリポの夜間タスクでも本文の39%が英語だった。

## 数え方（再利用）
- スクリプト：`workspace/output/agent_output/T-20261026-002/parse_v2.py`（日別・場所別・対話/予約別、英語抽出）。
- **分岐した会話は同じ tool_use id を持つ**（aa952878/ac1054a4 など）。数えるときは id で重複を除く。除かないと発注回数が水増しされる。
- 「夜間の予約タスク」と「社長との会話」を必ず分ける。10/26 の 01 は混ぜたため「10/19〜25 も毎日2〜8回振っていた」と誤って読めた。社長の会話だけだと7日で1回。
- フックが動いたかは、会話記録の attachment `hook_non_blocking_error`（exitCode 127）と `hook_additional_context` を時刻で数える。

## 作ったもの（登録は社長承認後に秘書が `install_language_and_bridge_hooks.py --apply`）
- `.claude/hooks/japanese-only-guard.py`：PreToolUse で社長に見える道具（wrap_up・AskUserQuestion・update_plan・start_session 等）の英語欄を deny。Stop で最後の本文が英語なら1回だけ block。実データ185呼び出しで再生し、誤検知0。
- `.claude/hooks/global-buppan-bridge.py`：~/.claude/settings.json 用。門は「transcript_path が scratch-workspaces」「物販の語 or cwd がリポ（一度当たれば覚える）」。リポのフックを subprocess で呼ぶだけ。

## 判断の線
- **設定ファイル（settings.json・~/.claude/settings.json）と CLAUDE.md の変更は、担当への発注文だけでは実行しない。** 道具・試験・差分・前後の文面まで作り、登録は社長承認を取った秘書がやる。報告で「作った」と「効いている」を分ける。
- グローバルフックは「他のプロジェクトで即終了する門」を試験に入れてから出す（他事業リポ・物販と関係ない scratch で無音）。
