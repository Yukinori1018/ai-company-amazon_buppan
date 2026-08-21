# Claude Code サブエージェント登録とフック実装の知見

作成: 2026-08-21 / T-20260821-002（タカシ）

## 1. `.claude/agents/<name>.md` の仕様（公式ドキュメント確認済み）

出典: https://code.claude.com/docs/en/sub-agents.md（2026-08-21 claude-code-guide 経由で確認）

- frontmatter 必須キーは **`name`** と **`description`** の2つだけ。
- **`name` は「小文字＋ハイフン」が公式の記法**。アンダースコアは仕様書に書かれていない。
  → `agents/general_affairs/` のようなディレクトリ名（snake_case）とは**別物として扱い**、
     エージェント名は `general-affairs` / `content-creator` / `it-engineer` とハイフンにした。
  → 本文中の参照パス（`agents/general_affairs/agent.md` 等）は snake_case のまま。ここを混同しない。
- **`tools` はカンマ区切り「文字列」**（YAML 配列ではない）。例: `tools: Read, Write, Edit, Bash, Grep, Glob, WebFetch, WebSearch`
- **`tools` を省略すると全ツールを継承する（MCP 含む）**。
  → **MCP を使うロールでは `tools` を書いてはいけない。** このリポの MCP ツール名は
     `mcp__129f29a9-9065-42b6-88ed-b992a7e37747__notion-*` のように**セッションごとに変わる UUID** を含むため、
     許可リストに固定名で書けない。マリエ（Notion 同期）とタカシ（ブラウザ検証等）は意図的に省略した。
- 他に `disallowedTools` / `model`（sonnet|opus|haiku|inherit）/ `permissionMode` / `maxTurns` / `memory` / `skills` 等があるが、
  YAGNI で今回は使っていない。`model` は省略＝既定に任せた。
- **本文＝そのサブエージェントのシステムプロンプト**。日本語で問題なし。
- `description` が**自動委譲の判断材料**になる。だから「◯◯と言われたらこのエージェント」と
  トリガー語を description に直接書き込むのが効く。

### 検証できなかったこと（正直に記録）
`claude --agent <name> -p ...` で実ロードを確認しようとしたが、
**`401 OAuth access token has been revoked` で認証段階に阻まれ、名前解決の可否を実測できなかった**。
存在しない名前でも同じ 401 で落ちるため、比較試験も不成立。
→ だから「動くか賭ける」のではなく「公式記法に寄せる」判断（ハイフン）を取った。

## 2. 空白入りパスの地雷（このリポ固有・最重要）

リポジトリパスが `/Users/yukinori/Claude Code/ai-company-amazon_buppan` で**フォルダ名に空白を含む**。

`session-start.sh` は次の書き方をしていて、**設置以来一度もリマインダーが発火していなかった**：

```bash
TICKETS_DIRS="$REPO/workspace/tickets/doing $REPO/workspace/tickets/waiting"
for TICKETS_DIR in $TICKETS_DIRS; do   # ← クォートなし＝空白で単語分割
  [ -d "$TICKETS_DIR" ] || continue    # ← 全部 false → 全 continue → 走査対象ゼロ
```

`/Users/yukinori/Claude` と `Code/workspace/tickets/doing` に割れていた。修正は配列化：

```bash
TICKETS_DIRS=( "$REPO/workspace/tickets/doing" "$REPO/workspace/tickets/waiting" )
for TICKETS_DIR in "${TICKETS_DIRS[@]}"; do
```

**教訓（これが本体）:**
- `bash -n` が通ることは「動く」ことの証明にならない。**このバグは構文的に完全に正しい。**
- **必ず「空白入りの実パス」で実走し、期待した件数が出ることまで確認する。**
  今回は修正後に実走し 29 件を検出、独立に awk で数えた実数 29 件と一致することまで確認した。
- 静かに失敗するフックが最悪。`continue` で握りつぶす設計は、失敗が見えない。

## 3. フック実装の型（このリポの流儀）

- 出力は `jq -n --arg msg ... '{hookSpecificOutput:{hookEventName:"<Event>", additionalContext:$msg}}'`。
  jq が無ければ stdout に素で書く（Claude は stdout も読む）フォールバックを必ず付ける。
- **UserPromptSubmit / PostToolUse は常に `exit 0`**（社長の作業を止めない）。ブロックは Stop フックだけ。
- 判定ロジックが少しでも複雑なら **`python3 - <<'PY'` ヒアドキュメント**に逃がす。bash の正規表現で粘らない。
  入力は `export HOOK_INPUT="$(cat)"` で環境変数経由に渡すのが既存の流儀。
- 不正 JSON・空 stdin では黙って `sys.exit(0)`。フックがエラーを吐いて社長の画面を汚さないこと。

