"""入口(g)：既存の帯の Finder を取り直し、前回の一覧のあとに条件を満たした新しい ASIN からメーカーを足す
（T-20260930-001 / タカシ 2026-10-21 夜間）。

なぜ：12_窓口集めキュー.csv は入口(f)（手持ち product の再判定）で 5,486位まで延びて尽きた。手持ちの product はもう掘り尽くした。
各帯の Finder 一覧は 10/4（a）・10/15（b）・10/17（c）・10/18（d）・10/19（e）に取ったきりで、そのあと月販・カート・本体の
在庫が動いて条件を満たした ASIN は手元に無い。条件は1つも変えず、一覧だけを今日の状態で取り直す。

帯（条件は各入口のファイルと同じ。ここで値を変えない）
  b  … 売価 1,500〜2,199・カート FBA            （52_entry_b.py）
  c  … 売価 ≥1,500・カート自己発送              （53_entry_c.py）
  d  … 売価 1,250〜1,499・カートは問わない        （54_entry_d.py）
  e  … ランク 50,001〜300,000・売価 ≥1,500       （55_entry_e.py --band rank）
  a  … 売価 ≥2,200・カート FBA（入口(a)・最古の 10/4 一覧。秘書の指示の4帯に §3.1 で足した。最後に回す）
  売価 1,000〜1,249（入口(e) price）は入口(f) と同じく入れない（掛けで落ちる：接触候補57社のうち27社が基準NG）

判定（変えていないもの）：56_entry_f.py の build をそのまま使う。手持ちの全 product ＋今回の新規 ASIN を集約し、
  過去の候補ファイル（10・11・11c〜11g）に載った社・既存キュー・既存台帳と同社／同じ代表 ASIN は足さない。
  一次除外（海外ブランド・中国系OEM・大手）・本人カート疑い・規模（gBiz）・上場（37_listed_dedup.listed_mark）も同じ。
  上場の判定は 2026-10-21 に直した（同名別会社の取り違え：トミタ・LOGOS）。詳しくは 37_listed_dedup.listed_mark。

    python3 57_entry_g.py probe                    # 各帯 perPage=50 で totalResults だけ見る（約11 token/帯）
    python3 57_entry_g.py list  [--band b,c,d,e,a]  # 一覧を全件取り、手持ちに無い ASIN → raw/order_wideG.json
    python3 57_entry_g.py fetch --until 04:30      # product（1 token/ASIN・月販の多い帯から・中断点から再開）
    python3 57_entry_g.py build --until 05:00 [--dry-run] [--prefetch]
    再実行は冪等：Finder・product はキャッシュ、キューに入った社は層の印「（入口g 取り直し）」で二重に増えない。キューへは追記のみ。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11h_追加候補_入口g.csv / 12j_入口g_落とした行.csv / 12_窓口集めキュー.csv（.bak_entryg_<日時> に退避）/ entry_g_status.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


F = _mod("entry_f", HERE / "56_entry_f.py")
M, keepa_io = F.M, F.keepa_io
WA = M.E["WIDE_A"]
_noFBA = {k: v for k, v in WA.items() if k != "buyBoxIsFBA"}
BANDS = {  # 各入口のファイルの SEL_B と同じ値（コピー。元を変えたらここも変える）
    "b": {**WA, "current_NEW_gte": 1_500, "current_NEW_lte": 2_199},
    "c": {**WA, "current_NEW_gte": 1_500, "buyBoxIsFBA": False},
    "d": {**_noFBA, "current_NEW_gte": 1_250, "current_NEW_lte": 1_499},
    "e": {**_noFBA, "current_SALES_gte": 50_001, "current_SALES_lte": 300_000, "current_NEW_gte": 1_500},
    "a": dict(WA),
}
TAG = "wideG"
ORDER = keepa_io.RAW / "order_wideG.json"
DAY = datetime.now().strftime("%Y%m%d")

# 56_entry_f の build を入口(g) 用に差し替える
F.STATUS = F.WORK / "entry_g_status.json"
F.LABEL = "入口(g) 帯の取り直し（b・c・d・e rank・a）"
F.ENTRY_MARK = "（入口g 取り直し）"
F.OUT_CAND, F.OUT_DROP, F.BAK_TAG = "11h_追加候補_入口g.csv", "12j_入口g_落とした行.csv", "entryg"
F.POOL = F.POOL + [(TAG, ORDER.name)]
F.PREV = F.PREV + ["11g_追加候補_入口f.csv"]
F.FRESH_NOTE = "未判定（入口g で新しく条件を満たした ASIN の社）"
M.RESERVE = 100  # 秘書の premium_watch.py と共用。取得の前に「必要量＋100」を待つ


def known() -> set[str]:
    out: set[str] = set()
    for p in keepa_io.RAW.glob("order*.json"):
        if p.name != ORDER.name:
            out |= set(json.loads(p.read_text()))
    return out


def cmd_probe(bands: list[str]) -> None:
    res = {}
    for b in bands:
        d = keepa_io.finder({**BANDS[b], "perPage": 50, "page": 0, "sort": [["monthlySold", "desc"]]}, f"wideGprobe{DAY}{b}")
        res[b] = d.get("totalResults")
        print(f"帯 {b}: totalResults {res[b]}", flush=True)
    F.status(probe={"日": DAY, **res}, 残高=keepa_io.tokens_left())


def cmd_list(bands: list[str]) -> None:
    kn = known()
    prev = json.loads(ORDER.read_text()) if ORDER.exists() else []
    seen, out, per = set(prev), list(prev), {}
    for b in bands:
        keepa_io.wait_for(115 + M.RESERVE, log=lambda s: print(s, flush=True))
        got = M.E["_list"](BANDS[b], f"wideG{DAY}{b}")  # タグに日付を入れる＝別の日に取り直せば別キャッシュ
        new = [a for a in got if a not in kn and a not in seen]
        seen |= set(new); out += new
        per[b] = {"一覧": len(got), "手持ちと重複": sum(1 for a in got if a in kn), "新規": len(new)}
        print(f"帯 {b}: 一覧 {len(got)} / 手持ちと重複 {per[b]['手持ちと重複']} / 新規 {len(new)}", flush=True)
        ORDER.write_text(json.dumps(out))  # 帯ごとに書く（途中で止まっても続きから）
    F.status(一覧={"日": DAY, **per}, 新規ASIN=len(out), 残高=keepa_io.tokens_left())


def cmd_fetch(until) -> None:
    order = json.loads(ORDER.read_text())
    n = 0
    for i in range(0, len(order), 100):
        cached = (keepa_io.RAW / f"prod_{TAG}_{i // 100:04d}.json.gz").exists()
        if not cached:
            need = len(order[i:i + 100]) + 5
            if not M.can_spend(need, until):
                print(f"締め切りまでに次の100件を取れないので止める（{i}/{len(order)}）", flush=True)
                break
            keepa_io.wait_for(need + M.RESERVE, log=lambda s: print(s, flush=True))
        keepa_io.products(order[: i + 100], TAG, log=lambda s: print(s, flush=True))
        n = min(i + 100, len(order))
    F.status(product取得済み=n, product未取得=len(order) - n, 残高=keepa_io.tokens_left())
    print(f"product 取得済み {n}/{len(order)}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "list", "fetch", "build"])
    ap.add_argument("--band", default="b,c,d,e,a")
    ap.add_argument("--until", help="HH:MM。これを過ぎる Keepa 取得はしない")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prefetch", action="store_true")
    a = ap.parse_args()
    bands = [x for x in a.band.split(",") if x]
    if a.cmd == "probe":
        cmd_probe(bands)
    elif a.cmd == "list":
        cmd_list(bands)
    elif a.cmd == "fetch":
        cmd_fetch(M.deadline(a.until))
    else:
        F.cmd_build(M.deadline(a.until), a.dry_run, a.prefetch)


if __name__ == "__main__":
    main()
