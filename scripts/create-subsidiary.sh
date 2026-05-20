#!/usr/bin/env bash
# ============================================================================
# create-subsidiary.sh
#
# ai-company-template から子会社リポジトリをワンコマンドで生成するスクリプト。
#
# 流れ:
#   A. GitHub テンプレートから新規リポジトリ作成（gh repo create --template）
#   B. ~/Claude Code/<repo>/ に clone
#   C. プレースホルダー一括置換（事業名・ミッション・KPI・主力商品・想定顧客）
#   D. Notion カンバン DB 作成（docs/notion-board-schema.md 準拠）
#   E. .mcp.json 生成（NOTION_API_KEY / NOTION_DATABASE_ID 埋め込み、git 対象外）
#   F. 最終納品物フォルダ作成（~/Documents/AI Company Outputs/<事業名>/）
#   G. 初期コミット & push
#   H. 動作確認チェックリスト出力
#
# 詳細: scripts/README.md
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. 定数 / グローバル
# ---------------------------------------------------------------------------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "${SCRIPT_DIR}/.." && pwd )"

# このテンプレートの識別情報を git remote から実行時判定（別名クローンでも動くため）
_origin_url="$(cd "$REPO_ROOT" && git remote get-url origin 2>/dev/null || true)"
if [ -n "$_origin_url" ]; then
  # owner/repo を抽出（git@github.com:OWNER/REPO.git, https://github.com/OWNER/REPO[.git] 両対応）
  TEMPLATE_REPO="$(echo "$_origin_url" | sed -E 's#\.git$##' | awk -F'[:/]' 'NF>=2 {print $(NF-1)"/"$NF}')"
else
  TEMPLATE_REPO="$(whoami)/$(basename "$REPO_ROOT")"
fi
TEMPLATE_REPO_NAME="$(basename "$TEMPLATE_REPO")"
unset _origin_url

# 共有設定パス。テンプレ／子会社のどのリポから実行しても同じ場所を参照する。
# （リポ名から動的生成すると、子会社リポから create-subsidiary.sh を再実行した時に
#  再設定を求められてしまう。共有を維持するため固定値にしている。）
CONFIG_FILE="${HOME}/.config/ai-company-template/config.env"
CLONE_PARENT="${HOME}/Claude Code"
OUTPUT_PARENT="${HOME}/Documents/AI Company Outputs"
NOTION_VERSION="2022-06-28"
SCHEMA_JSON="${SCRIPT_DIR}/notion-db-schema.json"

# 入力（引数 or 対話）
REPO_NAME=""
BUSINESS_NAME=""
MISSION=""
KPI=""
PRODUCTS=""
CUSTOMERS=""
VISIBILITY="--private"
DRY_RUN=0

# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------
log()   { printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"; }
ok()    { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
err()   { printf '\033[1;31m[ERR]\033[0m %s\n' "$*" >&2; }
die()   { err "$*"; exit 1; }

run() {
  # --dry-run のときは echo のみ、それ以外は実行
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m %s\n' "$*"
  else
    eval "$@"
  fi
}

usage() {
  cat <<EOF
Usage: create-subsidiary.sh [OPTIONS]

${TEMPLATE_REPO_NAME} から子会社リポジトリを生成し、Notion DB / .mcp.json /
最終納品物フォルダまで一括セットアップします。

OPTIONS:
  --repo <name>              リポジトリ名（kebab-case 推奨。例: amazon-merchandise）
  --business-name <text>     事業名（例: Amazon物販事業）
  --mission <text>           ミッション
  --kpi <text>               最重要KPI
  --products <text>          主力商品/サービス
  --customers <text>         想定顧客
  --private                  リポジトリを private で作成（デフォルト）
  --public                   リポジトリを public で作成
  --dry-run                  副作用を伴う処理を実行せず、計画のみ表示
  -h, --help                 このヘルプ

引数を省略した項目は対話的に入力を求められます。

事前準備:
  1. gh, jq, curl, git をインストール
  2. gh auth login で GitHub 認証
  3. ~/.config/ai-company-template/config.env を作成
     （雛形: scripts/config.env.example）

例:
  scripts/create-subsidiary.sh \
    --repo amazon-merchandise \
    --business-name "Amazon物販事業" \
    --mission "国内未進出のニッチ良品を発掘・販売し、月商800万を達成する" \
    --kpi "月商800万円、利益率20%以上、SKU数100" \
    --products "アジア圏のセレクト雑貨" \
    --customers "30〜45歳女性" \
    --private

詳細: scripts/README.md
EOF
}

# ---------------------------------------------------------------------------
# 1. 引数パース
# ---------------------------------------------------------------------------
parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --repo)           REPO_NAME="$2"; shift 2 ;;
      --business-name)  BUSINESS_NAME="$2"; shift 2 ;;
      --mission)        MISSION="$2"; shift 2 ;;
      --kpi)            KPI="$2"; shift 2 ;;
      --products)       PRODUCTS="$2"; shift 2 ;;
      --customers)      CUSTOMERS="$2"; shift 2 ;;
      --private)        VISIBILITY="--private"; shift ;;
      --public)         VISIBILITY="--public"; shift ;;
      --dry-run)        DRY_RUN=1; shift ;;
      -h|--help)        usage; exit 0 ;;
      *) die "Unknown option: $1 (--help でヘルプ表示)" ;;
    esac
  done
}

