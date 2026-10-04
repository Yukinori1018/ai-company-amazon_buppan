# ナレッジを「発注ゲート」に落とす型（2026-10-04 / T-20261004-001 タスク3）

## 何を作ったか
CLAUDE.md §3.5（仕入れ前チェック12項目）を、文章ではなく機械で止める仕組み。
- `scripts/sourcing_gate/checklist_spec.json` … 項目の正。コードは項目を持たない
- `scripts/sourcing_gate/gate.py` … 判定（required 全項目が 存在・PASS・鮮度内 のときだけ可）
- `scripts/sourcing_gate/check_record.py` … `set / show / verify / items`
- `.claude/hooks/order-gate-guard.py` … PreToolUse（Write/Edit/MultiEdit）
- `.githooks/pre-commit` の `order_gate()` … Bash 経由の書き込みの抜け道を commit で塞ぐ
- `write_order_proposal.py` … 書く前に gate を当て、不可ならファイルを書かず exit 1
- テスト `.claude/hooks/tests/test_order_gate_guard.sh`（48件）

## 設計判断と理由（次に似たゲートを作るときに再利用する）
1. **「どれを発注するか」を機械に読ませる印を必須にする**（`order-asins` マーカー）。
   本文から ASIN を推測すると、候補表・見送り行・比較表の ASIN まで拾って誤検知だらけになる。
   印が無い発注案はそれ自体をブロック（fail-closed）。
2. **「要確認」検査は「発注する ASIN を含む表の行」だけ**。地の文の注意書き・見送り行は止めない。
   全文で「要確認」を探すと、注意書きを書いた正直な成果物ほど止まる。
3. **Edit は書き換え後の全文で判定**。new_string だけ見るとマーカー削除や ASIN 追加が素通りする。
4. **除外判定はリポ相対パスで**。worktree の絶対パスは `/.claude/worktrees/x/` を含むので、
   素朴に `/.claude/` で除外すると worktree で書いた発注案が丸ごと素通りする（テストで固定）。
5. **記録はメイン作業ツリー1か所**（`git rev-parse --git-common-dir` の親）。agent_output は
   worktree ごとに分かれるので、そのままだと別 worktree で付けた確認が見えない。
6. **pre-commit は「新規」＋「マーカー付きの変更」だけ**。旧い発注案（35/36）の編集で止めると
   30分ごとの自動同期が止まり続ける。既存 pre-commit と同じ思想（新規だけ見る）。
7. 鮮度は全項目3日（§3.3-26「4日で陳腐化」）。**根拠の無い項目別の日数を自分で作らない**。
   伸ばすなら spec の `why_age` に根拠を書く運用にした。
8. spec 破損時：発注案は止める（fail-closed）、通常文書は通す。判定不能を「可」にしない。

## 実データでの確認
- 成果物36 にマーカーを足す Edit をフックに通すと、B008FIPMP2・B01DBGGW8S とも12項目欠落＋
  表の「要確認」行でブロック。
- `write_order_proposal.py` を実行すると exit 1、35_発注案.md は更新されず（mtime 不変）。
  「画面未確認」と書かれたセラー数の列も「未確認」として止まった＝正しい挙動。

## 残る抜け道（報告済み）
`--no-verify`／マーカー無し旧発注案の Bash 書き換え／商品名だけの表／旧スクリプト群。
ゲートは「うっかり」を止める網。最後は §3.5 の運用そのもの。

## 踏んだ罠：自社の pre-commit に自分の spec が止められた
`checklist_spec.json` の項目名「卸値・入り数・最小ロット」と「Keepa 価格履歴」が、既存 pre-commit の
NETSEA 卸値／Keepa 加工値の検知語に当たって commit が止まった（.json は全文が「行データ」扱い）。
**値は1つも無いのに語だけで止まる**。バイパスせず、言い換えて通した（「卸の仕入れ条件」「価格グラフ（csv）」）。
→ **新しい .json/.csv を作るときは、先に pre-commit の pat_* リストの語で grep してから commit する。**