## 4. リマインダーフックのノイズ抑制（delegation-check.sh の設計）

「毎回出る警告は、3日で誰も読まなくなる」。3層で抑制した：
1. 短文（12文字未満）・スラッシュコマンド・相槌の正規表現はそもそも無音
2. 担当キーワードにマッチした時だけ発火し、**担当名を名指しする**（汎用の説教は読まれない）
3. 状態ファイル（`$TMPDIR/claude-delegation-check-<session_id>.state`）でクールダウン。
   担当特定時 8 分／汎用 20 分。ただし**新しい担当が現れたら即再点火**する。
   → 状態をリポ内に置かない。`$TMPDIR` + session_id なら .gitignore もセッション後の掃除も不要。

## 5. frontmatter は「機械が読む契約」

`owner:` と `assignee:` は日本語だとどちらも「担当」で、**書いた本人には違いが見えない**。
テンプレに警告文を書くだけでは再発する（実際に13枚壊れた）。
→ PostToolUse フックに機械的検証を相乗りさせた。`ticket_id` 形式・`assignee` 固定語彙10種・
   エイリアス誤用（`id`/`owner`/`related`/`due` 等）を警告する。**ブロックはしない。**
→ 全85枚に通した結果、`related:`（正: `related_tickets:`）が **12枚**残存していることを発見。
   人間向けの注意書きより、機械チェックのほうが安い。

## 6. 追記（2026-08-21）：CLI バイナリを grep して仕様を確かめようとして失敗した話

`claude.exe` は **210MB の単一バンドル**。`strings | grep` も `grep -a -E` 直接も
**2分のタイムアウトを超えて完走しなかった**（2回試して2回とも打ち切り）。
バンドル内の実装から仕様を裏取りするのは、このサイズでは割に合わない。

そして**そもそもこの調査は不要だった**。
確かめたかったのは「`name` にアンダースコアが使えるか」だが、
採用した**ハイフンは公式記法として明記されている＝どちらに転んでも安全**。
「アンダースコアも通るか」が分かっても、打ち手は1ミリも変わらない。

**教訓:** 調べる前に「この答えで自分の行動は変わるか？」を1回問う。
変わらないなら調べない。安全側の選択肢が既に手元にあるなら、
確証を取りに行くより先に**それを採用して前に進む**（YAGNI は調査にも適用される）。
実ロードの可否は、次セッションで Agent ツールの選択肢を**目視する**のが最も安く確実。

## 7. 追記（2026-08-21）：バリデータの穴 ―― 「形式が正しい」は「一意である」を意味しない

初版のバリデータは `ticket_id` の**有無と形式**、`assignee` の**語彙**を見ていたが、
**重複を見ていなかった**。ここから実害が出た。

同じ `ticket_id` を持つ別チケットが2組、**約3ヶ月放置**された：
- `T-20260603-003` = 登録チェックリスト(waiting) と 返金交渉(done)
- `T-20260706-001` = 買い候補17件(waiting) と Sato-Scope brand/manufacturer(done)

**実害:**
1. Notion で別チケットの状態を上書き
2. 後発の `done/T-20260706-001` がキーを奪われ、**Notion 上にカードが存在しない**＝ボードから消えていた
3. 秘書も庶務も `ls workspace/tickets/*/${id}_*.md | head -1` で確認しており、
   **`head -1` が2枚目を隠して**検証をすり抜けた

**教訓（3点）:**
- **一意性は形式検証とは別の軸。** `T-\d{8}-\d{3}` にマッチしても、同じ値が2つあれば
  同期キーとしては破綻する。「値が妥当か」と「値が衝突していないか」は別のチェック。
- **`head -1` / `| head` は検証コードで使ってはいけない。** 「1件見つかった」を
  「1件しかない」と誤読させる。まさにこの事故を3ヶ月隠した張本人。
  警告を出す時は**必ず全パスを列挙する**（片方だけ出す実装は同じ見落としを再生産する）。
- **独立検証は「別経路」でやる。** カズヨの確認は `grep '^ticket_id:' | uniq -d`。
  同じ発想で数え直しても、同じ穴を踏む。こちらは frontmatter ブロックの厳密パース＋
  `os.walk` 全階層＋ファイル名 ID との突き合わせ、という別経路で数えて2組と確認した
  （加えて「ticket_id 欠落0枚」「ファイル名と frontmatter の ID 不一致0枚」も同時に取れた）。

**実装コスト:** 90枚の全走査で **20ms**（frontmatter はファイル先頭にあるので冒頭4096バイトだけ読む）。
フック全体183msの大半は python 起動コストで、走査は誤差レベル。毎回の Write で全数チェックして問題ない。
