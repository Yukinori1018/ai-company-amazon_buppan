# 予約タスクの停止検知（2026-10-10 / T-20260920-003）

## 事象
- Claude デスクトップの予約タスクは permission mode=default で起動する。最初の Bash/Chrome で許可画面を出し、夜間は誰も押さないので "running" のまま永久停止。
- per_task 上限1・global 上限3 が埋まり、新規タスク（amazon-buppan-nightly-sourcing）は一度も起動しなかった。9/30 以降1件も完了なし。**誰も気づかなかった**のが本当の事故。

## 仕組み
- `.claude/hooks/scheduled_task_health.py` を `session-start.sh`（リマインダー⑨）から呼ぶ。異常時だけ additionalContext の先頭に 🔴。
  - (a) `~/Library/Logs/Claude/main.log` の末尾4MB（36h超を確実に含む・実測で約66h分）から `[CCDScheduledTasks] Skipping dispatch` / `Not auto-approving` をタスク別に件数・最終時刻で集計
  - (b) 有効タスクの台帳 `~/Library/Application Support/Claude/claude-code-sessions/*/*/scheduled-tasks.json`（`enabled`, `cwd`, `createdAt`, `lastRunAt`）を読み、`OUTPUT_WATCH` に登録したタスクの成果物フォルダ最新 mtime が基準時間より古ければ警告
- 処理 0.4 秒。テスト `.claude/hooks/tests/test_scheduled_task_health.sh`（環境変数でログと台帳を差し替え）。

## 学び
- **`lastRunAt` は「起動を試みた時刻」で完了ではない。** 詰まっていても更新される。成功の証拠には使えない → 成果物の mtime を見る。
- ログ文言に依存する検知(a)だけだと、アプリ更新で文言が変わった日に黙る。結果を見る(b)を必ず並べる（「検知器は見張る対象より長生きしなければならない」の再適用）。
- 成果物パスはリポ基準ではなくタスクの `cwd` 基準で引く。worktree から走るとリポ基準では agent_output（gitignore）が空で誤検知する。
- 新しい夜間タスクを作ったら `OUTPUT_WATCH` に1行足す。足さないと(b)の対象外。