prompt_if_empty() {
  # $1 = 変数名, $2 = プロンプト文言
  local var="$1"
  local label="$2"
  local current
  eval "current=\${$var}"
  if [ -z "$current" ]; then
    printf '%s: ' "$label" >&2
    IFS= read -r value
    [ -z "$value" ] && die "$label が空です"
    eval "$var=\$value"
  fi
}

collect_inputs() {
  prompt_if_empty REPO_NAME       "リポジトリ名 (kebab-case 例: amazon-merchandise)"
  prompt_if_empty BUSINESS_NAME   "事業名 (例: Amazon物販事業)"
  prompt_if_empty MISSION         "ミッション"
  prompt_if_empty KPI             "最重要KPI"
  prompt_if_empty PRODUCTS        "主力商品/サービス"
  prompt_if_empty CUSTOMERS       "想定顧客"

  # 簡易バリデーション
  case "$REPO_NAME" in
    *' '*|*'/'*|*'\\'*) die "リポジトリ名に空白や / は使えません: $REPO_NAME" ;;
  esac
}

# ---------------------------------------------------------------------------
# 2. 前提チェック
# ---------------------------------------------------------------------------
preflight() {
  log "前提チェック..."
  for cmd in gh jq curl git sed; do
    command -v "$cmd" >/dev/null 2>&1 \
      || die "$cmd が見つかりません。インストールしてください（gh と jq は brew install gh jq）"
  done

  gh auth status >/dev/null 2>&1 \
    || die "gh の認証が未完了です。'gh auth login' を実行してください"

  [ -f "$SCHEMA_JSON" ] \
    || die "スキーマ JSON が見つかりません: $SCHEMA_JSON"

  ok "コマンド類 / gh 認証 OK"
}

load_config() {
  log "設定読込: $CONFIG_FILE"
  if [ ! -f "$CONFIG_FILE" ]; then
    cat <<EOF >&2
[ERR] 設定ファイルがありません: $CONFIG_FILE

初期化手順:
  mkdir -p ~/.config/ai-company-template
  cp scripts/config.env.example ~/.config/ai-company-template/config.env
  chmod 600 ~/.config/ai-company-template/config.env
  \$EDITOR ~/.config/ai-company-template/config.env

詳細: scripts/README.md
EOF
    exit 1
  fi

  # shellcheck disable=SC1090
  set -a; . "$CONFIG_FILE"; set +a

  [ -n "${NOTION_API_KEY:-}" ]        || die "config.env: NOTION_API_KEY が空"
  [ -n "${NOTION_PARENT_PAGE_ID:-}" ] || die "config.env: NOTION_PARENT_PAGE_ID が空"

  if [ -z "${GITHUB_OWNER:-}" ]; then
    GITHUB_OWNER="$(gh api user --jq .login)"
    log "GITHUB_OWNER を gh から取得: $GITHUB_OWNER"
  fi

  ok "設定読込 OK (owner=$GITHUB_OWNER)"
}

