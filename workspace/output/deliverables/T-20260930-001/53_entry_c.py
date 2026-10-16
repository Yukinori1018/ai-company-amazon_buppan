"""入口(c)：カートを自己発送（FBM）の出品者が持っている棚でメーカー候補を足し、窓口集めキューの末尾に並べる
（T-20260930-001 / タカシ 2026-10-17）。

なぜ：12_窓口集めキュー.csv は入口(b) の分まで 3,975位で尽きた。
入口(a)＋(b) の Finder 条件のうち、中村本の3基準でも積極条件でもない当社の定数が1本だけ残っていた：
「5a カートが FBA（buyBoxIsFBA=True）」。中村本が求めるのは「FBA 出品者がいる」ことで、カートが FBA であることではない。
同じ条件（売価≥1,500・FBA≥1 かつ新品オファー≥2）で buyBoxIsFBA を外すと 33,600 件、True 側は (a)+(b) の約23,600件、
False 側＝今回の入口(c) は 8,278 件（2026-10-17 02:25 実測・Keepa の概数）。

変えたもの（1変数だけ）：buyBoxIsFBA True → False。他は入口(a)∪(b) と同じ
- 中村本の3基準：本体なし（product の本体365日在庫切れ率≥90% で再判定）・大カテゴリー 50,000位以内・FBA 出品者あり
- 積極条件：monthlySold ≥ 50。売価は (a)∪(b) と同じ ≥1,500円（1,500円未満は手数料負けしやすいので入れない）
- 一次除外・本人カート疑い・規模・上場の判定は 52_entry_b.py（＝30・36・37・51）のものをそのまま使う

予想される癖：カートが自己発送＝メーカー本人の直販ショップがカートを持つ棚が混ざりやすい（層4 が増える）。
層の並びは 1〜3 が先なので、打診順への影響は末尾に寄るだけ。

    python3 53_entry_c.py list                     # Finder 一覧（約95 token）→ raw/order_wideC.json（既取得 ASIN を除く）
    python3 53_entry_c.py fetch --until 04:40      # product を月販の多い順に（1 token/ASIN・中断点から再開）
    python3 53_entry_c.py build --until 05:20 [--dry-run]
    再実行は冪等：キャッシュ済みは0 token、キューに入った社は層の印「（入口c カート自己発送）」で二重に増えない。
    Keepa は他のジョブ（premium_watch.py）と共用なので、取得の前に「必要量＋300」が貯まるまで待つ。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11d_追加候補_入口c.csv / 12e_入口c_落とした行.csv / 12_窓口集めキュー.csv（.bak_entryc_<日時> に退避）/ entry_c_status.json
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("entry_b", HERE / "52_entry_b.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)

M.TAG = "wideC"
M.ORDER = M.keepa_io.RAW / "order_wideC.json"
M.STATUS = M.WORK / "entry_c_status.json"
M.SEL_B = {**M.E["WIDE_A"], "current_NEW_gte": M.PRICE_MIN_B, "buyBoxIsFBA": False}
M.LABEL = "入口(c) カート自己発送・売価1,500以上"
M.ENTRY_MARK = "（入口c カート自己発送）"
M.KNOWN_ORDERS = ("order.json", "order_wideA.json", "order_seller.json", "order_wideB.json")
M.OLD_POOLS = [("order_wideB.json", "wideB")]
M.OUT_CAND, M.OUT_DROP, M.BAK_TAG = "11d_追加候補_入口c.csv", "12e_入口c_落とした行.csv", "entryc"
M.RESERVE = 300

if __name__ == "__main__":
    M.main()
