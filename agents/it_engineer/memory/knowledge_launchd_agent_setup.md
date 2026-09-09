# launchd 常駐エージェントの設置と検証（macOS）

初出: 2026-09-09 / T-20260909-004 発注（実体は T-20260909-003 の続き）
対象: `com.aicompany.catalog-server`（成果物配信サーバ `scripts/catalog/serve_deliverables.py`）

## 設置の型（このリポの標準手順）

```bash
REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
sed "s|__REPO_ROOT__|$REPO|g" "$REPO/scripts/catalog/com.aicompany.catalog-server.plist.example" \
  > ~/Library/LaunchAgents/com.aicompany.catalog-server.plist
plutil -lint ~/Library/LaunchAgents/com.aicompany.catalog-server.plist   # ← 必ず挟む
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aicompany.catalog-server.plist
```

- `bootstrap` の exit=0 は **plist を読めた**というだけ。**プロセスが生きている保証ではない。**
  必ず `launchctl print gui/$(id -u)/<label>` で `state = running` と `last exit code` を見る。
- `sed` の置換対象がコメント本文にも出てくると、設置後の plist のコメントが意味不明になる。
  設置済みコピーのヘッダは「これは実物」「停止/再起動コマンド」に書き換えておくと半年後に助かる。
- パスに空白（`Claude Code`）が入るので、シェル変数は必ずクォートする。plist 内の `<string>` は
  XML なのでエスケープ不要。

## 踏んだ罠 — 手動起動プロセスとのポート衝突

launchd 設置時、**別セッションが `nohup python3 serve_deliverables.py &` で同じポートを掴んでいた**。
結果 `OSError: [Errno 48] Address already in use` で `last exit code = 1`、KeepAlive が
ThrottleInterval（10秒）おきに失敗し続ける状態になった。**しかも `curl` は 200 を返す**
（手動プロセスが応答するため）ので、curl だけ見ていると成功と誤認する。

教訓:
- 常駐化の前に `lsof -nP -iTCP:<port> -sTCP:LISTEN` と `pgrep -fl <script>` で先客を確認して止める。
- 検証は **curl だけで済ませない**。`launchctl print` の `last exit code` / `state` と必ず両方見る。
- 常駐化した後は手動起動を禁止する旨を README に書く（今回書いた）。

## 検証チェックリスト（常駐サーバを入れたら毎回これを回す）

1. `launchctl print gui/$(id -u)/<label>` → `state = running` / `last exit code` が無いか 0
2. `curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>/` → 200
3. 日本語ファイル名を URL エンコードして `curl -I` → 200（`urllib.parse.quote` で作る）
4. 配信ルート外へ出るパス → 拒否されること
5. `StandardOutPath` / `StandardErrorPath` が実在し書けているか
6. **KeepAlive の実地テスト** — pid を kill して、別 pid で復活するか

6 は省略しがちだが、KeepAlive は plist に書いただけでは効いている証明にならないので必ずやる。
今回は pid 16756 → kill → 1 秒後に pid 16922 で復活を確認した。

## 判明したこと（serve_deliverables.py 固有）

- **ルート外パスは 403 ではなく 404 になる。** `translate_path` が `..` セグメントを
  **除去**してからルート起点で組み立てるため、`/../CLAUDE.md` は `<root>/CLAUDE.md` に化けて
  「存在しないファイル」＝404。`%2e%2e` や多段 `../` も同様に全て 404。
  情報は漏れないので実害はないが、**「403 が返るはず」と思って検証すると誤って不合格と判断する。**
- 403 を返すのは `_inside_root()` が効く経路＝**シンボリックリンクの飛び先がルート外のとき**。
  実地確認するにはリポを汚さずスクラッチに `--root` を向けた2台目を別ポートで立てるのが早い
  （`--port 17399 --root /tmp/.../root`）。今回この方法で symlink 経由 403・中身非漏洩を確認済み。
- `StandardOutPath` は Python の stdout バッファリングのため **常駐中はほぼ空**。起動バナーは
  プロセス終了まで flush されない。ログを見るときは `err` 側を見る（アクセスログもそちら）。
- 書き込み系メソッドは `SimpleHTTPRequestHandler` が未実装なので PUT/POST は 501。意図どおり。

## 並行セッションがいるときの作法

この回は「git 操作を一切するな」という制約付きだった（別エージェントが同じリポで作業中、
`git add -A` による巻き取り事故が同日発生済み）。
- リポ内ファイルの編集は README とテンプレのコメントに限定し、報告に一覧を明記した。
- 検証用の一時ファイルは**リポ内に作らない**（スクラッチディレクトリを使う）。deliverables 配下に
  テスト用 symlink を作ると 30 分ごとの自動同期に巻き込まれる。
- 他エージェントが起こしたプロセスを止めるときは、止めてよい理由（同一スクリプト・同一ポートで
  launchd 側が代替する）を確認してから。相手の検証を壊さない。

## 停止・撤去

```bash
launchctl bootout gui/$(id -u)/com.aicompany.catalog-server        # 停止（次回ログインで復活）
launchctl kickstart -k gui/$(id -u)/com.aicompany.catalog-server   # 再起動（コード修正後）
# 完全撤去は bootout のあと plist を削除。削除は CLAUDE.md §4.1 なので社長承認が要る。
```