# ---------------------------------------------------------------------------
# 3. 計画表示
# ---------------------------------------------------------------------------
show_plan() {
  cat <<EOF

────────────────────────────────────────────────────────────────
 子会社セットアップ計画
────────────────────────────────────────────────────────────────
  リポジトリ        : ${GITHUB_OWNER}/${REPO_NAME}   (${VISIBILITY})
  テンプレート元    : ${TEMPLATE_REPO}
  clone 先          : ${CLONE_PARENT}/${REPO_NAME}
  事業名            : ${BUSINESS_NAME}
  ミッション        : ${MISSION}
  最重要KPI         : ${KPI}
  主力商品/サービス : ${PRODUCTS}
  想定顧客          : ${CUSTOMERS}
  Notion 親ページ   : ${NOTION_PARENT_PAGE_ID}
  最終納品物フォルダ: ${OUTPUT_PARENT}/${BUSINESS_NAME}
  モード            : $([ "$DRY_RUN" -eq 1 ] && echo "DRY-RUN (副作用なし)" || echo "実行")
────────────────────────────────────────────────────────────────

EOF
}

# ---------------------------------------------------------------------------
# Step A: GitHub repo 作成
# ---------------------------------------------------------------------------
step_create_repo() {
  log "Step A: GitHub リポジトリ作成"
  local desc
  desc="${BUSINESS_NAME} — ${TEMPLATE_REPO_NAME} から生成"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m gh repo create %s/%s --template %s %s --description "%s"\n' \
      "$GITHUB_OWNER" "$REPO_NAME" "$TEMPLATE_REPO" "$VISIBILITY" "$desc"
  else
    gh repo create "${GITHUB_OWNER}/${REPO_NAME}" \
      --template "$TEMPLATE_REPO" \
      "$VISIBILITY" \
      --description "$desc"

    # `gh repo create --template` は非同期。テンプレファイルが新リポに
    # コピーされるまで待たないと、後続の clone が空リポとして失敗する。
    log "  テンプレファイル populate を待機中..."
    local attempts=0
    until gh api "repos/${GITHUB_OWNER}/${REPO_NAME}/contents/CLAUDE.md" --silent 2>/dev/null; do
      attempts=$((attempts + 1))
      if [ "$attempts" -gt 30 ]; then
        die "template populate がタイムアウト (60s)。GitHub 側を確認してください: https://github.com/${GITHUB_OWNER}/${REPO_NAME}"
      fi
      sleep 2
    done
  fi
  ok "Step A 完了"
}

# ---------------------------------------------------------------------------
# Step B: clone
# ---------------------------------------------------------------------------
step_clone() {
  log "Step B: clone"
  local dest="${CLONE_PARENT}/${REPO_NAME}"
  if [ -e "$dest" ]; then
    die "clone 先が既に存在: $dest （別名を使うか、既存を削除してください）"
  fi
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m mkdir -p "%s"\n' "$CLONE_PARENT"
    printf '\033[1;35m[DRY]\033[0m (cd "%s" && gh repo clone %s/%s)\n' \
      "$CLONE_PARENT" "$GITHUB_OWNER" "$REPO_NAME"
  else
    mkdir -p "$CLONE_PARENT"
    ( cd "$CLONE_PARENT" && gh repo clone "${GITHUB_OWNER}/${REPO_NAME}" )
  fi
  ok "Step B 完了: $dest"
}

# ---------------------------------------------------------------------------
# Step C: プレースホルダー置換
# ---------------------------------------------------------------------------
# macOS sed の特殊文字エスケープ（区切り文字 | を使うので | と & と \ を逃がす）
sed_escape() {
  printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'
}

