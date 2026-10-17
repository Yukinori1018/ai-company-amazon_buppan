"""入口(d)：売価 1,250〜1,499円の帯でメーカー候補を足し、窓口集めキューの末尾に並べる
（T-20260930-001 / タカシ 2026-10-18）。

なぜ：12_窓口集めキュー.csv は入口(c) の分まで 4,581位で尽きる。

10/17 に提案した「カート保持セラー起点（50_expand.py の sellers）」はやめた。
入口(a)∪(b) がカート FBA、(c) がカート自己発送で、売価≥1,500 の帯は同じ条件のもとで両側とも取り尽くしている。
セラーで絞っても条件が同じなら a∪b∪c の部分集合にしかならず、新しい社は「一覧を取ったあとに状態が変わった棚」しか来ない。
母数を延ばすには、条件のどれか1つを動かすしかない。

動かせる条件で、中村本の3基準でも積極条件でもない当社の定数は「売価の下限 1,500円」だけが残っている
（CLAUDE.md §3.3-27「実践者は単価の下限を置かない」）。第1弾の基準5は 10/16 から「売価≥2,200円」ではなく
「利益率5%に必要な掛け≥40%」なので、売価の下限は第1弾の入り口ではもう効いていない。
40_採算列.csv の実績（2026-10-18 集計）で掛け≥40% を満たす割合は、平時売価 1,250〜1,499円 で 25/30（83%）、
1,000〜1,249円 で 2/5（40%）。そこで下限を 1,250円まで下げる。1,000〜1,249円は次の帯（同じファイルの値を替えるだけ）。

変えたもの（1変数だけ）：売価の帯を 1,250〜1,499円 に。カートの FBA／自己発送は問わない（(a)(b) と (c) の和）。
- 中村本の3基準：本体なし（本体365日在庫切れ率≥90% で再判定）・大カテゴリー 50,000位以内・FBA 出品者あり
- 積極条件：monthlySold ≥ 50
- 一次除外・本人カート疑い・規模・上場の判定は 52_entry_b.py（＝30・36・37・51）のものをそのまま使う

    python3 54_entry_d.py list                     # Finder 一覧 → raw/order_wideD.json（既取得 ASIN を除く）
    python3 54_entry_d.py fetch --until 06:30      # product を月販の多い順に（1 token/ASIN・中断点から再開）
    python3 54_entry_d.py build --until 07:30 [--dry-run]
    再実行は冪等：キャッシュ済みは0 token、キューに入った社は層の印「（入口d 売価1,250〜1,499）」で二重に増えない。
    キューへは追記のみ（既存行は書き換えない）。Keepa は premium_watch.py と共用なので「必要量＋300」を待つ。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11e_追加候補_入口d.csv / 12f_入口d_落とした行.csv / 12_窓口集めキュー.csv（.bak_entryd_<日時> に退避）/ entry_d_status.json
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("entry_b", HERE / "52_entry_b.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

LO, HI = 1_250, 1_499
M.TAG = "wideD"
M.ORDER = M.keepa_io.RAW / "order_wideD.json"
M.STATUS = M.WORK / "entry_d_status.json"
M.PRICE_MIN_B = LO  # build の再判定「売価 ≥ 下限」に使われる
M.SEL_B = {**{k: v for k, v in M.E["WIDE_A"].items() if k != "buyBoxIsFBA"},
           "current_NEW_gte": LO, "current_NEW_lte": HI}
M.LABEL = "入口(d) 売価1,250〜1,499"
M.ENTRY_MARK = "（入口d 売価1,250〜1,499）"
M.KNOWN_ORDERS = ("order.json", "order_wideA.json", "order_seller.json", "order_wideB.json", "order_wideC.json")
M.OLD_POOLS = [("order_wideB.json", "wideB"), ("order_wideC.json", "wideC")]
M.OUT_CAND, M.OUT_DROP, M.BAK_TAG = "11e_追加候補_入口d.csv", "12f_入口d_落とした行.csv", "entryd"
M.RESERVE = 300

if __name__ == "__main__":
    M.main()
