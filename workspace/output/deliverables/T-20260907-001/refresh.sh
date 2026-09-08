#!/bin/bash
# 走行が進むたびに、これ1つを打てば最新の候補リストが出ます。
#   cd workspace/output/deliverables/T-20260907-001 && ./refresh.sh
# T-20260906-003 の out/ は**読むだけ**。走行中のジョブには触れません。
set -euo pipefail
cd "$(dirname "$0")"
python3 -m pytest tests/ -q          # 社長判断と法務判定が壊れていないことを先に確認
python3 reevaluate.py
python3 make_top10.py