step_replace_placeholders() {
  log "Step C: プレースホルダー置換"
  local dest="${CLONE_PARENT}/${REPO_NAME}"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m find %s -type f \\( -name "*.md" -o -name "*.json*" \\) で対象列挙し、以下を置換:\n' "$dest"
    printf '         {{ 事業名 }}            -> %s\n' "$BUSINESS_NAME"
    printf '         {{ ミッション }}        -> %s\n' "$MISSION"
    printf '         {{ 最重要KPI }}         -> %s\n' "$KPI"
    printf '         {{ 主力商品/サービス }} -> %s\n' "$PRODUCTS"
    printf '         {{ 想定顧客 }}          -> %s\n' "$CUSTOMERS"
    printf '         ※ {{ チケットタイトル }} は runtime のため置換しない\n'
    printf '         ※ {{ NOTION_API_KEY }} / {{ NOTION_DATABASE_ID }} は Step E で\n'
    ok "Step C 完了 (dry-run)"
    return
  fi

  local b m k p c
  b="$(sed_escape "$BUSINESS_NAME")"
  m="$(sed_escape "$MISSION")"
  k="$(sed_escape "$KPI")"
  p="$(sed_escape "$PRODUCTS")"
  c="$(sed_escape "$CUSTOMERS")"

  # 対象ファイル列挙（.git と docs/reference は除外）
  # NUL 区切りで読み、ファイル名の特殊文字に安全
  find "$dest" -type f \( -name "*.md" -o -name "*.json" -o -name "*.json.example" \) \
       -not -path "*/.git/*" \
       -not -path "*/docs/reference/*" \
       -print0 \
  | while IFS= read -r -d '' f; do
      sed -i '' \
        -e "s|{{ 事業名 }}|${b}|g" \
        -e "s|{{ ミッション }}|${m}|g" \
        -e "s|{{ 最重要KPI }}|${k}|g" \
        -e "s|{{ 主力商品/サービス }}|${p}|g" \
        -e "s|{{ 想定顧客 }}|${c}|g" \
        "$f"
    done

  ok "Step C 完了"
}

# ---------------------------------------------------------------------------
# Step D: Notion DB 作成
# ---------------------------------------------------------------------------
step_create_notion_db() {
  log "Step D: Notion DB 作成"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m POST https://api.notion.com/v1/databases (parent=%s, title="%s Tickets")\n' \
      "$NOTION_PARENT_PAGE_ID" "$BUSINESS_NAME"
    printf '\033[1;35m[DRY]\033[0m properties: %s より読み込み\n' "$SCHEMA_JSON"
    NOTION_DATABASE_ID="DRYRUN_DATABASE_ID_0000000000000000"
    NOTION_DATABASE_URL="https://www.notion.so/DRYRUN"
    ok "Step D 完了 (dry-run, dummy id)"
    return
  fi

  local payload tmpfile resp_file http
  tmpfile="$(mktemp)"
  resp_file="$(mktemp)"
  payload="$(jq -n \
    --arg parent "$NOTION_PARENT_PAGE_ID" \
    --arg title  "${BUSINESS_NAME} Tickets" \
    --slurpfile props "$SCHEMA_JSON" \
    '{
      parent:     { type: "page_id", page_id: $parent },
      title:      [ { type: "text", text: { content: $title } } ],
      properties: $props[0]
    }')"
  printf '%s' "$payload" > "$tmpfile"

  http=$(curl -sS -o "$resp_file" -w '%{http_code}' \
    -X POST https://api.notion.com/v1/databases \
    -H "Authorization: Bearer ${NOTION_API_KEY}" \
    -H "Notion-Version: ${NOTION_VERSION}" \
    -H "Content-Type: application/json" \
    --data @"$tmpfile")

  if [ "$http" != "200" ]; then
    err "Notion API エラー (HTTP $http)"
    echo "---- request ----" >&2
    cat "$tmpfile" >&2
    echo >&2
    echo "---- response ----" >&2
    cat "$resp_file" >&2
    rm -f "$tmpfile" "$resp_file"
    die "Notion DB 作成失敗。よくある原因: 親ページに Integration が Connect されていない / NOTION_PARENT_PAGE_ID が違う"
  fi

  NOTION_DATABASE_ID="$(jq -r '.id' < "$resp_file" | tr -d '-')"
  NOTION_DATABASE_URL="$(jq -r '.url' < "$resp_file")"
  rm -f "$tmpfile" "$resp_file"

  [ -n "$NOTION_DATABASE_ID" ] && [ "$NOTION_DATABASE_ID" != "null" ] \
    || die "Notion DB ID の取得に失敗"

  ok "Step D 完了 (database_id=$NOTION_DATABASE_ID)"
}

