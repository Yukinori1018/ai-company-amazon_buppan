# ログイン延命：Chrome の専用ウィンドウを launchd＋AppleScript で再読込する（2026-10-12 / T-20260920-003）

社長「ログインが何回も切れて私にお願いが来る。そうならない工夫を」への答え。
実体：`deliverables/T-20260920-003/login_keepalive/`・入口 `.claude/scripts/login-keepalive.sh`・
launchd `com.aicompany.amazon-buppan.login-keepalive`（600秒・RunAtLoad）。状態は `agent_output/T-20260920-003/login_watch/`。

## 型（次に同じ依頼が来たらこのまま使う）
- **専用ウィンドウを1枚**。1枚目のタブをリポ内の `keepalive_window.html`（file://）にして、それを印にウィンドウを探す。
  window id は Chrome 再起動で変わるので保存しても無駄。印方式なら「前回のページを開く」で復元されても見つかる。
- **社長の他のタブは読まない**：AppleScript 内で「tab 1 の URL に印があるか」だけ判定し、ウィンドウ id 以外は Python に返さない。
- `osascript -e '<script>' arg1 arg2` ＋ `on run argv` で引数を渡す（文字列埋め込みのエスケープ地獄を避ける）。
  区切りは ASCII 31/30（タイトルにタブや改行が入っても壊れない）。
- **「JavaScript from Apple Events」は不要**。URL・title・loading・reload・set URL だけで足りる。DOM は読まない＝Chrome 設定を変えさせない。
- Chrome が起動していなければ何もしない（`tell application` は起動してしまうので先に `pgrep -x "Google Chrome"`）。
- 社長がウィンドウを閉じたら出し直さない（10分ごとに窓が湧く）。作り直すのは `setup` と Chrome の pid が変わったときだけ。
- launchd 文脈からの osascript も 10/12 は TCC プロンプトなしで通った（kickstart で reload まで実測）。

## 検知は「読み込み後の URL」で。ただし URL で分からないサイトがある
| サイト | 非ログイン時の行き先（10/12 実測） |
|---|---|
| セラセン `/home` | curl では `/ap/signin`、**Chrome では `/amazonsell/business`（出品案内）**。最初これを OK と誤判定した |
| SD `/i/r/msgbox/` | `/p/do/clickMemberLogin` |
| 卸売ドットコム `mypage.php` | `login.php` |
| 卸問屋.com `MyPage.asp` | `sessionMessage.asp` |
| Gmail `u/1` | `accounts.google.com`（別ホストに出るので tab id で追う） |
| 国分 `menu.aspx` | **同じ URL のままログイン欄を表示**→検知不可。`unknown` と書き、OK とは書かない |
- 🔴 **curl の結果と Chrome の結果は違う**（セラセン）。判定パターンは必ず実ブラウザで1回回して確かめる。
- エラー判定をタイトルの `\b503\b` にすると Gmail の「受信トレイ (503)」で誤報する。先頭か「Error 503」に限る。NETSEA の障害ページは「サイト障害」。
- 「最後に OK だった時刻」を ALERT に書く＝セッションの実寿命の実測になる。間隔は実測で直す（§3.1）。

## 線引き
- パスワード・Cookie は扱わない。Chrome 設定（Preferences）を読むコマンドは auto mode の分類器が PII として止めた＝読まないのが正しい。設定の確認は社長の一手として一覧に書く。
- SD は §3.3-18 の1日30回以内（60分×7〜24時＝17回）にテストで固定した。
- スリープ中は延命も止まる。スリープ設定の変更は社長判断として渡した（自分で pmset/caffeinate しない）。
