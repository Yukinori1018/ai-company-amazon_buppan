#!/usr/bin/env python3
"""T-20260914-002 推奨案C（と既定内の案B）の12ヶ月月次キャッシュ表 — ハジメの 00_cf_base.py（T-20260914-003）に需要の上限を入れて回す

需要: 01_calc.py が出した 01_demand_paths_{B,C}.json（レーン別月商の P20／中央／P80）。
      各月の分位を並べたもので、1本の経路ではない（シナリオの形を作るための近似）。
発注: reinvest(lane, cap=翌月の需要×原価率, stop_after=…)。予備25万・確定済み未払・翌月固定費を先に引く（ハジメの安全側）。
判定: cum_cash（実質＝月末現金−未払−200万）と thin_cash（≥25万）。窓の外の税は after_window_tax。
"""
import importlib.util, json, pathlib, sys, io, contextlib

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cf", HERE.parent / "T-20260914-003" / "00_cf_base.py")
cf = importlib.util.module_from_spec(spec); spec.loader.exec_module(cf)

PATHS = {k: json.load(open(HERE / f"01_demand_paths_{k}.json")) for k in ("B", "C")}
FIXED = [15_253] + [15_253 + 2_200] * 11          # 段階1＋会計ソフト1,000（二次）＋SD 会費2,200（推測）
LANES = {
    "W": cf.preset("卸_カード", margin=0.11, turnover_m=2),       # 需要先行×卸マルチ（NETSEA・SD・卸問屋.com・国分）
    "M": cf.preset("メーカー直", margin=0.12, turnover_m=2.5),    # Keepa起点メーカー直（本丸B）＋展示会（本丸A）
    "S": cf.preset("電脳せどり", margin=0.09, turnover_m=1.3),   # 電脳せどり（限定再開・社長が目視・カード払い）
}
PLAN_LANES = {"B": ("W", "M"), "C": ("W", "M", "S")}


def caps(plan, ln, pct):
    R = PATHS[plan][ln][pct]                       # 月1..12 の月商
    c = LANES[ln].cost_rate
    nxt = R[1:] + [R[-1]]                    # 発注は翌月の需要に合わせる（リード15〜20日）
    return [c * r for r in nxt]


def run(plan, pct, stop_after=None):
    cfg = cf.Config(fixed_monthly=FIXED)
    pol = cf.combine(*[cf.reinvest(LANES[ln], cap=caps(plan, ln, pct), stop_after=stop_after) for ln in PLAN_LANES[plan]])
    return cf.simulate(cfg, pol)


def main():
    out = io.StringIO()
    names = {"0.2": "悲観（P20）", "0.5": "中央", "0.8": "楽観（P80）"}
    print("# 01_cf 出力 — 推奨案C（W＋M 週10通＋せどり）と既定内の案B（W＋M 週20通）を 00_cf_base.py で月次キャッシュ化", file=out)
    print("", file=out)
    print("## 1. 要約（実質＝月末現金−未払−200万。発注を続ける／月10から発注停止）", file=out)
    print("| 案 | シナリオ | 発注 | 12ヶ月累計キャッシュ（実質） | 12ヶ月累計利益 | 純資産の増加 | 最薄月・日次最低 | 初回入金 | 窓の外の税（2027年分） | 検算 |", file=out)
    print("|---|---|---|---:|---:|---:|---|---|---:|---:|", file=out)
    keep = {}
    for plan in ("C", "B"):
      for pct in ("0.2", "0.5", "0.8"):
        for stop, lab in ((None, "続ける"), (9, "月10から停止")):
            r = run(plan, pct, stop)
            keep[(plan, pct, stop)] = r
            a = r["after_window_tax"]
            tax = (a["income_tax_est"] + a["resident_est"] + a["biz_tax_est"]) if a else 0
            print(f"| 案{plan} | {names[pct]} | {lab} | {cf.yen(r['cum_cash'])} | {cf.yen(r['cum_profit'])} | {cf.yen(r['net_assets_gain'])} "
                  f"| {r['thin_month']}・{cf.yen(r['thin_cash'])} | {r['first_payout']} | {cf.yen(tax)} | {cf.check_identity(r):.0f}円 |", file=out)
    for key, title in ((("C", "0.5", 9), "案C 中央・月10から発注停止（推奨の運用）"), (("C", "0.2", 9), "案C 悲観・月10から発注停止"),
                       (("C", "0.5", None), "案C 中央・発注を続ける"), (("B", "0.5", 9), "案B 中央・月10から発注停止（既定内の代替）")):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cf.print_monthly(keep[key], title)
        print(buf.getvalue(), file=out)
    txt = out.getvalue()
    (HERE / "01_cf_出力.txt").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main()
