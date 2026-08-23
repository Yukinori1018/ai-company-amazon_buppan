# MCP のシークレット保管設計 — この会社での既定解

記録：タカシ ／ 2026-08-24 ／ 出典チケット T-20260824-001（Keepa 公式 MCP 導入設計）

## 結論（次に MCP を足すときはこれを既定にする）

**キーは macOS キーチェーン + `headersHelper` + `--scope user`。** リポジトリにも第三者 SaaS にも平文で置かない。

```bash
# 1. キー登録（-w を値なしで末尾に置くと非表示プロンプト＝シェル履歴に残らない。-U は上書き）
security add-generic-password -s <service-name> -a <acct> -U -w
# 2. ヘルパー（キーを含まない。stdout に JSON を1個。エラーは stderr へ）
#    printf '{"Authorization": "Bearer %s"}\n' "$(security find-generic-password -w -s <service-name>)"
# 3. 登録（リポ外の ~/.claude.json に入る）
claude mcp add-json --scope user <name> '{"type":"http","url":"...","headersHelper":"'"$HOME"'/.claude/scripts/<name>-auth.sh"}'
```

ローテーションは 1 だけ再実行。MCP 設定は触らない。

## なぜこの会社では「gitignore を信じる」設計にしないのか（最重要）

**本リポジトリは GitHub 上で PUBLIC で、`.claude/scripts/github-sync.sh` が30分ごとに `git add -A` → commit → push する。**
（`gh repo view` で `"visibility":"PUBLIC"` を実測。2026-08-24）

つまり防御が `.gitignore` の1行しかない。それが消える／パスが変わる／`git add -f` を打つ／キーを含む新ファイル名が生まれた瞬間に、
**全世界に公開され Git 履歴に永久に残る**。除去は force push ＝ CLAUDE.md §4.1 該当で事故後コストが極めて高い。

→ 方針は「リポジトリの外に出し、かつ平文で存在させない」。**この判断は今後の全 MCP・全シークレットに適用する。**

## Claude Code の設定機構（検証済みの事実）

| 事実 | 備考 |
|---|---|
| `${VAR}` / `${VAR:-default}` 展開は `.mcp.json` **と `~/.claude.json` の local/user スコープ両方**で効く | 対象は `command` / `args` / `env` / `url` / **`headers`** |
| `--scope local`（既定）→ `~/.claude.json` の `projects["<path>"].mcpServers` | リポ外 |
| `--scope project` → リポ直下の `.mcp.json` | **リポ内。シークレット用途では選ばない** |
| `--scope user` → `~/.claude.json` ルートの `mcpServers` | リポ外。**シークレットを含むならこれを既定に** |
| `headersHelper` = 接続時に実行され **stdout の JSON オブジェクト**をヘッダに使う | タイムアウト10秒／キャッシュなし／セッション開始時と再接続時に実行／401・403 で自動再実行＋1回リトライ |
| `headersHelper` は project/local スコープでは trust ダイアログ承認後にしか動かない。**user スコープなら制限なし** | user スコープを推す理由の1つ |
| `security ... -w` を**値なしで末尾**に置くと非表示プロンプト | man に "Put at end of command to be prompted (recommended)"。**シェル履歴にキーが残らない** |
| **クラウド／モバイルのセッションには専用シークレットストアが無い** | 公式が「環境変数はその環境を使う人なら誰でも読める」と警告。クラウド回では使わせない |

**未検証のまま残した点：** `claude mcp add --header 'Bearer ${VAR}'` が add 時に展開するか接続時まで保持するかは公式に記載なし。`headersHelper` のタイムアウト／不正 JSON 時のフォールバック挙動も未記載。`.claude/settings.json` の `env` が `.mcp.json` の `${...}` 展開に届くかも未記載。**推測で埋めず「未検証」と書いた。**

## 「キーを Notion 等の SaaS に置いて読み込む」は技術的に成立しない

社長からこの形の希望が出た（2026-08-24）。**却下ではなく「実現経路が無い」ことを説明する**のが正しい返し方。

MCP のヘッダを Claude Code が解決できる経路は3つだけ：**①リテラル ②`${ENV_VAR}` ③`headersHelper` の stdout**。
「SaaS から読む」はこのどれでもない。実現するなら、

- **(a) 人間/AI が毎回コピペ** → 「1回貼る」が「毎回貼る」に増えるだけで手間が純増
- **(b) `headersHelper` に SaaS の API を叩かせる** → **秘密を守るために別の秘密（SaaS トークン）を平文で置く循環**。しかも10秒制限内にネットワーク往復

さらに、**SaaS から読むたびにキーが AI のコンテキストに載る＝ Anthropic API に送信され、セッション記録 `~/.claude/projects/.../*.jsonl` に平文で残る。** キーチェーン方式ならこれがゼロ。

## 社長の希望を否定せずに扱う型（横展開できる）

社長の希望には**表明（Notion に置きたい）と、その裏の要求（デバイス間で同期したい）**がある。
**表明を評価して終わらせず、裏の要求を別手段で満たす**と「なるほど、ならこっちだ」になる。

今回：iCloud キーチェーンで Apple デバイス間は自動同期される → Notion を経由せず要求が満たされる。
満たせない部分（クラウド／モバイル）は**正直に「解決できない」と書き、既存の前例に寄せた**
（CLAUDE.md のカタログ同期も「クラウド回は CSV 追記まで、同期は次のローカル回」という同じ割り切り。**新しい例外を作らない**）。

## YAGNI の線引きをどう説明したか

「キーチェーンは大げさでは？」に対する答え：**増えるのは1回きりの2コマンドだけで、継続的な複雑さ（監視・ローテーション基盤・権限管理）はゼロ。**
1行で済む案A（`--scope user` に直書き）も**リポ外なので十分許容できる**と明記し、フォールバック経路として残した。
**推奨を1つ出しつつ、劣位案を「悪い」と書かない**ほうが社長は判断しやすい。

## 実装上の細かい罠

- **`md2html.py`（agent_output/T-20260824-001）は ``` フェンス未対応。**コマンドが1行に潰れて壊れる。
  コマンドが主役の文書では**必ずフェンスを退避 → 変換 → `<pre>` で戻す**前処理を入れる。
  他チケットが使っているので **md2html.py 本体は変更しない**（`render_mcp_setup.py` 側で吸収した）。
- `md2html.py` は末尾で `main()` を呼ぶ。**そのまま import すると他人の成果物 HTML を上書きする。**
  `re.sub(r'^main\(\)\s*$','',src,flags=re.M)` してから `exec` する。
- ヘルパースクリプトのエラーは**必ず stderr**。stdout を汚すと JSON パースが壊れて認証が落ちる。
- 検証はダミー値で。`security add-generic-password -s <test> ... -w "DUMMY"` → 読み戻し → `delete` で後始末。
  **本番のサービス名でダミーを入れない**（社長が後で混乱する）。

## 消費トークンの注意（Keepa MCP 固有）

MCP のツール呼び出しは**既存プランの Keepa トークンを消費する**（新規課金は無し）。
**夜間自走やループから無制限に呼ばせない。**既存の夜間スキャン（T-20260803-001 系）と食い合う。
用途は「対話中の単発調査」に限定。大量取得は従来どおり REST を直に叩くスクリプト側で
（Keepa 公式も「プログラムから使うなら REST API を直接使え。MCP の応答は言語モデル向けに整形してある」と明記）。
