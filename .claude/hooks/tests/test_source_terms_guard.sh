#!/bin/bash
# source-terms-guard.py（PreToolUse）と .githooks/pre-commit の回帰テスト。
#   bash .claude/hooks/tests/test_source_terms_guard.sh
#
# **このファイルに実額を書かないこと。** 数値はすべて架空（実在の卸値・送料・手数料ではない）。
# 実データでテストすると、テストコード自体が漏えい経路になる。
set -u
HOOKS="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$HOOKS/../.." && pwd)"
GUARD="$HOOKS/source-terms-guard.py"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
FAIL=0
ok() { echo "ok   - $1"; }
ng() { echo "FAIL - $1"; FAIL=1; }

# 台帳（公開区分に架空ホストを1つ入れて、出口が開くことを確かめる）
mkdir -p "$T/workspace"
cat > "$T/workspace/source-ledger.md" <<'EOF'
SOURCE: スーパーデリバリー | 会員限定 | 一般的発信禁止型 | 会員規約 17条1項 | 2026-09-20
SOURCE: example-maker.co.jp | 公開 | 発信禁止条項なし | https://example-maker.co.jp/terms | 2026-09-21
EOF

# Write ツールの PreToolUse ペイロードを組んで走らせ、終了コードを返す
run() { # $1=相対パス $2=本文
  python3 - "$1" "$2" <<'PY' > "$T/payload.json"
import json, sys
print(json.dumps({"tool_name": "Write",
                  "tool_input": {"file_path": sys.argv[1], "content": sys.argv[2]}}))
PY
  CLAUDE_PROJECT_DIR="$T" python3 "$GUARD" < "$T/payload.json" 2>"$T/err"; echo $?
}
D="$T/workspace/output/deliverables/T-99999999-001/01_x.md"

block() { # 陽性: 止まるべき
  local rc; rc="$(run "$2" "$3")"
  if [ "$rc" = "2" ]; then ok "$1"; else ng "$1（exit=$rc）"; fi
}
pass() { # 陰性: 通すべき
  local rc; rc="$(run "$2" "$3")"
  if [ "$rc" = "0" ]; then ok "$1"; else ng "$1（exit=$rc / $(head -c 200 "$T/err")）"; fi
}

echo "== 陽性（2026-09-21 に実際に漏れた4種。数値は架空）=="
block "① 地の文の卸値の実額"        "$D" '中央値ケースの卸値は 1,234 円（税抜）でした。'
block "② 卸値の分布表（4列）"        "$D" '| 最小 | 25%点 | 中央 | 75%点 |
|---|---|---|---|
| 卸値 | 111 | 222 | 333 |'
block "③ 決済手数料の実額"          "$D" '代引手数料は 987 円が上乗せされます。'
block "④ 送料無料ライン（漢数字）"   "$D" '九万円以上で送料無料になります。'
block "④' 送料無料ライン（混在）"    "$D" '9万円以上で送料が無料。'
block "④'' 送料無料ライン（カンマ）" "$D" '99,999円以上で送料無料。'
block "④''' カンマなし"             "$D" '99999円以上で送料無料。'
block "全角数字の上代"              "$D" '上代は１２３４円です。'
block "ロットの実数"                "$D" '最小ロットは 6 本からです。'
block "SD 品番"                     "$D" 'SD品番 99999999 で特定できます。'
block "チケット本文も対象"          "$T/workspace/tickets/doing/T-99999999-001_x.md" '卸単価 1,111 円で仕入れます。'

