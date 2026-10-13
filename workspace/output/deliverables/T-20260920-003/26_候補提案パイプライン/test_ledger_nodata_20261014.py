#!/usr/bin/env python3
"""2026-10-14 回帰テスト（タカシ）：「データなし」で台帳の判定理由を消さない。

背景：10/13 18:00、nightly.sh の write_report.py が pipeline/buy_list_private.csv を台帳の全行ダンプ
（4,716行）で上書き → score_20261004 がそれを旧プールとして読み、商品データの無い行を「取り直し」
UNKNOWN にした → ledger_refresh がそれを NO-GO より良い判定として採り、NO-GO 764行と stage B の210行の
理由を消した。

1. score_20261004.POOL は凍結コピーで、行集合が商品データ（RAW）と一致する
2. ledger_refresh.better：データなしの行はデータのある NO-GO に負ける
3. ledger_refresh.keep_when_no_data：データなしの採点で既存の NO-GO 行を上書きしない
4. supplier_screen.ledger_snapshots：dry-run の after を台帳として数えない

実行：python3 test_ledger_nodata_20261014.py （0 で成功）
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger_refresh as L  # noqa: E402
import score_20261004 as S  # noqa: E402
import supplier_screen as SS  # noqa: E402

NG = []


def check(name, cond):
    print(("OK  " if cond else "NG  ") + name)
    if not cond:
        NG.append(name)


# 1. 旧プールの行集合と商品データの供給元が対になっている
check("POOL は pipeline/buy_list_private.csv（毎晩上書きされる）ではない",
      S.POOL.name != "buy_list_private.csv")
pool = {r["ASIN"] for r in csv.DictReader(S.POOL.open(encoding="utf-8-sig"))}
raw = set()
for line in S.RAW.open():
    try:
        raw.add(json.loads(line)["asin"])
    except Exception:
        pass
check(f"旧プール {len(pool)}行が全部 RAW に商品データを持つ", pool <= raw and len(pool) == 648)

nodata = {"asin": "B000000001", "gates": [("取り直し", "UNKNOWN", "…")], "判定": "UNKNOWN"}
nogo = {"asin": "B000000001", "gates": [("価格の動き", "FAIL", "…")], "判定": "NO-GO"}
go = {"asin": "B000000001", "gates": [("価格の動き", "PASS", "…")], "判定": "GO"}

# 2. better
check("データなし UNKNOWN は NO-GO に勝たない（後から来ても）", not L.better(nodata, nogo))
check("NO-GO はデータなし UNKNOWN に勝つ（後から来ても）", L.better(nogo, nodata))
check("データのある同士は従来どおり GO>NO-GO", L.better(go, nogo) and not L.better(nogo, go))
check("最初の1行は採る", L.better(nodata, None))

# 3. keep_when_no_data
row_nogo = {"判定": "NO-GO", "判定理由": "未達：#10 取り分と在庫月数 FAIL：…"}
row_nodata = {"判定": "UNKNOWN", "判定理由": "未達：#13 価格データ UNKNOWN：今日の値を取り直せていません…"}
check("既存 NO-GO 行をデータなしの採点で上書きしない", L.keep_when_no_data(row_nogo, nodata))
check("既存 GO 行も据え置き（10/12 の挙動を保つ）", L.keep_when_no_data({"判定": "GO", "判定理由": ""}, nodata))
check("既存も『取り直し』なら更新してよい", not L.keep_when_no_data(row_nodata, nodata))
check("データがある採点は上書きする", not L.keep_when_no_data(row_nogo, nogo))

# 4. dry-run のスナップショットを台帳として読まない
snaps = SS.ledger_snapshots()
check("ledger_snapshots に dry-run の after が入らない",
      not any(p.name.startswith("after_") and "dry" in p.stem for p in snaps))

print("\n" + ("全部 OK" if not NG else f"NG {len(NG)}件"))
raise SystemExit(1 if NG else 0)
