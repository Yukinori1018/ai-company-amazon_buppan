---
name: knowledge-global-hook-registration-check
description: ユーザー全体（~/.claude/settings.json）とリポにフックを登録したあと確かめたこと（T-20261026-002）。登録した command 文字列をそのまま、実際の入力の形で流す
metadata:
  type: knowledge
  ticket: T-20261026-002
---

## 登録後に確かめたこと（2026-10-27・社長承認「A で」）
1. `install_language_and_bridge_hooks.py --apply` → リポ2件・全体4件。控えは各 settings.json の隣に `.bak.<日時>`（リポ側は .gitignore 済み）。**2回目の --apply が「追加0件」**＝冪等。
2. 全体設定は「既存のイベントの配列が先頭そのまま残っているか」「hooks 以外のキーが同じか」を控えと比べた。json.dump で書き直すので体裁は変わるが中身は同じ。
3. `python3 -m json.tool` で両方壊れていないこと。
4. 動作確認は、settings.json から command 文字列を読み出し `/bin/sh -c` で実行（空白入りパスを踏むため。単体テストの直呼びでは踏まない＝過去の exit 127 事故の型）。入力は実物の形（session_id・transcript_path・cwd・hook_event_name・tool_name・tool_input）。
5. フォルダなし会話の判定は transcript_path に `scratch-workspaces` が入るかなので、試験用の記録ファイルは scratchpad の `scratch-workspaces-x/` に置けば再現できる。
6. 委譲チェック（作業中）を試すときは**書き込み系**の Bash を使う。`ls` 等の読むだけは数えない設計なので、`ls` で10手流しても出ないのが正しい（一度「出ない」と誤読しかけた）。
7. 「ほかの事業のリポ」の対照は実在するリポで取る。`~/Claude Code/ai-company-homepage` は無かった（memory の場所は古い可能性）。`ai-company-tokyo_tour_inbound` で無音を確認。

## 未確認のまま残したもの
- 実際のアプリの会話で deny／差し込みが効くか（社長がフォルダなしで物販の話をしたときに見る）。
- worktree 3本の古い settings.json。

試験スクリプト：scratchpad の live.py・live2.py（使い捨て。手順は上の4〜6で再現できる）。
