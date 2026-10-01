#!/usr/bin/env python3
"""判定台帳 → 社長向け「買う候補リスト」（md / html）と、卸値つきフル版 CSV。

**真実は判定台帳シート**です。ここはその読み出しと整形だけ。

公開の線（CLAUDE.md §3.2 の注記・法務判定16・`source-terms-guard`）
----------------------------------------------------------------
| 項目 | リポ内の md/html | agent_output の CSV |
|---|---|---|
| 原価の実額・入り数・購入先URL・発注額の実額 | **書かない** | 書く |
| 率（卸率・利益率）・1個手残り・発注額の帯 | 書く | 書く |
| 購入元の名前（企業名） | 書く | 書く |
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
PIPE = REPO / "workspace/output/deliverables/T-20260920-003/26_候補提案パイプライン"
WORK = REPO / "workspace/output/agent_output/T-20260920-003/pipeline"
DELIV = REPO / "workspace/output/deliverables/T-20260920-003"
sys.path.insert(0, str(PIPE))
import ledger_sheet  # noqa: E402  (同じフォルダ)

TICKET = "T-20260920-003"
OTHER_UNIT_COSTS = 206          # 保管料+納品送料+梱包資材（商品台帳 L001 実測）
BUDGET_LEFT = 80_000            # テスト予算10万 − 消化19,756 ≒ 8万円
C = {name: i for i, name in enumerate(ledger_sheet.COLUMNS)}


def unit_columns(title: str, wholesale_incl, qty: int, order_total,
                 package_quantity=None, number_of_items=None, pack: int = 1) -> dict:
    """単位の3列と整合チェックを作る。**ここが今回の事故の現場。**

    - `set_count`          … Amazon の1個 ＝ 卸の何点か（読めなければ「未確定」）
    - `amazon_unit_cost`   … Amazon 1個あたりの原価 ＝ 卸の1点 × set_count
    - `wholesale_points`   … 発注で買う卸の点数 ＝ Amazon の個数 × set_count
    - `unit_check`         … `発注額 ≒ Amazon1個あたり原価 × 発注点数` が成り立つか

    不変条件が崩れていたら **数字を黙って直さず「NG」と書く**。
    黙って直すと、どちらが正しいか分からないまま辻褄だけが合います。
    """
    import set_family as sf
    sc = sf.resolve(title, package_quantity, number_of_items)
    mult = sc.n
    base = {"set_confidence": sc.confidence, "set_sources": sc.sources,
            "wholesale_sets": "", "wholesale_mouth": ""}
    if not wholesale_incl:
        return {**base, "set_count": "未確定" if mult is None else mult,
                "amazon_unit_cost": "", "wholesale_points": "",
                "unit_check": "原価が空（UNKNOWN）"}
    if not sc.is_decided():
        return {**base, "set_count": "未確定" if mult is None else f"{mult}?",
                "amazon_unit_cost": "", "wholesale_points": "",
                "unit_check": f"NG: セット数が確定していない（{sc.confidence}）。{sc.reason}"}
    unit = int(wholesale_incl) * mult
    points = qty * mult                        # 卸で買う点数（Amazon の個数 × セット数）
    lot = max(1, int(pack or 1))               # 卸はこの点数の倍数でしか売らない
    sets_ = -(-points // lot)                  # 卸で何口（何セット）買うか
    check = "OK"
    if order_total and abs(unit * qty - int(order_total)) > max(2, int(order_total) * 0.01):
        check = (f"NG: 発注額 {int(order_total):,} ≠ Amazon1個原価 {unit:,} × 発注点数 {qty}"
                 f" = {unit * qty:,}（単位が揃っていません）")
    return {**base, "set_count": mult, "amazon_unit_cost": unit,
            "wholesale_points": points,
            "wholesale_sets": sets_,
            "wholesale_mouth": f"1口{lot}点",
            "unit_check": check}


def clean_name(name: str) -> str:
    """セラー名・企業名から宣伝文を落として、**identity だけ**を残す。

    Amazon のストア表示名には「【◯◯円以上で全国送料無料】※一部…」のような
    宣伝文が入ります。公開情報なので秘密ではありませんが、
    「誰がカートを持っているか」を読む列に送料条件が混ざると読めません。
    """
    s = re.sub(r"[【\[（(][^】\])）]*(送料|無料|クーポン|ポイント|営業|即日|あす楽)[^】\])）]*[】\])）]",
               "", name or "")
    s = re.sub(r"※.*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _num(s):
    s = (s or "").replace(",", "").replace("%", "").replace("円", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def band(yen: float | None) -> str:
    """発注額は帯で出す（実額は会員限定の取引条件そのもの）。成果物21 と同じ刻み。"""
    if not yen:
        return "未算定"
    for lo, hi, label in ((0, 5000, "5千円未満"), (5000, 10000, "5千〜1万円"),
                          (10000, 15000, "1万〜1.5万円"), (15000, 20000, "1.5万〜2万円"),
                          (20000, 30000, "2万〜3万円"), (30000, 50000, "3万〜5万円")):
        if lo <= yen < hi:
            return label
    return "5万円以上"


def rank_of(reason: str) -> str:
    if "【ランク" in reason:
        return reason.split("【ランク", 1)[1].split("】", 1)[0].strip()
    return "不明"


def load_rows():
    state_ws = ledger_sheet.open_tab()
    values = state_ws.get_all_values()
    cands = json.loads((WORK / "discovered.json").read_text())["candidates"]
    out = []
    for r in values[1:]:
        if len(r) < len(ledger_sheet.COLUMNS) or r[C["チケットID"]] != TICKET:
            continue
        asin = r[C["ASIN"]]
        gross = _num(r[C["1個粗利(円)"]])
        cand = cands.get(asin, {})
        qty = _num(r[C["発注点数"]])
        total = _num(r[C["発注額(円・税込)"]])
        out.append({
            "asin": asin,
            "verdict": r[C["判定"]],
            "title": r[C["商品名"]],
            "brand": r[C["ブランド"]],
            "url": r[C["Amazon URL"]],
            "sell": _num(r[C["Amazon価格"]]),
            "sold": r[C["キーゾン 平均月販"]],
            "sellers": r[C["新品出品者数(画面実数)"]],
            "amazon": r[C["Amazon本体の有無"]],
            "cart": clean_name(r[C["カートの販売元"]]),
            "instock365": r[C["本体365日在庫率"]],
            "rank": rank_of(r[C["判定理由"]]),
            "cost_ratio": r[C["卸率(売価比)"]],
            "qty": int(qty) if qty is not None else "",
            "order_total": int(total) if total is not None else "",
            "date": r[C["判定日"]],
            "gross": int(gross) if gross is not None else None,
            "net": int(gross - OTHER_UNIT_COSTS) if gross is not None else None,
            "margin": r[C["利益率(%)"]],
            "months": r[C["売り切る月数"]],
            "gate": r[C["ゲート種別"]],
            "supplier": clean_name(r[C["購入元の名前"]]),
            "supplier_url": r[C["購入先URL"]],
            "reason": r[C["判定理由"]],
            # 卸値・入り数は台帳には率でしか無いので、発掘キャッシュ（agent_output）から取る
            "wholesale_incl": cand.get("unit_cost_incl"),
            "pack": cand.get("pack"),
            "jan": cand.get("jan", ""),
            **unit_columns(r[C["商品名"]], cand.get("unit_cost_incl"),
                           int(qty) if qty is not None else 0,
                           int(total) if total is not None else None,
                           (cand.get("extra") or {}).get("package_quantity"),
                           (cand.get("extra") or {}).get("number_of_items"),
                           cand.get("pack") or 1),
            # セット品ファミリの情報（どの口か・同じ JAN に何口あるか）
            "family_jan": (cand.get("extra") or {}).get("family_jan", ""),
            "family_size": (cand.get("extra") or {}).get("family_size", ""),
        })
    out.sort(key=lambda r: (-(r["verdict"] == "GO"), -(r["net"] if r["net"] is not None else -10 ** 9)))
    return out


# ── 予算8万円の組み合わせ案 ───────────────────────────────────────────────


def plans(go: list[dict]) -> list[tuple[str, str, list[dict], int, int]]:
    """(案の名前, 考え方, 行, 発注額, 見込み手残り) を3つ返す。貪欲法で十分。"""
    def pack(rows, budget=BUDGET_LEFT):
        chosen, spend = [], 0
        for r in rows:
            t = r["order_total"] or 0
            if t and spend + t <= budget:
                chosen.append(r)
                spend += t
        return chosen, spend, sum((r["net"] or 0) * r["qty"] for r in chosen)

    by_net = sorted(go, key=lambda r: -(r["net"] or 0))
    by_total = sorted(go, key=lambda r: (r["order_total"] or 10 ** 9))
    by_speed = sorted(go, key=lambda r: (_num(r["months"]) or 99,
                                         -(r["net"] or 0)))
    out = []
    for name, why, rows in (
        ("A 手残り優先", "1個あたりの手残りが大きい順に、予算に収まるまで積む。"
                         "1 SKU の当たりが大きいが、在庫が偏る。", by_net),
        ("B 数優先（SKU を増やす）", "発注額の小さい順に積む。出品許可申請の書類（納品書10点以上）を"
                                    "集めやすく、売れ筋の当たり外れを分散できる。", by_total),
        ("C 回転優先", "売り切る月数が短い順に積む。現金が戻るのが早く、"
                       "2周目の仕入れを早く回せる。", by_speed),
    ):
        chosen, spend, net = pack(rows)
        out.append((name, why, chosen, spend, net))
    return out


# ── 出力 ──────────────────────────────────────────────────────────────────

MD_COLS = ["#", "判定", "商品名", "ブランド", "Amazon", "売価", "過去1ヶ月の販売数",
           "セラー数", "Amazon本体", "カートの販売元", "本体365日在庫率", "売れ筋ランク",
           "Amazon側は何個セットか", "買う卸の口", "何口買うか",
           "卸率", "発注点数(Amazon何個)", "発注額の帯", "1個手残り", "利益率", "売り切る月数",
           "ゲート種別", "購入元の名前", "購入先URL"]


def set_label(r: dict) -> str:
    """「単品」か「N個セット」か「未確定」か。**空文字を返しません**（§3.2 空欄を作らない）。"""
    n = r.get("set_count")
    if n == 1:
        return "単品（Amazon 1個＝卸1点）"
    if isinstance(n, int) and n > 1:
        return f"{n}個セット（Amazon 1個＝卸{n}点）"
    return "セット数 未確定（人が両方の画面を見る）"


def md_table(rows: list[dict]) -> str:
    out = ["| " + " | ".join(MD_COLS) + " |",
           "|" + "---|" * len(MD_COLS)]
    for i, r in enumerate(rows, 1):
        out.append("| " + " | ".join(str(x) for x in [
            i, r["verdict"], r["title"][:48], r["brand"][:20],
            f"[dp/{r['asin']}]({r['url']})",
            f"{int(r['sell']):,}円" if r["sell"] else "不明",
            r["sold"], r["sellers"], r["amazon"], r["cart"][:32], r["instock365"],
            r["rank"],
            set_label(r),
            r["wholesale_mouth"] or "未確認", r["wholesale_sets"] or "未算定",
            r["cost_ratio"], r["qty"], band(r["order_total"]),
            (f"{r['net']:,}円" if r["net"] is not None else "未算定"), r["margin"], r["months"],
            r["gate"] or "未確認", r["supplier"] or "不明",
            "※非公開（卸サイトURL）",
        ]) + " |")
    return "\n".join(out)


def write_private_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # ⚠️ **単位を列名に書く。**2026-10-01、`原価(税込・1個あたり)` が「卸の1点」なのに
    # `発注点数` が「Amazon の個数」で、同じ CSV の中で単位が揃っていなかった
    # （カップ麺18食入りを 利益率75.5% と報告。実際は ▲778円/個）。
    # 「Amazon 何個を買うか」と「そのために卸を何点買うか」を**別の列**にする。
    cols = ["ASIN", "判定", "商品名", "ブランド", "AmazonURL", "JAN", "売価", "過去1ヶ月の販売数",
            "セラー数", "Amazon本体の有無", "カートの販売元", "本体365日在庫率", "売れ筋ランク",
            "卸の1点あたり原価(税込)", "Amazon側のセット数(Amazon1個=卸何点か)",
            "Amazon1個あたり原価(税込)", "卸の最小ロット(点)",
            "セット数の確度", "セット数の情報源", "同じJANの口の数",
            "発注点数(Amazon何個)", "発注する卸の点数", "買う卸の口", "買う卸の口数(セット)",
            "発注額(円・税込)",
            "卸率(売価比)", "1個粗利(円)", "1個手残り(円)", "利益率(%)", "売り切る月数",
            "単位の整合チェック",
            "ゲート種別", "購入元の名前", "購入先URL", "判定理由"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r["asin"], r["verdict"], r["title"], r["brand"], r["url"], r["jan"],
                        r["sell"], r["sold"], r["sellers"], r["amazon"], r["cart"],
                        r["instock365"], r["rank"],
                        r["wholesale_incl"], r["set_count"], r["amazon_unit_cost"], r["pack"],
                        r["set_confidence"], json.dumps(r["set_sources"], ensure_ascii=False),
                        r["family_size"],
                        r["qty"], r["wholesale_points"], r["wholesale_mouth"],
                        r["wholesale_sets"], r["order_total"],
                        r["cost_ratio"], r["gross"], r["net"], r["margin"], r["months"],
                        r["unit_check"],
                        r["gate"], r["supplier"], r["supplier_url"], r["reason"]])


def main() -> int:
    rows = load_rows()
    go = [r for r in rows if r["verdict"] == "GO"]
    unknown = [r for r in rows if r["verdict"] == "UNKNOWN"]
    write_private_csv(rows, WORK / "buy_list_private.csv")
    json.dump({"go": len(go), "unknown": len(unknown), "total": len(rows)},
              open(WORK / "buy_list_summary.json", "w"), ensure_ascii=False)
    print(f"GO {len(go)}件 / UNKNOWN {len(unknown)}件 / 台帳の本チケット行 {len(rows)}件")
    print(f"フル版CSV: {WORK / 'buy_list_private.csv'}")
    # md/html は内容の文章込みで別途書く（ここは表と予算案の素材だけ出す）
    (WORK / "buy_list_table.md").write_text(md_table(go or unknown[:20]), encoding="utf-8")
    lines = []
    for name, why, chosen, spend, net in plans(go):
        lines.append(f"### 案{name}\n\n{why}\n")
        lines.append(f"- 発注額 **{spend:,}円**／残り {BUDGET_LEFT - spend:,}円"
                     f"／SKU {len(chosen)}件／売り切ったときの手残り見込み **{net:,}円**")
        for r in chosen:
            lines.append(f"  - {r['title'][:40]}（{r['asin']}）… Amazon は{set_label(r)}"
                         f"／卸は{r['wholesale_mouth'] or '未確認'}の口を"
                         f"{r['wholesale_sets'] or '未算定'}口（＝{r['wholesale_points'] or '未算定'}点）"
                         f"／Amazon {r['qty']}個ぶん・{band(r['order_total'])}"
                         f"・1個手残り{r['net']:,}円")
        lines.append("")
    (WORK / "buy_list_plans.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"素材: {WORK / 'buy_list_table.md'} / {WORK / 'buy_list_plans.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
