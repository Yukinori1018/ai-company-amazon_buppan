"""recalc_buybox.py の出力層。数え上げと out/07_修正後候補.csv / .html。

★このファイルに金額・Keepa加工値を書かない（PUBLIC）。数字は実行時に out/ へだけ出る。

並べ順は「最小ロットの回転月数が短い順」（同点は利益率）。社長ルール3
「手残り・粗利で順位付けしない」に合わせる。利益率順にすると終売品が上に来る
（knowledge_discontinued_bias_in_margin_ranking）。
"""
import csv, html, statistics
from pathlib import Path

TOP_N = 30
UNRESOLVED_LABEL = "入数が解けない"


def _best_by_asin(items):
    """同一 ASIN が複数行（仕入先違い）あれば、修正後の利益率が高い行を1本残す。"""
    best = {}
    for x in items:
        cur = best.get(x["asin"])
        if cur is None or (x["m_after"] or -9) > (cur["m_after"] or -9):
            best[x["asin"]] = x
    return list(best.values())


def _judge(r, R, cache):
    """1行を3通り（従来／成約料0だけ／成約料0＋カート価格）で計算する。"""
    lo = r["fact"].get("price_yen")
    m0, ev0 = R.margin_at(r, R.BEFORE, lo)
    m1, ev1 = R.margin_at(r, R.AFTER, lo)
    price, src = R.price_after(r, cache)
    m2, ev2 = R.margin_at(r, R.AFTER, price)
    return {"asin": r["asin"], "r": r, "lo": lo, "price": price, "src": src,
            "m_before": m0, "m_fee0": m1, "m_after": m2,
            "net_before": ev0.result.net_profit if ev0.result else None,
            "net_after": ev2.result.net_profit if ev2.result else None,
            "review_after": bool(ev2.review_reason), "review_before": bool(ev0.review_reason),
            "ev": ev2}


def _final(x, key):
    m = x[key]
    review = x["review_after"] if key == "m_after" else x["review_before"]
    return m is not None and m >= 0.05 and not review and not x["r"]["why"]


