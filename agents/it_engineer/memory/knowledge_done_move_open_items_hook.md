# done 移動時の未決事項警告フック／台帳鮮度チェック（T-20260912-001・2026-09-12）

## 何を入れたか
- `.claude/hooks/done-open-items-check.sh`（PostToolUse, matcher `Write|Bash`）
  - `mv`/`git mv` のコマンドに `tickets/done` があれば、コマンド中の TicketID で done/ のファイルを引いて「宙に浮・未回答・要確認・未確認」を grep
  - 強い語（宙に浮・未回答）を先頭、残りは下（新しい）から。最大8行。警告のみ・exit 0
- `session-start.sh` リマインダー⑧：auto-memory の `project_amazon_account_ledger.md` の「## 更新ログ」内の最大日付が7日超なら1行。無ければ無音。`LEDGER_PATH` で差し替え可
- テスト: `bash .claude/hooks/tests/test_forgetting_hooks.sh`（11件）

## 設計の判断
- **mv は mtime を保つ**ので「最近変更された done ファイル」方式は効かない。コマンド文字列から ID を拾うのが確実
- auto-memory のパスは リポ絶対パスの英数字以外を `-` に置換（空白・`_` も `-`）
- 実データ T-20260826-004 で試すと13行ヒット＝解決済みも拾う。判定は人に任せ、強い語を先に出して肝心の行（L231 メキシコ）が埋もれないようにした

## 入れなかったもの
- 提案3「気づいた」語で既存記録を grep するフック：固有名詞抽出が曖昧で誤検知が多い。チケット編集のたびに出る警告は読まれなくなる（⑤⑥が「異常時だけ出る」設計なのと同じ理由）。台帳＋報告前照合ルールで代替
