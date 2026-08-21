#!/bin/bash
#
# deploy.sh — Satoy Select サイトを Cloudflare Pages へ公開する（T-20260817-006）
#
#   ./deploy.sh            … 事前チェックだけ実行（公開しない）※既定
#   ./deploy.sh --deploy   … チェックに全部通ったときだけ実際に公開する
#
# 既定を「チェックのみ」にしてあるのは、うっかり実行で公開されるのを防ぐため。
# 公開は §4.1（外部発信）に該当するため、社長の指示があるまで --deploy は付けない。
#
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PUB="$HERE/公開用"
DIST="$HERE/会社概要_配布用"
PROJECT="satoy-select"
export PATH="$HOME/.npm-global/bin:$PATH"

DO_DEPLOY=0
[ "${1:-}" = "--deploy" ] && DO_DEPLOY=1

fail=0
ng() { printf '  ✗ %s\n' "$*"; fail=1; }
ok() { printf '  ✓ %s\n' "$*"; }

echo "=============================================="
echo " Satoy Select — 公開前チェック"
echo "=============================================="

# 1) 公開用フォルダがあるか
if [ ! -d "$PUB" ]; then
  echo "  ✗ 「公開用」フォルダがありません。先に site/fill.py を実行してください。"
  exit 1
fi
ok "「公開用」フォルダあり"

# 2) 埋め残し（{{ }}）が無いか
left="$(grep -rlo '{{[A-Z_]*}}' "$PUB" 2>/dev/null || true)"
if [ -n "$left" ]; then ng "未置換の {{ }} が残っています:"; echo "$left" | sed 's/^/      /'
else ok "未置換の {{ }} は 0件"; fi

# 3) 会社概要（配布専用）が公開用に混ざっていないか ── 最重要
for leak in "profile.html" "Satoy-Select_会社概要.pdf"; do
  if [ -e "$PUB/$leak" ]; then ng "$leak が「公開用」に入っています。アップロードすると誰でも読めます"
  else ok "$leak は「公開用」に無い"; fi
done

# 4) メールアドレスが公開用に露出していないか（決定③：メールは非公開）
mails="$(grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$PUB" 2>/dev/null | sort -u || true)"
if [ -n "$mails" ]; then ng "メールアドレスが公開用に含まれています:"; echo "$mails" | sed 's/^/      /'
else ok "公開用にメールアドレスなし"; fi

# 5) 404 とサイトマップ
[ -f "$PUB/404.html" ] && ok "404.html あり" || ng "404.html がありません"
[ -f "$PUB/sitemap.xml" ] && ok "sitemap.xml あり" || ng "sitemap.xml がありません"
if [ -f "$PUB/sitemap.xml" ] && grep -q '{{' "$PUB/sitemap.xml"; then ng "sitemap.xml にドメインが入っていません"; fi

# 6) 配布用フォルダの所在を案内
[ -d "$DIST" ] && echo "  ℹ 会社概要（メーカー手渡し用）: $DIST ← ここはアップロードしません"

echo "----------------------------------------------"
if [ $fail -ne 0 ]; then
  echo " 結果: ✗ 公開できません。上の ✗ を直してから再実行してください。"
  exit 1
fi
echo " 結果: ✓ すべて通過"

if [ $DO_DEPLOY -eq 0 ]; then
  echo
  echo " （チェックのみ実行しました。公開はしていません）"
  echo " 公開するには: ./deploy.sh --deploy"
  exit 0
fi

command -v wrangler >/dev/null || { echo " ✗ wrangler が見つかりません（npm i -g wrangler）"; exit 1; }
wrangler whoami </dev/null 2>&1 | grep -q "not authenticated" && {
  echo " ✗ Cloudflare にログインしていません。先に  wrangler login  を実行してください。"; exit 1; }

echo
echo " Cloudflare Pages へ公開します（プロジェクト: $PROJECT）…"
wrangler pages deploy "$PUB" --project-name "$PROJECT"
