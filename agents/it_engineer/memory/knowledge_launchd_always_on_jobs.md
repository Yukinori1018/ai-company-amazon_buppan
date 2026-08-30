# macOS で「無人で走り続けるジョブ」を作るときの型（2026-08-31 / T-20260831-002）

`github-sync`（30分間隔・稼働中）と `night-shift`（**14日間・814回 exit 127 で死んでいた**）を
並べて読んで分かったことの整理。**常駐ジョブの依頼が来たら、まずここを読むこと。**

---

## 1. night-shift はなぜ14日間誰にも気づかれなかったか

原因は拍子抜けするほど単純で、`plist` の `ProgramArguments` が指す
`.claude/scripts/night-shift.sh` が **一度も存在しなかった**。`git log` にも無い。
`/bin/bash <存在しないファイル>` は 127 を返すので、13回/晩 × 14日 = 814行が
`workspace/.night-shift/stderr.log` に積まれ続けた。

**教訓は「ログを見なかったこと」ではなく、「誰も見ないログにしか出力しなかったこと」。**
無人ジョブの生死は、**人が必ず通る導線**（この会社なら SessionStart フック）に出す。

    ✅ plist を書いたら、その場でこれを打つ
       python3 -c "import plistlib;print(plistlib.load(open('<plist>','rb'))['ProgramArguments'])"
       ls -l <出てきたパス>
    ✅ load したら `launchctl list | grep <label>` で **exit code が 0** であることを見る
       （2列目が最後の終了コード。127=コマンドが無い、126=実行権が無い、78=設定エラー）

## 2. `KeepAlive` を付けるなら「異常でも exit 0」で終わること

`KeepAlive: true` は終了コードに関係なく再起動する。依存欠落で毎回死ぬコードだと、
`ThrottleInterval`（既定10秒）ごとの再起動ストームになる。

**正解の形**: 起動時に依存チェック → 欠けていたら `ALERT` を書いて **`return 0`**。
「起動しなかった」という事実はファイルに残し、プロセスとしては静かに終わる。
`ThrottleInterval` は明示で60秒以上に。

## 3. 単一インスタンスは `flock`。PID ファイルは信用しない

`kill -0 $(cat pidfile)` は **PID が再利用されると「死んでいるプロセスを走行中と誤判定」**する。
`fcntl.flock(f, LOCK_EX | LOCK_NB)` なら、プロセスが死んだ瞬間に OS がロックを解く。

同じ理由で、**生死の表示にも PID を使わない。** 60秒ごとに `heartbeat.json` を書き、
mtime の古さで判定する。`STATUS.md` の「走行中」という文字列は嘘をつく。

## 4. `StartInterval` と `StartCalendarInterval` の違い

| | スリープ中 | 復帰時 |
|---|---|---|
| `StartInterval` | 発火しない | **溜まったぶんを1回だけ**実行 |
| `StartCalendarInterval` | 発火しない | 同上（時刻を過ぎていれば1回） |

「常時走らせたい」なら、どちらでもなく **プロセス側を無限ループにして `KeepAlive` で戻す**のが素直。

## 5. launchd の環境には Homebrew の PATH が無い

`github-sync.sh` と同じく、スクリプト先頭で明示する。

    export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

## 6. plist はリポにも同じものを置く

`~/Library/LaunchAgents/` は Git の外。Mac を入れ替えたら全部消える。
`deliverables/<ticket>/<label>.plist` に同じものを置き、README に復元手順を書く。

## 7. 「止め方」は1本だけにする

STOP ファイル1つ。スーパーバイザとワーカーで**同じパスを共有**する。
2つ作ると必ず片方を忘れる。README の一番上に `touch` のコマンドを丸ごと書いておく。

---

## 実際に作った構成（参考にしてよい形）

    .claude/scripts/<job>.sh        launchd の入口。run/stop/start/status のサブコマンド
    <deliverable>/always_on.py      無限ループ本体（ガード・子プロセス管理・心拍監視）
    <deliverable>/cycle_state.py    状態遷移の**純ロジック**（I/O なし＝全部テストできる）
    <deliverable>/state/            実行時状態（gitignore）

`always_on.py` は「いつ走らせるか」だけを持ち、実際の仕事は既存スクリプトを
`subprocess` で叩く。**既存の実績あるコードを書き直さずに常駐化できる**のが利点。
セッションを区切って繰り返す（今回は6時間）ことで、自己修復の機会と日次の区切りが手に入る。
