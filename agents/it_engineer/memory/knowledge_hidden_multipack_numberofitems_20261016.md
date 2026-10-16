---
name: knowledge-hidden-multipack-numberofitems-20261016
description: 商品名に数が無い「40g」の商品が実は5袋セットだった。numberOfItems>=2 を捨てると原価を1/Nに見る（B0FF9HRRYD・2026-10-16）
metadata:
  type: knowledge
---

# 商品名に数が無いセット品（T-20260920-003・2026-10-16）

## 何が起きたか
- B0FF9HRRYD（あじげん オニポテスナック うすしお味 40g）を台帳は「Amazon1個＝卸1点（商品名だけが読めました）」で採算 36.8% と出していた
- カズヨ実画面：「袋あたり￥296」＝5袋セット。カートもメーカー公式店。セット数5で引き直すと中央値 -361円/個・-24.4%（C）
- Keepa には最初から答えがあった：numberOfItems=5・unitCount {unitValue 5, unitType 袋, eachUnitCount 1}・size「40g×5パック」・features「内容量：40g×5袋」。packageQuantity は -1
- `set_family.resolve` は numberOfItems を「1 が既定値で入る」理由で参考扱いにし、商品名の 1 で SINGLE を返していた

## 直し方
- 商品名=1（数なし）かつ packageQuantity なし かつ numberOfItems>=2 → UNREADABLE（人が見る）。numberOfItems=1 は従来どおり無視
- 安全側（UNKNOWN）に倒すだけなので候補は落とさない。dry-run で判定が変わった行0・理由文が変わった行1

## 人の確認を台帳へ書く手順（再利用）
1. シートの該当行を直接更新し、確認者を「カズヨ（…）」だけにする（"タカシ" を含めない）→ `is_human` が凍結する
2. 同じ内容を証跡ファイルにも置く：`cart_maker_flags_<日付>_human.csv`（区分=確定）・`set_check_<日付>_human.csv`（確度 高）。ファイル名の日付が既存より後であること（後勝ち）
3. `RUN_TAG=xxx ledger_refresh.py --dry-run` → `after_dryrun.json` で当該行が据え置きか、判定件数の前後を比較
4. 採算は `fba_cost.grade(売価, 原価×N, 区分, keepa_pct=, sell_worst=)` で出し直す（推測で書かない）
5. 注意：dry-run でも go_list_/track_record_list_/extra_go_<日付>.csv は書き直される

## 検算のやり方（セット数の決め打ち探し）
- 台帳の 発注額÷発注点数 ＝ Amazon1個原価(税込)。NETSEA 索引の unit_price_excl×1.1 で割ると実際に使った倍率が出る
- Keepa の numberOfItems / unitCount / size に「×N」があるのに倍率1の行が要注意。入り数（6枚入など）と束ね（×5袋）は機械では区別できない
