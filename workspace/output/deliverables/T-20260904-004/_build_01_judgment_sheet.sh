#!/bin/bash
# 01_初回仕入れ判定_買ってはいけないリストと向くカテゴリ.html の生成コマンド（T-20260904-004 / C-2）
#
# 原稿 research/draft.md が唯一の正。HTML は機械変換物なので、原稿を直したらこれを再実行する。
# 手で HTML を編集しないこと（md と HTML が食い違う事故を構造的に防ぐため）。
#
# 検証: python3 workspace/output/agent_output/T-20260904-004/html/verify.py <draft.md> <出力.html>
set -e
cd "$(dirname "$0")/../../../.."

python3 agents/content_creator/skills/md_to_standalone_html.py \
  "workspace/output/deliverables/T-20260904-004/research/draft.md" \
  "workspace/output/deliverables/T-20260904-004/01_初回仕入れ判定_買ってはいけないリストと向くカテゴリ.html" \
  --title "初回仕入れ判定 — 買ってはいけないリスト／初回に向くカテゴリ" \
  --kicker "T-20260904-004 ／ 初回仕入れ判定資料 ／ 2026-09-04" \
  --box "結論=conclusion" \
  --box "1-B. 例外なく買わない（致命的）=danger" \
  --box "2-D. 仕入れ確定前チェックリスト（実務手順）=checklist" \
  --box "3-B. 単一ソースにしか依存していない主張=warn" \
  --box "3-D. この資料の限界=alert" \
  --cellmark "致命的=danger" \
  --cellmark "単一ソース=warn" \
  --cellmark "本文到達不能=info" \
  --cellmark "^未実施=muted" \
  --cellmark "^一致=ok" \
  --cellmark "^部分一致=warn" \
  --cellmark "^不一致=danger" \
  --reftable "出典一覧" \
  --reftable-widths "3em,27%,21%,15%,11%,23%" \
  --note "HTML版。内容の唯一の正は workspace/output/deliverables/T-20260904-004/research/draft.md です。本ファイルは原稿を機械変換したもので、加筆・削除・言い換えはありません。"
