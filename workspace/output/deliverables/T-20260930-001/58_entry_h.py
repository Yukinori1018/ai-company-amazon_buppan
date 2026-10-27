"""入口(h)：入口(a)〜(g) が一度も通していない「売価×ランク」の升目から ASIN を取り、メーカーを足す
（T-20260930-001 / タカシ 2026-10-24 夜間）。

なぜ：12_窓口集めキュー.csv は入口(g)（既存の帯の取り直し）で 5,924位まで延びて尽きた。b〜e・a の帯は 10/21 に取り直し済みで、
3日では差分が小さい。そこで「升目」を見た。既存の入口が通した売価×ランク（Finder 段・build 段とも）は次の和集合：
  ランク ≤5万 × 売価 ≥1,000（a・b・c・d・e price）／ランク 5万〜30万 × 売価 ≥1,500（e rank）
空いている升目（monthlySold ≥50 の基準は同じ）：
  h1 … ランク 50,001〜300,000 × 売価 1,250〜1,499（d の売価帯を e のランク帯へ）
  h2 … ランク 300,001〜500,000 × 売価 ≥1,250   （§3.3-8：50万位より下は NO-GO・その間は UNKNOWN。月販≥50 で生存は確認済み）
売価 1,000〜1,249 は入口(f)(g) と同じく足さない（掛けで落ちる：入口(e) price の接触候補57社のうち27社が基準NG）。
50万位より下は §3.3-8 で NO-GO なので入れない。

判定（変えていないもの）：56_entry_f.py の build をそのまま使う。月販≥50・本体の365日在庫切れ率≥90%・FBA 出品者の条件・
  除外ルート・一次除外（maker_rules.classify）・本人カート疑い・Amazon 本体カートの除外・規模（gBiz）・上場（37_listed_dedup）。
  過去の候補ファイル（10・11・11c〜11h）に載った社・既存キュー・既存台帳と同社／同じ代表 ASIN は足さない。
変えたもの：build 段の売価×ランク＝「ランク ≤50万 × 売価 ≥1,250」（既存の和集合から売価1,000〜1,249 を除き、h1・h2 を足したもの）。
  手持ちの product にもこの升目に入る ASIN があるので、それも判定する（入口(f) と同じ考え方）。

    python3 58_entry_h.py probe                     # 各帯 perPage=50 で totalResults だけ見る（約11 token/帯）
    python3 58_entry_h.py list  [--band h1,h2]       # 一覧を全件取り、手持ちに無い ASIN → raw/order_wideH.json
    python3 58_entry_h.py fetch --until 05:30       # product（1 token/ASIN・中断点から再開）
    python3 58_entry_h.py build --until 06:00 [--dry-run] [--prefetch]
    再実行は冪等：Finder・product はキャッシュ、キューに入った社は層の印「（入口h）」で二重に増えない。キューへは追記のみ。

  2回目以降の差分（2026-10-25 追加）：  python3 58_entry_h.py <cmd> --round 2 --band gb,gc,gd,ge,ga,u,x,h1
    --round N（N≥2）は一覧・product・出力・status を別名（order_wideH{N}.json・prod_wideH{N}_*・11i{N}_・12k{N}_・
    entry_h{N}_status.json）に分ける。なぜ：同じ order に追記すると、product のキャッシュが100件単位のファイルなので
    最後の端数ファイル（10/24 は 3,100〜3,164 の65件）に後から足した ASIN が「取得済み」と見なされ、黙って取りこぼす。
    前の回の order は「手持ち」（known）に入るので、差分は前の回にも無い ASIN だけになる。前の回の 11i は PREV に入る。
  🔴 4回目以降（2026-10-27 追記）：ga は使わず --band gb,gc,gd,ge,ga1,ga2a,ga2b,u,x,h1。Finder は1回10,000件までで、
    降順＋昇順の和集合は効いていなかった（ga2 totalResults 10,900 → 一覧 10,000）。帯は 10,000 件未満に割る。
    帯を足すときは fetch の前に list を追加で回す（fetch 後に order へ足すと端数キャッシュで取りこぼす）。

出力（agent_output/T-20260930-001/・Keepa 加工値を含むので Git 除外）
  11i_追加候補_入口h.csv / 12k_入口h_落とした行.csv / 12_窓口集めキュー.csv（.bak_entryh_<日時> に退避）/ entry_h_status.json
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
_noFBA = {k: v for k, v in M.E["WIDE_A"].items() if k != "buyBoxIsFBA"}  # 入口(d)(e) と同じくカートは問わない
_any = {k: v for k, v in _noFBA.items() if k != "current_NEW_gte"}           # WIDE_A の売価下限 2,200 を外したもの
_WA = M.E["WIDE_A"]
BANDS = {
    # 空き升目（2026-10-24 02時 probe の totalResults：h1 72・h2 0・u 887・x 138）
    "h1": {**_noFBA, "current_SALES_gte": 50_001, "current_SALES_lte": 300_000,
           "current_NEW_gte": 1_250, "current_NEW_lte": 1_499},
    "h2": {**_noFBA, "current_SALES_gte": 300_001, "current_SALES_lte": 500_000, "current_NEW_gte": 1_250},
    # u … カートが「資格なし」の棚。既存の入口は全部 Finder で buyBoxIsUnqualified=False を掛けていたが、build の基準には無い条件
    "u": {**_noFBA, "buyBoxIsUnqualified": True, "current_SALES_gte": 1, "current_SALES_lte": 500_000, "current_NEW_gte": 1_250},
    # x … 新品最安は 1,249 以下だがカート価格（送料込み）は 1,250 以上。既存の入口は Finder を新品最安で切っていたが build はカート価格で判定する
    "x": {**_any, "current_SALES_gte": 1, "current_SALES_lte": 500_000, "current_NEW_lte": 1_249,
          "current_BUY_BOX_SHIPPING_gte": 1_250},
    # 差分 … 入口(g) と同じ5帯（57_entry_g.BANDS のコピー）を今日の状態で取り直し、10/21 の一覧に無かった ASIN だけ足す
    "gb": {**_WA, "current_NEW_gte": 1_500, "current_NEW_lte": 2_199},
    "gc": {**_WA, "current_NEW_gte": 1_500, "buyBoxIsFBA": False},
    "gd": {**_noFBA, "current_NEW_gte": 1_250, "current_NEW_lte": 1_499},
    "ge": {**_noFBA, "current_SALES_gte": 50_001, "current_SALES_lte": 300_000, "current_NEW_gte": 1_500},
    "ga": dict(_WA),
    # ga を売価で2つに割ったもの（2026-10-27 追加）。ga の一覧が Finder の上限 20,000 件（降順・昇順の和集合）を
    # 超えたら、ga の代わりにこの2本を使う。境目は probe の totalResults で半々に近い所（実測 GA_SPLIT）
    "ga1": {**_WA, "current_NEW_lte": 3_499},
    "ga2": {**_WA, "current_NEW_gte": 3_500},
    # 🔴 2026-10-27 実測：降順＋昇順の和集合は効いていない（ga2 totalResults 10,900 → 一覧 10,000 ちょうど・
    # ga も 19,900 → 19,041）。1帯 10,000 件未満に割らないと取りこぼす。ga2 をさらに2つに割ったもの
    "ga2a": {**_WA, "current_NEW_gte": 3_500, "current_NEW_lte": 5_499},
    "ga2b": {**_WA, "current_NEW_gte": 5_500},
}
TAG = "wideH"
ORDER = keepa_io.RAW / "order_wideH.json"
DAY = datetime.now().strftime("%Y%m%d")


def rank_price_ok(f: dict) -> bool:
    r, p = f["rank"], f["price"]
    return r is not None and p is not None and r <= 500_000 and p >= 1_250


# 56_entry_f の build を入口(h) 用に差し替える
F.STATUS = F.WORK / "entry_h_status.json"
F.LABEL = "入口(h) 空き升目（h1 ランク5万〜30万×売価1,250〜1,499／h2 ランク30万〜50万／u カート資格なし／x カート価格≥1,250・最安<1,250）＋10/21 一覧との差分"
F.ENTRY_MARK = "（入口h）"
F.OUT_CAND, F.OUT_DROP, F.BAK_TAG = "11i_追加候補_入口h.csv", "12k_入口h_落とした行.csv", "entryh"
F.POOL = F.POOL + [("wideG", "order_wideG.json"), (TAG, ORDER.name)]
F.PREV = F.PREV + ["11g_追加候補_入口f.csv", "11h_追加候補_入口g.csv"]
F.FRESH_NOTE = "未判定（入口h の升目・差分で条件を満たした社）"
F.RANK_PRICE_LABEL = "4・6 ランク≤50万×売価≥1,250（既存の升目＋入口h の h1・h2）"
F.rank_price_ok = rank_price_ok
M.RESERVE = 300  # 6b の機械の段が並行で Keepa を使う。残高 300 を切らない


def known() -> set[str]:
    out: set[str] = set()
    for p in keepa_io.RAW.glob("order*.json"):
        if p.name != ORDER.name:
            out |= set(json.loads(p.read_text()))
    return out


def cmd_probe(bands: list[str]) -> None:
    res = {}
    for b in bands:
        keepa_io.wait_for(15 + M.RESERVE, log=lambda s: print(s, flush=True))
        d = keepa_io.finder({**BANDS[b], "perPage": 50, "page": 0, "sort": [["monthlySold", "desc"]]}, f"wideHprobe{DAY}{b}")
        res[b] = d.get("totalResults")
        print(f"帯 {b}: totalResults {res[b]}", flush=True)
    F.status(probe={"日": DAY, **res}, 残高=keepa_io.tokens_left())


def cmd_list(bands: list[str]) -> None:
    kn = known()
    prev = json.loads(ORDER.read_text()) if ORDER.exists() else []
    seen, out, per = set(prev), list(prev), {}
    for b in bands:
        keepa_io.wait_for(115 + M.RESERVE, log=lambda s: print(s, flush=True))
        got = M.E["_list"](BANDS[b], f"wideH{DAY}{b}")
        new = [a for a in got if a not in kn and a not in seen]
        seen |= set(new); out += new
        per[b] = {"一覧": len(got), "手持ちと重複": sum(1 for a in got if a in kn), "新規": len(new)}
        print(f"帯 {b}: 一覧 {len(got)} / 手持ちと重複 {per[b]['手持ちと重複']} / 新規 {len(new)}", flush=True)
        ORDER.write_text(json.dumps(out))
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


def use_round(n: int) -> None:
    """--round N（N≥2）：前の回と別のファイルに分ける（docstring 参照）。層の印は「（入口h）」のまま＝同じ入口の追加。"""
    global TAG, ORDER
    if n < 2:
        return
    TAG = f"wideH{n}"
    ORDER = keepa_io.RAW / f"order_{TAG}.json"
    F.STATUS = F.WORK / f"entry_h{n}_status.json"
    F.OUT_CAND, F.OUT_DROP, F.BAK_TAG = f"11i{n}_追加候補_入口h.csv", f"12k{n}_入口h_落とした行.csv", f"entryh{n}"
    prev_rounds = [("wideH", "order_wideH.json")] + [(f"wideH{k}", f"order_wideH{k}.json") for k in range(2, n)]
    F.POOL = [x for x in F.POOL if x[0] != "wideH"] + prev_rounds + [(TAG, ORDER.name)]
    F.PREV = F.PREV + ["11i_追加候補_入口h.csv"] + [f"11i{k}_追加候補_入口h.csv" for k in range(2, n)]
    F.LABEL = F.LABEL + f"（{n}回目の差分・{DAY}）"
    F.FRESH_NOTE = f"未判定（入口h {n}回目の差分で条件を満たした社）"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["probe", "list", "fetch", "build"])
    ap.add_argument("--band", default="h1,h2,u,x,gb,gc,gd,ge,ga")
    ap.add_argument("--until", help="HH:MM。これを過ぎる Keepa 取得はしない")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prefetch", action="store_true")
    ap.add_argument("--round", type=int, default=1, help="2以上で前の回と別ファイルに分けて差分を取る")
    a = ap.parse_args()
    use_round(a.round)
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