echo "== 陰性（止めてはいけない4種）=="
pass "① 件数（ASIN・バリエーション・商標）" "$D" 'ASIN は 120件、バリエーションは 8件、商標の保有件数は 3件です。'
pass "② Amazon の売価・手数料（公開情報）"   "$D" 'Amazon 売価 1,980円、販売手数料 297円、FBA 配送代行手数料 434円。'
pass "③ 卸率（%）での記述"                   "$D" '卸率55%以下は12点、全40点のうち3割でした。'
pass "④ 検索語を code で引用"                "$D" '検索は `卸値` `上代` `送料無料ライン` の3語で行う。'
pass "率だけの結論"                          "$D" '卸率が高く、必要倍率に届かないため黒字になりません。'
pass "伏せ字済みの行"                        "$D" '送料無料ラインは〔一定額以上〕（実額は非公開）。'
pass "実額は agent_output なら可"            "$T/workspace/output/agent_output/T-99999999-001/raw.md" '卸値 1,234 円'
pass "法務判定書は対象外"                    "$T/workspace/output/deliverables/T-99999999-001/16_法務判定.md" '卸値 1,234 円が残存。'
pass "小さな数字だけの表（件数表）"          "$D" '| 区分 | 件数 |
|---|---|
| 候補 | 12 |
| 除外 | 8 |'
pass "公開ページ由来の出口（台帳の公開区分）" "$D" '<!-- public-source: https://example-maker.co.jp/terms verified:2026-09-21 -->
上代は 1,234 円と自社サイトに掲載されています。'
pass "台帳に無いホストの注記は出口にならない…はず→陽性側で確認"  "$D" '率だけ'
block "台帳に無いホストでは出口は開かない" "$D" '<!-- public-source: https://not-in-ledger.example/terms verified:2026-09-21 -->
上代は 1,234 円。'

echo "== カズヨの抜き打ち10ケース（2026-09-21。うち3件は実装が落とした形。数値は架空）=="
block "抜1 送料の言い換え（送料無料と書いていない・漢数字）" "$D" '初回ロットを税抜9万円以上で組めば仕入送料は0円。'
block "抜1' 同（タダ／かからない）"       "$D" '税抜9万円以上ならば送料はかからない。'
block "抜2 卸の実額（税抜＝税込の併記）"   "$D" '卸 税抜999円＝税込1,098円で計算。'
block "抜3 卸値の分布表（数字だけの4列）"  "$D" '| 最小 | 25%点 | 中央 | 75%点 |
|---|---|---|---|
| 卸値 | 111 | 222 | 333 |'
block "抜4 代引手数料の実額"               "$D" '代引手数料は 987 円が上乗せされます。'
block "抜7 卸価格の分布（〔〕で囲っても中身が実額）" "$D" '卸価格の分布〔最小111円〜中央222円〜最大333円〕。'
block "抜8 上代の実額"                     "$D" '上代は 1,234 円です。'
pass  "抜5 卸率・Amazon の売価と手数料・商標の件数" "$D" '卸率55%以下は12点。Amazon 売価 1,980円、販売手数料 297円。商標の保有件数は 3件。'
pass  "抜6 agent_output なら実額可"        "$T/workspace/output/agent_output/T-99999999-001/raw.md" '卸 税抜999円＝税込1,098円。9万円以上で送料無料。'
block "抜9 丁寧形の否定＋純漢数字"        "$D" '九万円を超えるご発注なら運賃はかかりません。'
block "抜9' 同（頂戴しません／不要です）"  "$D" '九万円以上なら発送料は頂戴しません。'
pass  "抜10 送料無料でも閾値が無ければ通す（Amazon の公開情報）" "$D" 'Amazon 売価 1,980円、配送料は無料です。'
pass  "「手数料がかかります」を無料と誤読しない" "$D" '9万円以上の発注でも送料はかかります。'

echo "== 落ちない・誤爆しない =="
pass "空の本文"            "$D" ''
pass "リポ外のパス"        "$T/somewhere/else.md" '卸値 1,234 円'
rc="$(printf 'not json' | CLAUDE_PROJECT_DIR="$T" python3 "$GUARD" 2>/dev/null; echo $?)"
[ "$rc" = "0" ] && ok "壊れた入力でも通す" || ng "壊れた入力でも通す（exit=$rc）"
rc="$(printf '{"tool_name":"Read","tool_input":{"file_path":"x"}}' | CLAUDE_PROJECT_DIR="$T" python3 "$GUARD" 2>/dev/null; echo $?)"
[ "$rc" = "0" ] && ok "Read は対象外" || ng "Read は対象外（exit=$rc）"
rc="$(run "$D" '卸値 1,234 円')"; grep -q "agent_output" "$T/err" && ok "メッセージに退避先が出る" || ng "メッセージに退避先が出る"
grep -q "16_公開リポに残る取引条件" "$T/err" && ok "メッセージに法務判定のパスが出る" || ng "法務判定のパスが出る"
grep -q "no-verify\|バイパス" "$T/err" && ng "バイパス手段を書いていない" || ok "バイパス手段を書いていない"

