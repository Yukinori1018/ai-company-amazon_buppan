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