# ---------------------------------------------------------------------------
# Step E: .mcp.json 生成
# ---------------------------------------------------------------------------
step_generate_mcp_json() {
  log "Step E: .mcp.json 生成"
  local dest="${CLONE_PARENT}/${REPO_NAME}"
  local src="${dest}/.mcp.json.example"
  local out="${dest}/.mcp.json"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m cp %s %s\n' "$src" "$out"
    printf '\033[1;35m[DRY]\033[0m sed で {{ NOTION_API_KEY }} と {{ NOTION_DATABASE_ID }} を埋め込み\n'
    ok "Step E 完了 (dry-run)"
    return
  fi

  [ -f "$src" ] || die ".mcp.json.example が見つかりません: $src"
  cp "$src" "$out"

  local key db
  key="$(sed_escape "$NOTION_API_KEY")"
  db="$(sed_escape "$NOTION_DATABASE_ID")"
  sed -i '' \
    -e "s|{{ NOTION_API_KEY }}|${key}|g" \
    -e "s|{{ NOTION_DATABASE_ID }}|${db}|g" \
    "$out"

  chmod 600 "$out" || true
  ok "Step E 完了: $out (gitignore 対象)"
}

# ---------------------------------------------------------------------------
# Step F: 最終納品物フォルダ
# ---------------------------------------------------------------------------
step_make_output_dir() {
  log "Step F: 最終納品物フォルダ作成"
  local d="${OUTPUT_PARENT}/${BUSINESS_NAME}"
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m mkdir -p "%s"\n' "$d"
  else
    mkdir -p "$d"
  fi
  ok "Step F 完了: $d"
}

# ---------------------------------------------------------------------------
# Step G: 初期コミット & push
# ---------------------------------------------------------------------------
step_commit_and_push() {
  log "Step G: プレースホルダー埋め込み結果をコミット & push"
  local dest="${CLONE_PARENT}/${REPO_NAME}"

  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\033[1;35m[DRY]\033[0m (cd %s && git add -A && git commit && git push)\n' "$dest"
    ok "Step G 完了 (dry-run)"
    return
  fi

  (
    cd "$dest"
    git add -A
    if git diff --cached --quiet; then
      warn "コミット対象の差分がありません（置換結果なし？）"
    else
      git commit -m "chore: initialize subsidiary (${BUSINESS_NAME})

${TEMPLATE_REPO_NAME} から create-subsidiary.sh で生成:
- プレースホルダーを実値で置換
- Notion カンバン DB を作成し .mcp.json に紐付け（.mcp.json は gitignore）
- 最終納品物フォルダ ~/Documents/AI Company Outputs/${BUSINESS_NAME}/ を作成"
      git push
    fi
  )
  ok "Step G 完了"
}

# ---------------------------------------------------------------------------
# Step H: 動作確認チェックリスト
# ---------------------------------------------------------------------------
step_print_checklist() {
  local dest="${CLONE_PARENT}/${REPO_NAME}"
  cat <<EOF

╔══════════════════════════════════════════════════════════════╗
║  セットアップ完了。次にやること                              ║
╚══════════════════════════════════════════════════════════════╝

  1) cd "${dest}"

  2) Claude Code を起動
       claude

  3) 動作確認（4テスト）
       a. 「自己紹介してください」と頼む → カズヨが名乗ればOK
       b. 「テスト用チケットを起票してください」
          → workspace/tickets/todo/ にファイルができ、
            Notion カンバンの "todo" 列にカードが追加されればOK
       c. 「そのチケットを doing に進めてください」
          → ファイルが doing/ に移動し、Notion 側のカラムも更新
       d. 「外部にメール送信したい」と頼む
          → §4.1 該当として waiting/ に出し承認を求めればOK

  4) Notion カンバン URL:
       ${NOTION_DATABASE_URL:-(dry-run のため未取得)}

  5) 最終納品物の置き場（Finder でブックマーク推奨）:
       ${OUTPUT_PARENT}/${BUSINESS_NAME}/

  6) GitHub:
       https://github.com/${GITHUB_OWNER}/${REPO_NAME}

トラブル時は scripts/README.md / docs/subsidiary-onboarding.md を参照。
EOF
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
  parse_args "$@"
  preflight
  load_config
  collect_inputs
  show_plan

  if [ "$DRY_RUN" -ne 1 ]; then
    printf '上記の内容で実行します。よろしいですか？ [y/N]: '
    IFS= read -r ans
    case "$ans" in
      y|Y|yes|YES) ;;
      *) die "中止しました" ;;
    esac
  fi

  step_create_repo
  step_clone
  step_replace_placeholders
  step_create_notion_db
  step_generate_mcp_json
  step_make_output_dir
  step_commit_and_push
  step_print_checklist
}

main "$@"