# =============================================================================
echo "== pre-commit（依頼2: 月間販売数＝A クラスに合わせる）=="
G="$T/git"; mkdir -p "$G"; cd "$G" || exit 1
git init -q .; git config user.email t@example.com; git config user.name t
mkdir -p .githooks; cp "$REPO/.githooks/pre-commit" .githooks/; git config core.hooksPath .githooks
mkdir -p workspace/output/deliverables/T-99999999-001
commit() { # $1=ファイル名 $2=中身 → pre-commit の終了コード
  local p="workspace/output/deliverables/T-99999999-001/$1"
  printf '%s' "$2" > "$p"
  git add -f "$p" >/dev/null 2>&1
  git -c core.hooksPath=.githooks commit -q -m x >/dev/null 2>"$T/gerr"; local rc=$?
  # 後片付け。`git clean -fd` は使わないこと — 未追跡の .githooks/ ごと消えて、
  # 2回目以降フックが動かなくなる（最初にこれで全部「通った」ように見えた）。
  git reset -q --hard >/dev/null 2>&1; rm -f "$p"
  echo $rc
}
c_pass() { local rc; rc="$(commit "$2" "$3")"; [ "$rc" = "0" ] && ok "$1" || ng "$1（exit=$rc / $(grep -o '【.*' "$T/gerr" | head -1)）"; }
c_block() { local rc; rc="$(commit "$2" "$3")"; [ "$rc" != "0" ] && ok "$1" || ng "$1（通ってしまった）"; }

c_pass  "月間販売数（A クラス）は通る"      a1.csv 'asin,商品名,月間販売数,現在価格
B000000001,テスト,100,1980'
c_pass  "monthlySold は通る"                a2.csv 'asin,monthlySold,price
B000000001,100,1980'
c_pass  "monthly_sold は通る"               a3.csv 'asin,monthly_sold,price
B000000001,100,1980'
# monthly_sold_real は 2026-09-21 にハルオが A クラスで確定（monthlySold の素通し・推計なし）。
# 条件は「複数時点で並べない」「取得日を併記する」の2つ。
c_pass  "monthly_sold_real 単体（A クラス・取得日つき）" a4.csv 'asin,monthly_sold_real,main_rank,取得日
B000000001,100,5000,2026-09-21'
c_block "monthly_sold_real に日付が付いたら B へ戻る" b6.csv 'asin,monthly_sold_real_20260921,monthly_sold_real_20260820
B000000001,100,90'
c_block "同（全角カッコの日付）"              b7.csv 'asin,monthly_sold_real（2026-09）,現在価格
B000000001,100,1980'
c_pass  "main_rank 単体（現在ランク＝A）"     a5.csv 'asin,main_rank,現在価格,取得日
B000000001,5000,1980,2026-09-21'
c_block "想定月販（B クラス）は止まる"      b2.csv 'asin,想定月販,ドロップ数
B000000001,120,14'
c_block "時系列（日付つき列名）は止まる"    b3.csv 'asin,月間販売数（2026-09）,月間販売数（2026-08）
B000000001,100,90'
c_block "monthlySold_YYYYMMDD も止まる"     b4.csv 'asin,monthlySold_20260921,monthlySold_20260820
B000000001,100,90'
c_block "上代（C クラス）は止まる"          c1.csv 'jan,上代,卸率
4900000000001,1980,55'
c_block "SD品番（C クラス）は止まる"        c2.csv 'SD品番,商品名,数量
99999999,テスト,6'
c_block "送料無料ライン（C クラス）は止まる" c3.csv '項目,値
送料無料ライン,99999'
c_block "90日平均（B クラス）は止まる"      b5.csv 'asin,90日平均,在庫切れ率
B000000001,1980,12'
c_pass  "解説の散文は通る（従来どおり）"    d1.md '# 用語
月間販売数は Amazon の商品ページに表示される購入点数です。上代や卸値は会員限定です。'

cd / || exit 1
exit $FAIL