def write(recs, passed, verified, cache, targets, R):
    out = R.OUT
    # ── 母集団：②③通過・入数解決・選定条件OK（価格・回転・予算はまだ問わない）──
    pop = [r for r in recs if r["passed"] and r.get("sel") is not None
           and not any(w.startswith(("選定除外", UNRESOLVED_LABEL, "Amazon未出品")) for w in r["why"])]
    xs = _best_by_asin([_judge(r, R, cache) for r in pop])

    def cnt(f):
        return sum(1 for x in xs if f(x))

    red_to_black = cnt(lambda x: x["m_before"] is not None and x["m_before"] <= 0
                       and x["m_after"] is not None and x["m_after"] > 0)
    lt5_to_ge5 = cnt(lambda x: x["m_before"] is not None and x["m_before"] < 0.05
                     and x["m_after"] is not None and x["m_after"] >= 0.05)
    fee_only_ge5 = cnt(lambda x: x["m_before"] is not None and x["m_before"] < 0.05
                       and x["m_fee0"] is not None and x["m_fee0"] >= 0.05)
    final_before = [x for x in xs if _final(x, "m_before")]
    final_after = [x for x in xs if _final(x, "m_after")]

    lines = [
        f"母集団（②③通過×入数解決×選定OK）: {len(xs)} ASIN",
        f"  うち回転6ヶ月・最小ロット10万円も満たす: {cnt(lambda x: not x['r']['why'])}",
        f"赤字→黒字: {red_to_black}",
        f"5%未満→5%以上: {lt5_to_ge5}（成約料0だけで {fee_only_ge5}）",
        f"最終候補（5%以上×回転6ヶ月×ロット10万×比率ガードなし）: 修正前 {len(final_before)} → 修正後 {len(final_after)}",
        f"カート価格の出どころ（Keepa取得 {len(targets)} ASIN）: " + ", ".join(
            f"{k} {sum(1 for x in final_after if x['src'] == k)}" for k in
            ("カート90日平均", "現在のカート価格", "最安値(カート取れず)")) + "（最終候補内）",
    ]

    # ── 見落とし (b)：未検証 1,719 / 入数未解決 ──
    unver = [r for r in recs if r["drops5"] and not r["verified"]]
    unver_asins = {r["asin"] for r in unver}
    ok_np = [r for r in unver if not r["why"]]
    ratios = [c["bb_avg90"] / (next((y["lo"] for y in xs if y["asin"] == a), None) or 1)
              for a, c in cache.items() if c.get("bb_avg90")]
    med = statistics.median(ratios) if ratios else 1.0
    ok_price = set()
    for r in ok_np:
        m, ev = R.margin_at(r, R.AFTER, (r["fact"].get("price_yen") or 0) * med)
        if m is not None and m >= 0.05 and not ev.review_reason:
            ok_price.add(r["asin"])
    n_verified = len({r["asin"] for r in recs if r["drops5"] and r["verified"]})
    pass_rate = len(passed) / max(n_verified, 1)
    unres = {r["asin"] for r in recs if r["passed"] and UNRESOLVED_LABEL in r["why"]}
    resolved_passed = {r["asin"] for r in recs if r["passed"] and UNRESOLVED_LABEL not in r["why"]
                       and "Amazon未出品/価格なし" not in r["why"]}
    hit_rate = len(final_after) / max(len(resolved_passed), 1)
    lines += [
        "",
        f"(b) 未検証（①通過・②③未実施）: {len(unver_asins)} ASIN",
        f"    価格以外の条件OK: {len({r['asin'] for r in ok_np})} / うちカート価格＝最安値×{med:.3f}(実測中央値)で5%以上: {len(ok_price)}",
        f"    ②③の通過率 {pass_rate:.1%} を掛けた見込み: 約 {round(len(ok_price) * pass_rate)} 件",
        f"(b) ②③通過のうち入数未解決: {len(unres)} ASIN。入数解決済みでの最終候補率 {hit_rate:.2%} を当てると 約 {round(len(unres) * hit_rate)} 件",
    ]

    # ── 見落とし (a)：未承認サプライヤー ──
    app = R.REPO / "workspace/output/agent_output/T-20260831-006/netsea_取引申請状況_480社.csv"
    if app.exists():
        from collections import Counter
        st = Counter(x["取引状況"] for x in csv.DictReader(app.open(encoding="utf-8-sig")))
        lines += ["", f"(a) 取引申請 480社の内訳: " + ", ".join(f"{k or '(空欄)'} {v}" for k, v in st.items()),
                  f"    取引中 {st['取引中']} 社のうち API で見える 225 社 → 見えない承認済み {st['取引中'] - 225} 社",
                  "    申請したことのない社の数は既存データに無い（NETSEA の全サプライヤー数を持っていない）"]

    # ── 上位30件 ──
    final_after.sort(key=lambda x: (x["r"]["months"], -(x["m_after"] or 0)))
    cols = ["順", "ASIN", "商品名", "仕入先", "卸値(税込・1出品ぶん)", "売値", "売値の出どころ", "最安値(参考)",
            "純利益", "利益率%", "純利益(修正前)", "利益率%(修正前)", "30日ドロップ", "出品者数", "月の取り分",
            "入数", "最小ロット出品数", "最小ロット金額", "最小ロットの回転月数", "10点の出品数", "10点買ったときの金額",
            "バリエーションの子", "PSE", "印", "Amazonページ", "NETSEA商品ページ"]
    rows = []
    for i, x in enumerate(final_after[:TOP_N], 1):
        r, ev = x["r"], x["ev"]
        row = r["row"]
        rows.append({
            "順": i, "ASIN": x["asin"], "商品名": row.get("商品名"), "仕入先": row.get("サプライヤー名"),
            "卸値(税込・1出品ぶん)": round(r["unit"] * r["pack"]), "売値": round(x["price"]),
            "売値の出どころ": x["src"], "最安値(参考)": x["lo"],
            "純利益": round(x["net_after"]), "利益率%": round(x["m_after"] * 100, 1),
            "純利益(修正前)": "" if x["net_before"] is None else round(x["net_before"]),
            "利益率%(修正前)": "" if x["m_before"] is None else round(x["m_before"] * 100, 1),
            "30日ドロップ": r["drops"], "出品者数": r["sellers"], "月の取り分": round(r["per_month"], 2),
            "入数": r["pack"], "最小ロット出品数": r["min_units"] // r["pack"], "最小ロット金額": r["lot_yen"],
            "最小ロットの回転月数": round(r["months"], 1), "10点の出品数": r["n10"],
            "10点買ったときの金額": r["yen10"],
            "バリエーションの子": "子" if r["is_child"] else "",
            "PSE": getattr(r.get("sel"), "pse_verdict", ""),
            "印": " / ".join(getattr(r.get("sel"), "flags", []) or []),
            "Amazonページ": row.get("Amazonページ"), "NETSEA商品ページ": row.get("NETSEA商品ページ"),
        })
    out.mkdir(exist_ok=True)
    with (out / "07_修正後候補.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    (out / "07_修正後_集計.txt").write_text("\n".join(lines) + "\n")
    _html(out / "07_修正後候補.html", lines, cols, rows, len(final_after))
    print("\n".join(lines))
    print(f"\n上位 {min(TOP_N, len(final_after))} 件 → {out/'07_修正後候補.csv'}")
    for d in rows[:10]:
        print(f"{d['順']:>2} {d['商品名'][:30]} | 純{d['純利益']} {d['利益率%']}% | 10点{d['10点買ったときの金額']} | {d['売値の出どころ']} | 回転{d['最小ロットの回転月数']}")


def _html(path, lines, cols, rows, total):
    e = html.escape
    num_cols = {"卸値(税込・1出品ぶん)", "売値", "最安値(参考)", "純利益", "純利益(修正前)", "最小ロット金額",
                "10点買ったときの金額"}

    def cell(c, v):
        if c in ("Amazonページ", "NETSEA商品ページ") and v:
            return f'<td><a href="{e(str(v))}" target="_blank">開く</a></td>'
        if c in num_cols and v != "":
            return f'<td class="n">{int(v):,}</td>'
        return f'<td>{e(str(v))}</td>'

    body = "".join("<tr>" + "".join(cell(c, d[c]) for c in cols) + "</tr>" for d in rows)
    path.write_text(f"""<title>修正後の NETSEA 候補</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mut:#6b6b66;--line:#e3e0d8;--acc:#1f6f5c}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#161614;--fg:#ecebe6;--mut:#a3a29c;--line:#34332f;--acc:#6cc3a8}}}}
:root[data-theme=dark]{{--bg:#161614;--fg:#ecebe6;--mut:#a3a29c;--line:#34332f;--acc:#6cc3a8}}
body{{background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,"Hiragino Sans",sans-serif;margin:0;padding:24px}}
h1{{font-size:20px;margin:0 0 4px}} .mut{{color:var(--mut)}}
pre{{background:transparent;border:1px solid var(--line);padding:12px;white-space:pre-wrap}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;font-size:12px}}
th,td{{border-bottom:1px solid var(--line);padding:4px 6px;vertical-align:top}} th{{text-align:left;position:sticky;top:0;background:var(--bg)}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}} a{{color:var(--acc)}}
</style>
<h1>修正後の NETSEA 候補（大口・カート価格90日平均）</h1>
<p class="mut">T-20260909-002 / 2026-09-12。基本成約料0・売値＝カート価格の直近90日平均（無ければ現在のカート価格→最安値）。他の費目とルールは従来どおり。
最終候補 {total} 件のうち上位 {len(rows)} 件。並びは最小ロットの回転月数が短い順。10点の金額は商品代のみ（送料別）。発注はしていません。</p>
<pre>{e(chr(10).join(lines))}</pre>
<div class="wrap"><table><thead><tr>{''.join(f'<th>{e(c)}</th>' for c in cols)}</tr></thead><tbody>{body}</tbody></table></div>
""", encoding="utf-8")
