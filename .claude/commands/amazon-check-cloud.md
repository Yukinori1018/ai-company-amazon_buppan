---
description: Amazon 日次チェックのクラウド版（Gmail 通知のみ）を回し、ログに1件追記して push する
---

あなたは秘書のカズヨです。Amazon 日次チェックの**クラウド版**を、今この場で1回実行してください。
クラウドのスケジュールタスク（毎日 11:56 JST 頃）から呼ばれる想定ですが、手で打っても同じです。

背景：2026-09-06〜10-15 の40日間、Mac 側（スケジュールタスク・自動同期・番犬）が丸ごと止まり、
Amazon の重要通知（カナダ店の無効化など）を誰も見ていませんでした（T-20261016-002）。
これは **Mac に依存しない保険**です。Mac 版（`/amazon-check`）の代わりにはなりません。

## できること／できないこと（正直に書く）

| 見る | 見られない（毎回「未確認」と書く） |
|---|---|
| `satoyukinori1018@gmail.com` に届いた Amazon 出品者向けメール（Gmail コネクタ） | セラーセントラルの画面（ログイン・2FA が要る） |
| Mac の自動同期が生きているか（Git 履歴） | `satoyselect@gmail.com`（ケースの返信先） |

## 手順

1. **前回の記録を読む。** `workspace/monitoring/amazon-daily-check-cloud.md` の最新エントリの日付を確認する（その日以降が今回の確認範囲）。

2. **Gmail を検索する**（Gmail コネクタの search_threads。日付は前回エントリの日付）。

   ```
   after:YYYY/MM/DD (from:seller-performance OR from:seller-notification OR from:donotreply@amazon.com OR from:seller.support OR from:merchant-notifications OR from:no-replies-appeals OR from:seller-reactivation OR from:amazon.ca OR from:account-update@amazon.co.jp OR from:no-reply@amazon.co.jp) -from:store-news@amazon.co.jp
   ```

   件名・本文に「停止 / deactivated / suspended / 再開 / reinstated / 本人確認 / verification / 期限 / required / Case」がある通は get_thread で本文を読む。購入者向けの販促は数えない。

3. **Mac の生死を見る。**

   ```
   bash .claude/scripts/sync_liveness.sh --status
   python3 .claude/scripts/amazon_check_log.py status
   ```

4. **`workspace/monitoring/amazon-daily-check-cloud.md` の「---」の直下に1件追記する**（新しい順）。見出しは `## YYYY-MM-DD（クラウド・Gmailのみ）`（日本時間の日付）。
   - 表で：Gmail の結果／セラーセントラル画面＝**未確認**／satoyselect＝**未確認**／Mac の自動同期の状態
   - 新着メールがあれば日時(JST)・差出人・要旨・要対応を表に
   - **新着なしの日も必ず1件書く**。本文に「未実行」という語を使わない（使うと実行されなかった日として数えられる）
   - **`amazon-daily-check.md`（Mac 版）には書かない。** 同じファイルを Mac とクラウドが書くと git が分岐し Mac の自動同期が止まる

5. **commit して push する。** 追記したファイルだけを add する（`git add -A` はしない）。

   ```
   git add workspace/monitoring/amazon-daily-check-cloud.md
   git commit -m "chore(monitoring): Amazon日次確認（クラウド・Gmail）YYYY-MM-DD（変化あり/なし）"
   git push origin HEAD:main
   ```

   push が non-fast-forward で拒否されたら `git pull --rebase origin main` → 再 push（**force push はしない**）。

## してはいけないこと

- Amazon・Gmail で**送信・返信・削除・ラベル変更をしない**（読むだけ。CLAUDE.md §4.1）
- `.claude/scripts/amazon-check-watchdog.sh` を引数なしで走らせない（Mac 専用。ログを書き換える）
- 「メールが無い＝状態に変化なし」と書かない。画面は見ていない
