#!/usr/bin/env python3
"""整合性検査と autofill のテスト。`python3 scripts/sourcing_gate/test_consistency.py`

方針
  - 金額はすべて**架空の合成値**。PUBLIC リポなので実際の卸の取引条件は1つも書かない。
  - 検査ごとに「崩れている行で鳴る」「正しい行で鳴らない」の両方を見る。
    片方だけだと、常に鳴る検査・絶対鳴らない検査が緑のまま通る。
  - §3.3-20「縮退した入力をテストする」：全項目が同じ値／空／1行だけ／セット数不明。
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import consistency as K  # noqa: E402

TODAY = date(2026, 10, 9)
BASE = date(2026, 10, 4)

_fails: list[str] = []
_n = 0


def ok(cond, label: str) -> None:
    global _n
    _n += 1
    if not cond:
        _fails.append(label)
        print(f"  NG  {label}")
    else:
        print(f"  ok  {label}")


def checks(res: K.RowResult) -> set[str]:
    return {f.check for f in res.findings}


# ── 健全な1行（ここから1箇所ずつ壊す）────────────────────────────────────
# 区分 標準7・売価 10,000円・料率15.4% → 手数料 1,694円／FBA 472円／その他固定費 460円
def good_row(**over) -> dict:
    row = {
        "ASIN": "B000000001", "判定": "GO", "等級": "A",
        "販売価格(90日中央値)": "10000", "保守値(90日の下位25%)": "9500",
        "現在価格": "10000", "価格の出どころ": "BuyBox", "価格の判定": "使える",
        "価格の傾き(%/30日)": "+1.0", "価格の振れ幅": "5%",
        "サイズ区分": "標準7", "販売手数料": "1694", "FBA配送代行": "472",
        "その他固定費": "460", "Amazon1個あたり原価(税込)": "5000",
        "Amazon側のセット数(Amazon1個=卸何点か)": "1", "セット数の確度": "確定",
        "1個手残り": "2374", "利益率(%)": "23.7",
        "悲観の手残り": "1500", "悲観の利益率(%)": "15.8",
        "発注点数(Amazon何個)": "10", "発注額(円・税込)": "50000",
        "手残り合計": "23740", "売り切る月数": "3",
        "発注日": "10/20", "着荷の見込み": "10/25", "FBA納品完了の見込み": "11/05",
        "販売開始日": "11/12", "売り切り目標月": "2027-01",
        "季節の窓": "○（通年）", "季節(ランク12ヶ月履歴)": "通年",
        "Amazon本体の有無": "なし", "カートの販売元": "ヨソノセラー（A1XXXXXXXXXX）",
    }
    row.update(over)
    return row


def run(row: dict, wholesale=None) -> K.RowResult:
    return K.check_row(row, today=TODAY, base_date=BASE, wholesale=wholesale)


print("== 健全な行は鳴らない ==")
r = run(good_row())
ok(r.ok and not r.findings, f"所見ゼロ（出たもの: {checks(r)}）")

print("\n== 不変条件 ==")
ok("order_amount" in checks(run(good_row(**{"発注額(円・税込)": "49000"}))),
   "発注額 ≠ 原価 × 点数 を捕まえる")
ok("order_amount" not in checks(run(good_row(**{"発注額(円・税込)": "50001"}))),
   "1円の丸め差は通す")
ok("net_per_unit" in checks(run(good_row(**{"1個手残り": "2000"}))),
   "1個手残りの引き算違いを捕まえる")
ok("net_total" in checks(run(good_row(**{"手残り合計": "20000"}))),
   "手残り合計 ≠ 1個手残り × 点数 を捕まえる")
ok("margin_pct" in checks(run(good_row(**{"利益率(%)": "30.0"}))),
   "利益率の計算違いを捕まえる")

print("\n== 単位ずれ（卸の1点 × セット数）==")
wh_ok = {"卸の1点あたり原価(税込)": "2500", "卸の最小ロット(点)": "10"}
r = run(good_row(**{"Amazon1個あたり原価(税込)": "5000",
                    "Amazon側のセット数(Amazon1個=卸何点か)": "2",
                    "発注額(円・税込)": "50000"}), wholesale=wh_ok)
ok("unit_cost_from_wholesale" not in checks(r), "1点2,500円 × 2点 = 5,000円 は通る")
r = run(good_row(**{"Amazon側のセット数(Amazon1個=卸何点か)": "1"}), wholesale=wh_ok)
ok("unit_cost_from_wholesale" in checks(r),
   "卸1点の値段をそのまま Amazon 1個の原価にしている行を捕まえる（当社が3回踏んだ型）")
r = run(good_row(**{"発注点数(Amazon何個)": "2", "発注額(円・税込)": "10000"}),
        wholesale={"卸の1点あたり原価(税込)": "5000", "卸の最小ロット(点)": "10"})
ok("min_lot" in checks(r), "Amazon 2個 × セット1 = 卸2点 で最小発注数10点に届かないのを捕まえる")

print("\n== 750円の崖（§3.3-23）==")
# 売価700円・小型 → 手数料は一律5%＝35円 → 税込39円
r = run(good_row(**{"販売価格(90日中央値)": "700", "現在価格": "700", "サイズ区分": "小型",
                    "販売手数料": "39", "FBA配送代行": K.F and str(K.F.fba_fee_yen("小型", 700)),
                    "その他固定費": str(round(K.F.other_costs("小型", 3.0).total)),
                    "Amazon1個あたり原価(税込)": "400", "1個手残り": "", "利益率(%)": "",
                    "悲観の手残り": "", "悲観の利益率(%)": "", "等級": "UNKNOWN",
                    "発注点数(Amazon何個)": "", "発注額(円・税込)": "", "手残り合計": ""}))
ok("referral_cliff" not in checks(r), "750円以下で5%（最低30円）なら通る")
r = run(good_row(**{"販売価格(90日中央値)": "700", "現在価格": "700", "販売手数料": "119"}))
ok("referral_cliff" in checks(r), "750円以下なのに15.4%で計算している行を捕まえる")
r = run(good_row(**{"販売手数料": "550"}))
ok("referral_cliff" in checks(r),
   "750円超なのに5%で計算している行を捕まえる（崖の向きが逆）")
r = run(good_row(**{"販売手数料": "1200"}))
ok("referral_cliff" in checks(r), "公式の段のどれにも当たらない料率を捕まえる")

print("\n== 死に帯 ==")
for sell in (751, 900, 1001, 1100):
    r = run(good_row(**{"販売価格(90日中央値)": str(sell), "現在価格": str(sell)}))
    ok("death_band" in checks(r), f"売価 {sell}円 を死に帯として警告する")
for sell in (750, 901, 1000, 1101):
    r = run(good_row(**{"販売価格(90日中央値)": str(sell), "現在価格": str(sell)}))
    ok("death_band" not in checks(r), f"売価 {sell}円 は死に帯ではない")

print("\n== 固定費の再計算 ==")
ok("fba_fee" in checks(run(good_row(**{"FBA配送代行": "222"}))),
   "区分と売価から引き直した FBA 配送代行と合わない行を捕まえる")
ok("other_costs" in checks(run(good_row(**{"その他固定費": "206"}))),
   "その他固定費が引き直した額と合わない行を捕まえる（『固定費206円』は廃止された旧モデル）")
ok("fba_fee" in checks(run(good_row(**{"サイズ区分": "特大99"}))),
   "公式の区分表に無いサイズ区分は番兵で UNKNOWN にする")

print("\n== 90日中央値で計算しているか（§3.3-28）==")
# 現在価格12,000円で採算を組んでしまった行（中央値は10,000円）
r = run(good_row(**{"現在価格": "12000", "1個手残り": "4374", "利益率(%)": "43.7",
                    "手残り合計": "43740"}))
ok("price_basis" in checks(r), "現在価格で採算を計算している行を捕まえる")
r = run(good_row(**{"販売価格(90日中央値)": "", "保守値(90日の下位25%)": ""}))
ok("price_basis" in checks(r), "中央値が空欄なのに採算がある行を捕まえる")
r = run(good_row(**{"現在価格": "12000"}))
ok("price_basis" not in checks(r), "現在価格が違っても、中央値で計算してあれば通す")

print("\n== 番兵（§3.3-17）==")
r = run(good_row(**{"Amazon1個あたり原価(税込)": "500", "1個手残り": "6874",
                    "利益率(%)": "68.7", "発注額(円・税込)": "5000",
                    "手残り合計": "68740"}))
ok("sentinel_cost_ratio" in checks(r) and "sentinel_margin" in checks(r),
   "原価が売価の5%・利益率68.7% の行は番兵2本で UNKNOWN")
ok(all(f.severity == K.SENTINEL for f in r.findings
       if f.check.startswith("sentinel")), "番兵の重さは UNKNOWN")
r = run(good_row(**{"セット数の確度": "食い違い"}))
ok("set_count_undecided" in checks(r),
   "セット数が食い違っているのに採算が計算されている行を捕まえる")
r = run(good_row(**{"セット数の確度": "食い違い", "1個手残り": "", "利益率(%)": "",
                    "Amazon1個あたり原価(税込)": "", "発注額(円・税込)": "",
                    "手残り合計": "", "販売手数料": "", "FBA配送代行": "",
                    "その他固定費": "", "等級": "UNKNOWN", "悲観の手残り": "",
                    "悲観の利益率(%)": "", "発注点数(Amazon何個)": ""}))
ok("set_count_undecided" not in checks(r), "正しく計算を止めている行は鳴らさない")

print("\n== 等級 ==")
# 規定（fba_cost.grade）: 中央・悲観とも「利益率20%以上 **または** 手残り400円以上」なら A。
# good_row の悲観は 1,500円 ＝ 400円を超えるので **A が正しい**。
# ⚠️ CLAUDE.md §3.5 の表には「利益率20%以上」しか書いておらず、OR 条件が落ちている（報告済み）。
def b_row(**over):
    """悲観で割れる行（中央 23.7% / 悲観 3.2%・手残り300円）＝ B が正しい。"""
    base = {"悲観の手残り": "300", "悲観の利益率(%)": "3.2", "等級": "B"}
    base.update(over)
    return good_row(**base)

ok("grade_rule" in checks(run(good_row(**{"等級": "C"}))),
   "中央で黒字なのに C になっている行を捕まえる")
ok("grade_rule" not in checks(run(good_row(**{"等級": "A"}))),
   "悲観の手残りが400円を超える行は A が正しい（率でなく額で通る）")
ok("grade_rule" in checks(run(b_row(**{"等級": "A"}))),
   "悲観で率も額も割れているのに A になっている行を捕まえる")
ok("grade_rule" not in checks(run(b_row())), "正しい等級 B は通す")
ok("grade_rule" in checks(run(good_row(**{"等級": "A", "悲観の手残り": ""}))),
   "根拠の数字が空欄の等級を捕まえる")

print("\n== 日付 ==")
ok("timeline" in checks(run(good_row(**{"販売開始日": "10/22"}))),
   "販売開始が FBA 納品完了より前になっている行を捕まえる")
ok("timeline" in checks(run(good_row(**{"売り切り目標月": "2027-06"}))),
   "売り切りまで6ヶ月を超える行を捕まえる")
ok("timeline" in checks(run(good_row(**{"発注日": "うるう"}))),
   "日付として読めない行を捕まえる")
ok("timeline_stale" in checks(run(good_row(**{"発注日": "10/01"}))),
   "発注日が過去の行を警告する")
ok(all(f.severity == K.WARN for f in run(good_row(**{"発注日": "10/01"})).findings
       if f.check == "timeline_stale"), "発注日が古いだけで採算欄は空にしない")
# 年末年始をまたぐ鎖
r = run(good_row(**{"発注日": "12/28", "着荷の見込み": "01/05",
                    "FBA納品完了の見込み": "01/15", "販売開始日": "01/20",
                    "売り切り目標月": "2027-04"}), )
ok("timeline" not in checks(r), "12/28 → 01/05 をまたぐ鎖を逆順と誤判定しない")

print("\n== 縮退した入力（§3.3-20）==")
empty = {k: "" for k in good_row()}
empty["ASIN"] = "B000000002"
r = run(empty)
ok(r.ok, f"全部空欄の行は NG にしない（入力が無い検査は対象外。出たもの: {checks(r)}）")
same = {k: "1" for k in good_row()}
same["ASIN"] = "B000000003"
r = run(same)
ok(not any(f.check == "death_band" for f in r.findings),
   "全項目が同じ値（1）でも死に帯に化けない")
ok(len(r.findings) > 0, "全項目が同じ値の行は無傷で通さない（算術が合わないはず）")
r = run(good_row(**{"Amazon側のセット数(Amazon1個=卸何点か)": "", "セット数の確度": "不明",
                    "1個手残り": "", "利益率(%)": "", "Amazon1個あたり原価(税込)": "",
                    "販売手数料": "", "FBA配送代行": "", "その他固定費": "",
                    "悲観の手残り": "", "悲観の利益率(%)": "", "等級": "UNKNOWN",
                    "発注点数(Amazon何個)": "", "発注額(円・税込)": "", "手残り合計": ""}))
ok(r.ok, f"セット数が不明で採算を止めている行は NG にしない（出たもの: {checks(r)}）")

print("\n== num() が注記つきの文を数値にしない ==")
ok(K.num("未確定（月販非表示・3ヶ月で仮置き）") is None,
   "「3ヶ月で仮置き」を 3 と読まない（仮置きが確定値に化ける事故を防ぐ）")
ok(K.num("3ヶ月") == 3.0, "「3ヶ月」は読む")
ok(K.num("21,930") == 21930.0 and K.num("68.3%") == 68.3, "カンマと % を読む")
ok(K.num("") is None and K.num(None) is None, "空欄は 0 ではなく None")

print("\n== CSV まるごと：是正は2回目で0行（§3.3-17）==")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    cols = list(good_row())
    rows = [good_row(),                                                 # 健全
            good_row(ASIN="B000000011", **{"発注額(円・税込)": "49000"}),
            good_row(ASIN="B000000012", **{"1個手残り": "9999"}),
            # 死に帯（860円）の行。**算術は全部合わせてある**ので、鳴るのは death_band だけ。
            # 区分 小型・売価860円 → 手数料146円（15.4%）／FBA 222円（1,000円以下の安い列）／
            # その他固定費 63円／原価200円 → 手残り229円・26.6%。悲観で割れるので等級は B。
            good_row(ASIN="B000000013", **{
                "販売価格(90日中央値)": "860", "現在価格": "860",
                "保守値(90日の下位25%)": "820", "サイズ区分": "小型",
                "販売手数料": "146", "FBA配送代行": "222", "その他固定費": "63",
                "Amazon1個あたり原価(税込)": "200", "1個手残り": "229",
                "利益率(%)": "26.6", "悲観の手残り": "100", "悲観の利益率(%)": "12.5",
                "等級": "B", "発注点数(Amazon何個)": "10",
                "発注額(円・税込)": "2000", "手残り合計": "2290"})]
    src = td / "in.csv"
    with src.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    def do(inp: Path, out: Path) -> str:
        p = subprocess.run(
            [sys.executable, str(HERE / "consistency.py"), "fix", str(inp),
             "--out", str(out), "--today", "2026-10-09", "--base-date", "2026-10-04"],
            capture_output=True, text=True)
        return p.stdout

    o1, o2, o3 = td / "p1.csv", td / "p2.csv", td / "p3.csv"
    s1, s2 = do(src, o1), do(o1, o2)
    s3 = do(o2, o3)
    ok("書き換えた行: 4行" in s1, f"1回目は4行を書き換える（{[l for l in s1.splitlines() if '書き換えた' in l]}）")
    ok("書き換えた行: 0行" in s2, f"2回目は0行（{[l for l in s2.splitlines() if '書き換えた' in l]}）")
    ok("書き換えた行: 0行" in s3, "3回目も0行")
    ok(o1.read_bytes() == o2.read_bytes() == o3.read_bytes(), "2回目・3回目の出力はバイト一致")

    fixed = list(csv.DictReader(o1.open(encoding="utf-8-sig")))
    bad = {r["ASIN"]: r for r in fixed}
    ok(bad["B000000011"]["整合性検査"].startswith("NG"), "壊した行に NG の印が付く")
    ok(bad["B000000011"]["1個手残り"] == "" and bad["B000000011"]["等級"] == "UNKNOWN",
       "NG 行の採算欄は空・等級は UNKNOWN（数字を黙って直さない）")
    ok(bad["B000000011"]["販売価格(90日中央値)"] == "10000",
       "売価は消さない（なぜ落ちたかが読めなくなる）")
    ok(bad["B000000013"]["整合性検査"].startswith("WARN")
       and bad["B000000013"]["1個手残り"] != "",
       "死に帯は WARN だけで、採算欄は消さない")
    ok(bad["B000000001"]["整合性検査"] == "OK", "健全な行は OK")

    # 空の CSV（ヘッダだけ）と1行だけの CSV
    only_head = td / "head.csv"
    only_head.write_text(",".join(cols) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(HERE / "consistency.py"), "check", str(only_head),
                        "--today", "2026-10-09"], capture_output=True, text=True)
    ok(p.returncode == 0 and "母集団 0行" in p.stdout, "ヘッダだけの CSV で落ちない")
    one = td / "one.csv"
    with one.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow(good_row())
    p = subprocess.run([sys.executable, str(HERE / "consistency.py"), "check", str(one),
                        "--today", "2026-10-09", "--base-date", "2026-10-04"],
                       capture_output=True, text=True)
    ok(p.returncode == 0 and "母集団 1行" in p.stdout, "1行だけの CSV で落ちない")

    # 列が足りない CSV（別のパイプラインが作った表）
    thin = td / "thin.csv"
    thin.write_text("ASIN,商品名\nB000000099,なにか\n", encoding="utf-8")
    p = subprocess.run([sys.executable, str(HERE / "consistency.py"), "check", str(thin),
                        "--today", "2026-10-09"], capture_output=True, text=True)
    ok(p.returncode == 0, "採算の列が無い CSV を NG にしない（検査できないものは対象外）")

print("\n== autofill：人の記録を機械が上書きしない ==")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    env = dict(os.environ, SOURCING_CHECKS_DIR=str(td / "checks"))
    cols = list(good_row())
    src = td / "in.csv"
    with src.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow(good_row())

    def rec_cmd(*args):
        return subprocess.run([sys.executable, str(HERE / "check_record.py"), *args],
                              capture_output=True, text=True, env=env)

    def auto(*args):
        return subprocess.run([sys.executable, str(HERE / "autofill.py"), str(src),
                               "--today", "2026-10-09", "--base-date", "2026-10-04", *args],
                              capture_output=True, text=True, env=env)

    # 人が1項目を先に記録する
    r = rec_cmd("set", "B000000001", "actual_sales", "--value", "キーゾン3か月 33個",
                "--result", "PASS", "--source", "キーゾン画面", "--by", "owner")
    ok(r.returncode == 0, "人の記録を先に入れる")
    p = auto()
    ok(p.returncode == 0, f"autofill が走る（{p.stderr[-200:]}）")
    rec = json.loads((td / "checks" / "B000000001.json").read_text(encoding="utf-8"))
    ok(rec["items"]["actual_sales"]["checked_by"] == "owner",
       "🔴 人が付けた記録を機械が上書きしない")
    ok(rec["items"]["actual_sales"]["value"] == "キーゾン3か月 33個", "人の値がそのまま残る")
    ok(rec["items"]["price_median90"]["result"] == "PASS"
       and rec["items"]["price_median90"]["checked_by"] == "autofill",
       "machine 項目は autofill が PASS で埋める")
    ok(rec["items"]["gate_type"]["result"] == "UNKNOWN", "human 項目は UNKNOWN のまま")
    ok("取り方" in rec["items"]["gate_type"].get("note", ""),
       "UNKNOWN には理由と取り方を書く（空欄で埋めない）")
    ok(rec["items"]["buybox_seller"]["result"] == "UNKNOWN",
       "partial：本体でなくても UNKNOWN（メーカー本人かは人が見る）")
    ok(rec["consistency"]["result"] == "OK", "整合性検査の結果も記録に書く")

    # 2回目は何も書かない（冪等）
    before = (td / "checks" / "B000000001.json").read_bytes()
    auto()
    ok((td / "checks" / "B000000001.json").read_bytes() == before,
       "autofill の2回目は記録を書き換えない")

    # カート保持者が Amazon 本体なら機械で FAIL
    src2 = td / "in2.csv"
    with src2.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerow(good_row(ASIN="B000000004", **{"カートの販売元": "Amazon.co.jp"}))
    subprocess.run([sys.executable, str(HERE / "autofill.py"), str(src2),
                    "--today", "2026-10-09", "--base-date", "2026-10-04"],
                   capture_output=True, text=True, env=env)
    rec = json.loads((td / "checks" / "B000000004.json").read_text(encoding="utf-8"))
    ok(rec["items"]["buybox_seller"]["result"] == "FAIL",
       "カート保持者が Amazon 本体なら機械で FAIL（§3.3-1）")

print("\n== 発注ゲートが整合性検査 NG で止まる ==")
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    cd = td / "checks"
    cd.mkdir()
    os.environ["SOURCING_CHECKS_DIR"] = str(cd)
    for m in ("gate", "consistency"):
        sys.modules.pop(m, None)
    import gate  # noqa: E402

    spec = gate.load_spec()
    full = {it["id"]: {"value": "確認済み", "result": "PASS", "source": "テスト",
                       "checked_at": TODAY.isoformat(), "checked_by": "owner"}
            for it in spec}
    (cd / "B000000005.json").write_text(
        json.dumps({"asin": "B000000005", "items": full}, ensure_ascii=False),
        encoding="utf-8")
    r = gate.evaluate("B000000005", today=TODAY, spec=spec)
    ok(r.ok, f"21項目が全部 PASS なら通る（{[p.reason for p in r.problems]}）")

    (cd / "B000000005.json").write_text(
        json.dumps({"asin": "B000000005", "items": full,
                    "consistency": {"result": "NG", "detail": "[net_per_unit] 引き算が合わない",
                                    "checked_at": TODAY.isoformat(), "checked_by": "autofill"}},
                   ensure_ascii=False), encoding="utf-8")
    r = gate.evaluate("B000000005", today=TODAY, spec=spec)
    ok(not r.ok and any(p.item_id == "consistency" for p in r.problems),
       "🔴 21項目が全部 PASS でも、整合性検査 NG なら発注させない")

    doc = ("<!-- order-asins: B000000005 -->\n# 発注案\n\n"
           "| ASIN | 等級 |\n|---|---|\n| B000000005 | A |\n")
    msgs = gate.check_document("workspace/output/deliverables/T-X/99_発注案.md", doc, today=TODAY)
    ok(msgs and any("整合性検査" in m for m in msgs),
       "発注案の文書判定でも整合性検査 NG が理由に出る")

    (cd / "B000000005.json").write_text(
        json.dumps({"asin": "B000000005", "items": full,
                    "consistency": {"result": "WARN", "detail": "[death_band] 死に帯",
                                    "checked_at": TODAY.isoformat(), "checked_by": "autofill"}},
                   ensure_ascii=False), encoding="utf-8")
    r = gate.evaluate("B000000005", today=TODAY, spec=spec)
    ok(r.ok, "WARN では止めない")

print("\n== spec の仕分けが21項目ぶん揃っている ==")
sys.modules.pop("gate", None)
os.environ.pop("SOURCING_CHECKS_DIR", None)
import gate as G  # noqa: E402
sp = G.load_spec()
ok(len(sp) == 21, f"項目は21件（{len(sp)}件）")
ok(all(it.get("decidable") in ("machine", "partial", "human") for it in sp),
   "全項目に decidable が付いている")
ok(all(len(it.get("decidable_why", "")) > 10 for it in sp),
   "全項目に仕分けの根拠が1行ある")

print(f"\n{'=' * 60}")
print(f"{_n - len(_fails)}/{_n} 件 通過" + (f"  失敗: {_fails}" if _fails else "  （全件通過）"))
sys.exit(1 if _fails else 0)
