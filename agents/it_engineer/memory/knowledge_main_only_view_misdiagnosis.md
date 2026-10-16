# 「止まった」と言われたら、まず全ブランチを見る（2026-10-16 / T-20261016-002）

依頼の前提は「Amazon 日次巡回も github-sync も 9/6 から40日止まっている」。**実際は止まっていなかった。**
Mac のリポジトリが 9/6 20:57 から `claude/nighttime-work-checkin-iTWEa` に居続け、github-sync
（カレントブランチだけ同期する設計）が 1,193 コミットをそのブランチへ毎日 push していた。
main だけを見るクラウドのセッションと秘書には「Mac が死んだ」と見え、40日前の状態から作業していた。

## 自分がやった誤診（同じ穴に落ちないために）

最初の30分、手元の clone（main だけ fetch 済み）で `git log --all` を見て「Mac 丸ごと停止」
「pre-commit が commit を止めた」と順位付けし、報告書まで書いた。**`--all` は手元にある参照しか見ない。**
クラウドの clone は main しか取っていないことが多い。気づいたのは、動作確認で起動した別セッション
（新しく clone した）が「Mac の自動同期は正常・10/16 03:09」と返したから。

## 最初に打つ1行（これを省いて推論を始めない）

    git fetch origin '+refs/heads/*:refs/remotes/origin/*' && \
    git log --remotes=origin --grep='chore(auto-sync)' -3 --format='%h %ad %D' && \
    git branch -r --contains <最新の auto-sync の sha>

- 自動同期コミットがどのブランチに載っているかで、「止まった」か「別の場所に流れている」かが分かれる。
- 別ブランチなら、Mac の本物の状態は `git show origin/<branch>:<path>` で読める。推測は不要。

## 「止まって見える」と「本当に止まった」は層が違う

同じ40日の中に両方あった。

| 層 | 実態 | 証拠 |
|---|---|---|
| 同期（launchd github-sync） | 動いていた。行き先が main でなかった | ブランチ上の毎日の auto-sync |
| 巡回（Claude の予約タスク） | **9/13〜10/10 は本当に止まっていた** | ブランチ上のログに番犬の「未実行」行 |
| 巡回の原因 | 予約タスクが許可画面で「実行中」のまま停止（上限1件が埋まり次回も起動しない） | Mac 側 `scheduled_task_health.py`（10/10）、allow 追加コミット 206aa06（10/13） |

**片方の説明でもう片方を説明しない。** 「Mac が止まっていた」で巡回の欠測まで説明した気になると、
許可画面という本当の原因を見逃す。

## 設計上の教訓

1. **「カレントブランチだけ同期」は、ブランチに居続けた瞬間に静かな分断を生む。**
   同期ジョブは「どこに書いたか」を外から見える形で出すこと（今回 github-sync に main 以外なら通知を追加）。
2. **検知器は全ブランチを見る。** `sync_liveness.sh` は全ブランチを最大15秒 fetch してから判定する。
   fetch できなかった時は「手元の参照だけで判定」と出力に書く（黙って古い参照で断定しない）。
3. **判定ロジックの入力元を固定しない。** `amazon_check_log.py --ref auto` は Mac が実際に書いている
   ブランチからログを読む。main のファイルを読むと、正しいロジックが古いデータで嘘をつく。
4. **永遠に鳴る警告は警告ではない。** 欠測の警告は直近7日だけにした。過去の欠測は取り返せない。
5. **書き手ごとに1ファイル。** Mac とクラウドが同じログの同じ位置を書くと git が分岐する。
   クラウド巡回は `amazon-daily-check-cloud.md` に分けた。

## クラウドのスケジュールタスクの実測（create_trigger）

- **新規セッション方式（create_new_session_on_fire）は使えなかった**：sources が空で main への push が 403、
  Gmail コネクタも付かない（connectors 引数はこの組織では不可）。
- **専用セッションを create_session（source_url 付き）で作り、persistent_session_id で起こす方式は動く**：
  Gmail 可・push 可（接続確認の1ターンで先に確かめてから trigger を作ること）。
- 試走は fire_trigger。結果は list_events（kinds=result）で読み、ログが push されたかを `git log origin/main` で見る。

## 権限で止まったこと

1,193 コミットのブランチを main に統合する merge commit は、auto mode の分類器に
「共有資源の変更」として止められた。試験 merge（worktree）で競合2件と解決案までは作れる。
**大きな統合は社長（Mac）側でやってもらう前提で、手順と判断材料を渡す**のが正しい分担。
