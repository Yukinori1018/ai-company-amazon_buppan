# 成果物カタログ → Google スプレッドシート 書き込み連携

成果物カタログのマスター CSV を、**URL を変えずに**同じ Google スプレッドシートへ
反映するための連携です。仕組みは「Apps Script Web App に CSV を POST → シートを
全クリアして全行書き込み（ミラー更新）」。

- 対象シート: <https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit>
- マスター CSV（真実）: `workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`
- 認証情報をローカルに置かない（OAuth/サービスアカウント不要）。共有トークンのみ。

---

## カタログの作り方（2026-09-09 / T-20260909-003）

手で1行ずつ追記する運用は廃止しました（積み残しが 248 件になったため）。
`deliverables/` を走査してマスター CSV を生成します。

```bash
python3 scripts/catalog/build_catalog.py            # マスター CSV を再生成
python3 scripts/catalog/build_catalog.py --dry-run  # 書かずに件数だけ確認
python3 scripts/catalog/build_catalog.py --check-untracked  # 追跡漏れの検知
python3 scripts/catalog/build_catalog.py --html     # 旧 HTML 版も出す（既定オフ）
```

- **社長の入口は Google スプレッドシートです**（2026-09-09 社長指示）。
  HTML 版カタログ（`00_成果物カタログ.html`）は入口ではなくなりました。
  既定では再生成しませんが、**ファイルは削除せず残置**しています（§4.1 不可逆な削除）。
  内容は 2026-09-09 時点のまま古くなります。必要なら `--html` で更新してください。
- 既存の 内容（要約）/ 暫定結果 / 備考 / 種別 / 担当 は、リポジトリ相対パスをキーに
  **必ず引き継ぎます**。新規行の要約は `要記入`。
- 走査対象はファイルシステムであって git ではありません。卸値を含むため追跡していない
  成果物も「ローカルのみ」として載ります（社長のローカルには実在するため）。
- 順番は **build_catalog.py →（マリエが要約を記入）→ sync_catalog_to_sheet.py**。

---

## シートのセルからローカルの実ファイルを開く（配信サーバ）

**要件**: スプレッドシートの成果物をクリックしたら、社長の Mac 上の実ファイルが開くこと。

**なぜサーバが要るのか**: Google スプレッドシートのハイパーリンクは `file://` を開けません
（`=HYPERLINK("file:///…")` は無効扱いになり、通ってもブラウザ側が遮断します）。
そこで **127.0.0.1 だけに bind した小さな HTTP サーバ**を常駐させ、
`http://localhost:17325/<相対パス>` でローカルの実ファイルを返します。
配信するのは `workspace/output/deliverables/` の中だけです。

### 起動・状態確認・停止

```bash
# 起動（前景。Ctrl-C で停止）
python3 scripts/catalog/serve_deliverables.py

# 起動（背景。ターミナルを閉じても残す）
nohup python3 scripts/catalog/serve_deliverables.py > /tmp/catalog-server.log 2>&1 &

# 起動しているか
python3 scripts/catalog/serve_deliverables.py --status
# → "port 17325: 起動中" / "停止中"

# 停止
pkill -f serve_deliverables.py
```

**ポート 17325 を選んだ理由**: 非特権（1024 以上で sudo 不要）／macOS のエフェメラルポート
範囲 49152–65535 の外（OS に横取りされない）／主要ツールの既定ポート
（3000・4000・5000＝AirPlay Receiver・5173・8000・8080・8787＝wrangler dev・8888・9000）
から離れている。変更する場合は `serve_deliverables.py` の `DEFAULT_PORT` と
`build_catalog.py` の `CATALOG_PORT` を**両方**そろえ、CSV を再生成してください
（環境変数 `CATALOG_PORT` で両方をまとめて上書きできます）。

### 安全側の作り（緩めないこと）

| 守り | 実装 |
|---|---|
| LAN に出さない | `127.0.0.1` にのみ bind。`0.0.0.0` にすると同じ Wi-Fi の全員に卸値が配られます |
| 配信ルートより上を出さない | `..` を除去したうえで、最終的な `realpath` がルート配下かを確認。外を指すシンボリックリンクは 403 |
| 書き込ませない | GET と HEAD のみ。POST/PUT/DELETE のハンドラを持たない |
| 検索エンジンに拾わせない | `X-Robots-Tag: noindex, nofollow` と `Cache-Control: no-store` |

HTML はブラウザで描画、`.md` `.py` などはテキスト表示、
`.csv` `.xlsx` などは `Content-Disposition: attachment` でダウンロードされます。
日本語ファイル名はパーセントエンコードで正しく解決します（14 URL で実測確認済み）。

### Mac ログイン時の自動起動（launchd）— **未設置。社長の承認待ち**

雛形だけ用意してあります。**まだシステムには何も入れていません。**

- 雛形: `scripts/catalog/com.aicompany.catalog-server.plist.example`

導入する場合の手順（3コマンド）:

```bash
REPO="/Users/yukinori/Claude Code/ai-company-amazon_buppan"
sed "s|__REPO_ROOT__|$REPO|g" "$REPO/scripts/catalog/com.aicompany.catalog-server.plist.example" \
  > ~/Library/LaunchAgents/com.aicompany.catalog-server.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aicompany.catalog-server.plist
```

確認は `python3 scripts/catalog/serve_deliverables.py --status`。
外すときは `launchctl bootout gui/$(id -u)/com.aicompany.catalog-server` のあと
plist を削除します（削除は §4.1 なので社長承認のうえで）。

## 構成ファイル

| ファイル | 役割 |
|---|---|
| `build_catalog.py` | deliverables を走査してマスター CSV を生成する（HTML は `--html` 時のみ） |
| `serve_deliverables.py` | deliverables を 127.0.0.1 限定で配信する HTTP サーバ（シートのリンク先） |
| `com.aicompany.catalog-server.plist.example` | 上記をログイン時に自動起動する launchd 雛形（**未設置**） |
| `catalog_sync.gs` | シート側に貼る Apps Script。POST を受けてシートを全置換する |
| `sync_catalog_to_sheet.py` | ローカルから CSV を読んで POST するヘルパー（標準ライブラリのみ） |
| `.catalog_sync.env.example` | 設定見本。これをコピーして `.catalog_sync.env` を作る |
| `.catalog_sync.env` | 実設定（URL・トークン）。**gitignore 対象** |

---

## 社長の一度きり初期設定（クリック単位・全10ステップ）

> 所要 5〜10 分。一度やれば以降は秘書が `python3` 一発で同期できます。

1. 対象スプレッドシートをブラウザで開く。
2. 上部メニュー **拡張機能 → Apps Script** をクリック（新しいタブでエディタが開く）。
3. 既存の `コード.gs` の中身を全選択して削除し、リポジトリの
   `scripts/catalog/catalog_sync.gs` の中身を**全部コピペ**して、フロッピーアイコン（保存）をクリック。
4. 左側の歯車 **プロジェクトの設定** をクリック → 下部の **スクリプト プロパティ** →
   **スクリプト プロパティを追加** をクリック。
   - プロパティ名: `SHARED_TOKEN`
   - 値: 任意の長いランダム文字列（例: `Kx9aQ2m...` 24文字以上推奨）→ **スクリプト プロパティを保存**。
   - ※この値は後でステップ9で `.env` にも貼るので控えておく。
5. 右上 **デプロイ → 新しいデプロイ** をクリック。
6. 「種類の選択」の歯車 → **ウェブアプリ** を選択。
7. 設定を以下にする:
   - 説明: 任意（例: catalog sync v1）
   - 次のユーザーとして実行: **自分**
   - アクセスできるユーザー: **全員**
     （トークンで保護するため。「全員」でないとローカルから叩けません）
8. **デプロイ** をクリック → 初回は **アクセスを承認** を求められるので、
   自分の Google アカウントを選び、「詳細 → （プロジェクト名）に移動 → 許可」で認可する。
9. 表示される **ウェブアプリ URL**（末尾 `/exec`）を**コピー**。
10. リポジトリで `scripts/catalog/.catalog_sync.env.example` を
    `scripts/catalog/.catalog_sync.env` にコピーし、
    `WEBAPP_URL=` にステップ9の URL、`SHARED_TOKEN=` にステップ4の値を貼って保存。

これで設定完了です。

---

## 同期の実行（設定後・秘書が回す）

```bash
# 送信せず内容だけ確認（行数・先頭行のプレビュー）
python3 scripts/catalog/sync_catalog_to_sheet.py --dry-run

# 実送信（シートを全置換でミラー更新）
python3 scripts/catalog/sync_catalog_to_sheet.py

# 別の CSV を指定する場合
python3 scripts/catalog/sync_catalog_to_sheet.py --csv path/to/other.csv
```

成功すると `[OK] 同期成功: シート=..., 書き込み NN 行 x 12 列` と表示されます。

---

## トラブルシュート

| 症状 | 原因と対処 |
|---|---|
| `WEBAPP_URL が未設定` と出て送信されない | `.catalog_sync.env` 未作成。ステップ10をやり直す |
| JSON でない（HTML）レスポンス | デプロイのアクセス権が「全員」でない。ステップ7を修正し再デプロイ |
| `unauthorized` | `.env` の `SHARED_TOKEN` と Script Property の値が不一致 |
| 接続失敗 | URL の末尾が `/exec` か確認。`/dev` ではない |
| シートのリンクを押しても何も開かない | 配信サーバが止まっている。`python3 scripts/catalog/serve_deliverables.py --status` で確認し、停止中なら起動する |
| リンクが青字にならず `=HYPERLINK(...)` の文字列のまま | CSV 生成が古い。`build_catalog.py` を実行してから再同期する |
| コードを直したのに反映されない | Apps Script で **デプロイ → デプロイを管理 → 編集（鉛筆）→ バージョン「新バージョン」→ デプロイ**。URL は変わりません |

## 設計メモ

- 行追記ではなく**全置換**。マスター CSV が常に真実で、シートはそのミラー。
  差分計算が不要で冪等（何度流しても同じ結果）。
- HTTP ステータスは Apps Script の制約で常に 200 系。成否はレスポンス JSON の
  `ok` フラグで判定している（`sync_catalog_to_sheet.py` 側で処理）。
- 列数が不揃いな行は Web App 側で右パディングしてから書き込む。
