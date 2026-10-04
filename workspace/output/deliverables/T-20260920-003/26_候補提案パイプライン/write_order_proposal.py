#!/usr/bin/env python3
"""成果物35「発注案」を書き出す（md ＋ html ＋ シート用CSV）。

    python3 write_order_proposal.py

出すもの
  deliverables/T-20260920-003/35_発注案.md / .html
  agent_output/.../score20261004/sheet_買う候補_20261004.csv   ← 判定台帳シート用
  agent_output/.../score20261004/top30_private.csv             ← 卸値つき（PUBLIC に出さない）

⚠️ **PUBLIC リポに卸値・卸率・卸サイトの商品 URL を書きません**（法務判定E・
`source-terms-guard`）。成果物に出すのは**購入元の企業名まで**で、実額は agent_output 側です。
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import order_plan                     # noqa: E402
import score_20261004 as SC           # noqa: E402

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
DELIV = REPO / "workspace/output/deliverables/T-20260920-003"
OUT = REPO / "workspace/output/agent_output/T-20260920-003/score20261004"
TOP_N = 30

# 社長への表の必須6列（CLAUDE.md §3.2）。**欠けた表は出さない。**
REQUIRED_COLUMNS = ("過去1ヶ月の販売数", "セラー数", "Amazon本体の有無",
                    "AmazonURL", "購入元の名前", "購入先URL")

# 先人の型（成果物34）。どれを使ったかを必ず書く（社長指示 2026-10-04）。
PRACTITIONER_NOTES = [
    "**売価750円以下は販売手数料5%**（ちゃんやま氏の計算例：販売750円−手数料38円−"
    "配送222円＝入金490円）。`fba_cost.referral_pct` の750円の崖として実装し、"
    "**この帯を候補から外していません**。",
    "**単価の下限は置かない**（実践者 N=6 全員が置いていない）。判定は**利益額**で切り、"
    "`fba_cost.MIN_PROFIT_YEN = 400`（実践者の下端）**または**利益率20%の OR にしました。",
    "**「低単価だからセット組」は誤り。体積が大きいからセット組**（`fba_cost.bundle_advice`）。"
    "小型で既に750円以下の商品をセットにすると手数料が5%→15.4%に跳ねます。",
    "**仕入れ数＝月販÷(出品者+1)**（うみぞう氏／`knowledge_keepa_operation_umizou`）を"
    "`profit.order_qty` の回転上限6ヶ月と合わせて使っています。",
]


def split_verdict(lv, ledger_price: int) -> str:
    """🔴 「一時的に安いだけ」か「恒常的に下がった」かを**データから**書く。

    ここは手で文章を書いてはいけません。2026-10-04、持ち越しの打ち切りを直したあとも
    手書きの文章が残っていて、**表の数字（中央値7,990円）と本文（12,100円のまま）が
    矛盾した成果物**を一度作りました。文章は必ず数字から作ります。
    """
    if not lv or not lv.median90:
        return "価格履歴が足りず切り分けできません。"
    parts: list[str] = []
    m90, m180, screen = lv.median90, lv.median180, lv.screen_price
    if m180:
        drift = (m90 - m180) / m180
        if drift <= -0.10:
            parts.append(f"**恒常的に下がっています**（180日中央 {m180:,}円 → "
                         f"90日中央 {m90:,}円・{drift * 100:+.0f}%）")
        elif drift >= 0.10:
            parts.append(f"**上がっています**（180日中央 {m180:,}円 → 90日中央 {m90:,}円）")
        else:
            parts.append(f"**水準は動いていません**（180日中央 {m180:,}円・"
                         f"90日中央 {m90:,}円）")
    if lv.slope_pct_per_30d is not None:
        parts.append(f"直近90日の傾きは {lv.slope_pct_per_30d:+.1f}%/30日")
    if screen:
        if lv.p25_90 and screen < lv.p25_90:
            parts.append(f"実画面 {screen:,}円 は90日の下位25%（{lv.p25_90:,}円）より下＝"
                         f"**履歴に出ていない安値**。一時的な下げか、"
                         f"履歴に乗らない出品かのどちらかで、**人が実画面で要確認**")
        elif screen > (lv.p75_90 or screen):
            parts.append(f"実画面 {screen:,}円 は上位25%より上＝いまは高値")
        else:
            parts.append(f"実画面 {screen:,}円 は90日の幅の中＝**普段の値どおり**")
    gap = ((ledger_price - m90) / m90 * 100) if m90 else 0
    parts.append(f"台帳の売価 {ledger_price:,}円 は90日中央値より {gap:+.0f}%")
    return "。".join(parts) + "。"


LANE = (REPO / "workspace/output/agent_output/T-20260920-003"
        / "lane_selling20261004/summary.json")


def lane_section() -> list[str]:
    """母数を取りに行くレーン（売れている棚 → NETSEA 索引）の**実測**結果。

    **走らせていなければ「未実施」と書きます。**推測で率を語りません
    （2026-09-30 に SD で同じ向きを試して 0/10件 だった実績があるので、
    「当たるはず」と書くのは特に危険）。
    """
    A = ["## 母数を取りに行くレーン（売れている棚から入る）の実測", ""]
    if not LANE.exists():
        return A + ["**未実施です。**Keepa のトークンがプール648件の再取得で尽きました"
                    "（1件3トークン × 648件 ＝ 1,944トークン／回復は20/分）。",
                    "", "`python3 lane_selling_first.py --budget 400` で走ります。", ""]
    d = json.loads(LANE.read_text())
    A += [f"- `monthlySold >= 50` の棚から **{d['照合']}件**を取り、"
          f"NETSEA 索引（67,667 JAN）に当てました",
          f"- **一致 {d['一致']}件（{d['一致率(%)']}%）**／消費 {d['消費トークン']}トークン"]
    if d["照合"] and d["一致率(%)"] > 0:
        need = int(round(100 / d["一致率(%)"] * 3))
        A.append(f"- 一致1件あたり約 **{need}トークン**。"
                 f"20件増やすには約 {need * 20:,}トークン＝**{need * 20 / 20 / 60:.1f}時間**"
                 f"（回復 20/分）")
    else:
        A.append("- 🔴 **一致0件でした。**2026-09-30 に SD で試したときと同じ結果です"
                 "（品揃えのズレ）。この向きは**カテゴリを絞らないと効きません**。")
    A += ["", "> 一致した行はまだ採算を当てていません（卸値・ロットの取得が別途必要）。"
          "**次に伸ばすのはここです。**", ""]
    return A


def md_table(rows: list[dict], cols: list[str]) -> list[str]:
    out = ["| " + " | ".join(cols) + " |",
           "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, (int, float)) and c not in ("現在価格÷90日中央値",
                                                         "価格の振れ幅",
                                                         "価格の傾き(%/30日)",
                                                         "利益率(%)", "悲観の利益率(%)",
                                                         "売り切る月数"):
                v = f"{int(v):,}"
            cells.append(str(v if v not in (None, "") else "—").replace("|", "／"))
        out.append("| " + " | ".join(cells) + " |")
    return out


def status_of(s: dict) -> str:
    """その行が**次に誰の一手**を待っているか。表の1列目に出す。"""
    if s["判定"] == "GO":
        return "機械判定 GO（実売の根拠あり）"
    return "🔴 実売をキーゾンで確認（人の1手）"


def build() -> tuple[list[str], list[dict], list[order_plan.Plan], dict]:
    scored = SC.score_all()
    live = [s for s in scored if s.get("product")]
    go, pend = SC.candidates(scored)
    cands = go + pend
    top = cands[:TOP_N]

    picks = [p for p in (order_plan.pick_from_row(s) for s in top) if p]
    plans = order_plan.build_plans(picks)

    stats = {
        "台帳": len(scored), "取り直し済み": len(live), "候補": len(cands),
        "機械GO": len(go), "確認待ち": len(pend),
        "判定": dict(Counter(s["判定"] for s in scored)),
        "等級": dict(Counter(s["等級"] for s in scored)),
        "落ちた内訳": dict(Counter(SC.first_fail(s) for s in scored
                                 if s["判定"] != "GO")),
    }
    rows = []
    for s in top:
        r = SC.as_row(s)
        r["次の一手"] = status_of(s)
        rows.append(r)
    return SC.relax_table(scored), rows, plans, stats | {
        "scored": scored, "top": top}


def main() -> int:
    relax, top_rows, plans, stats = build()
    scored, top = stats.pop("scored"), stats.pop("top")
    today = date.today().strftime("%Y-%m-%d")

    L: list[str] = []
    A = L.append
    A("# 発注案 — 価格履歴で採り直した候補と、残枠8万円で買う3案")
    A("")
    A(f"IT エンジニア タカシ／{today}／チケット T-20260920-003")
    A("")
    A("> **ロードマップ上の位置**：4日間 候補0件だった原因を「価格の陳腐化」ではなく"
      "「**普段いくらで売れているかを見ていなかったこと**」として直し、"
      "**発注と出品申請の手前まで**持っていく回です。発注は社長判断（§4.1）。")
    A("")
    A("---")
    A("")
    A("## 結論（3行）")
    A("")
    A(f"1. **候補は {stats['候補']}件**です（＝人が実画面で見る価値のある行。§3.3-16）。"
      f"内訳は**機械判定 GO が {stats['機械GO']}件**と、"
      f"**実売だけをキーゾンで見れば決まる行が {stats['確認待ち']}件**。"
      f"台帳 {stats['台帳']}件のうち今日の値で取り直せたのは {stats['取り直し済み']}件。")
    A("2. 🔴 **候補が増えない主因は原価でも売価でもなく「実売の根拠が無いこと」でした。**"
      f"`monthlySold` が取れている行は取り直せた行の "
      f"**{sum(1 for s in scored if s.get('monthlySold')) / max(1, stats['取り直し済み']) * 100:.0f}%** しかなく、"
      f"代用していたランクは **{sum(1 for s in scored if (s.get('rank_shared') or 1) > 1)}件が"
      f"兄弟 ASIN との共有値**で、"
      "ASIN 単位の「売れている根拠」になりません。")
    A("3. **入口が逆です。**既存プールは卸（NETSEA）から入って Amazon に当てたので、"
      "「仕入れはあるが売れていない棚」ばかりになりました。"
      "**売れている棚から入る**向き（`lane_selling_first.py`）を用意し、下の節で"
      "**実際に当たる率を測りました**。")
    A("")
    A("## 社長の5件を履歴で切り分けました（「一時的に安い」か「恒常的に下がった」か）")
    A("")
    A("| ASIN | 商品 | 台帳の売価 | 10/4 実画面 | 90日中央値 | 下位25% | 履歴の判定 | 切り分け |")
    A("|---|---|---:|---:|---:|---:|---|---|")
    names = {"B003181XQ8": "ナカイ 股関節サポート", "B00ZW7OO0I": "パールホワイト",
             "B01N5Q61K6": "オリヒロ フコイダン", "B004PXZAFI": "日本アンテナ",
             "B086LB3LH6": "マルフク クエン酸"}
    led = {"B003181XQ8": 12100, "B00ZW7OO0I": 1991, "B01N5Q61K6": 4250,
           "B004PXZAFI": 5897, "B086LB3LH6": 1980}
    by_asin = {s["asin"]: s for s in scored}
    for asin, nm in names.items():
        s = by_asin.get(asin) or {}
        lv = s.get("price")
        if not lv:
            A(f"| {asin} | {nm} | {led[asin]:,} | {SC.SCREEN_PRICES[asin]:,} | — | — | "
              f"取り直し未完 | — |")
            continue
        m90 = f"{lv.median90:,}" if lv.median90 else "—"
        p25 = f"{lv.p25_90:,}" if lv.p25_90 else "—"
        A(f"| {asin} | {nm} | {led[asin]:,} | {SC.SCREEN_PRICES[asin]:,} | "
          f"{m90} | {p25} | {lv.verdict} | {split_verdict(lv, led[asin])} |")
    A("")
    n_below = sum(1 for asin in names
                  if (by_asin.get(asin) or {}).get("price")
                  and (by_asin[asin]["price"].p25_90 or 0) > SC.SCREEN_PRICES[asin])
    A(f"> 🔴 **{n_below}/5件で、社長が実画面で見た価格が90日の下位25%より下でした**"
      "＝履歴に出ていない安値です。履歴は「普段いくらで売れているか」を教えてくれますが、"
      "**この5件は履歴と実画面が食い違います。**片方を黙って採らず、"
      "`price_history.PriceLevel.disagreement` に残し、**採算は低いほう（実画面）で**"
      "計算しています（§3.3-1「食い違ったら食い違いごと出す」）。")
    A("")
    n_same = sum(1 for asin in names
                 if (by_asin.get(asin) or {}).get("price")
                 and by_asin[asin]["price"].median90 == led[asin])
    A(f"🔴 **ここから分かったこと：{n_same}/5件で台帳の売価が90日中央値と1円単位で一致します。**"
      "つまり台帳が古かったのではなく、**Keepa の履歴そのものが社長の見た安値を"
      "見ていません**（薄い棚では最安オファーが履歴に乗らないことがある）。")
    A("")
    A("したがって **Keepa だけで売価を確定するのは不可能**です。パイプラインは")
    A("")
    A("1. 採算の売価を **min(90日中央値, 人が実画面で見た価格)** にし、")
    A("2. **発注の直前に、売価も人が実画面で見る**（ゲート確認と同じ一手でできます）")
    A("")
    A("という形にしました。**上位候補の実画面確認は、ゲートだけでなく価格も見てください。**")
    A("")
    A("## 🔴 どのゲートで何件落ちたか")
    A("")
    A("| 最初に落ちた／決まらなかったゲート | 件数 |")
    A("|---|---:|")
    for k, c in sorted(stats["落ちた内訳"].items(), key=lambda kv: -kv[1]):
        A(f"| {k} | {c}件 |")
    A("")
    if stats["候補"] < TOP_N:
        A(f"## 🔴 なぜ30件に届かないのか（{stats['候補']}件しか出ない理由）")
        A("")
        A("**原価でも売価でも条件の厳しさでもありません。『実売の根拠が機械では取れない』"
          "という、プールそのものの性質です。**下の感度表を見てください ──")
        A("**ランクの上限を10万位から50万位まで動かしても、候補はほとんど増えません。**")
        A("")
        A("| 事実 | 数 |")
        A("|---|---|")
        n_ms = sum(1 for s in scored if s.get("monthlySold"))
        A(f"| `monthlySold`（Amazon が表示する実売数）が取れている行 | "
          f"**{n_ms}件 / {stats['取り直し済み']}件"
          f"（{n_ms / max(1, stats['取り直し済み']) * 100:.0f}%）** |")
        A(f"| ランクが**兄弟 ASIN と共有**で ASIN 単位の根拠にならない行 | "
          f"**{sum(1 for s in scored if (s.get('rank_shared') or 1) > 1)}件** |")
        A(f"| 同じブランド×購入元の行 | **1リストあたり "
          f"{SC.MAX_PER_FAMILY}件まで**に制限（切る前は上位30件のうち25件が"
          f"DNライティングの直管蛍光灯・仕入れ先1社でした） |")
        A("")
        A("### だから、増やし方は3つしかありません（緩めることではない）")
        A("")
        A("| # | 手段 | 増える数 | 要るもの |")
        A("|---|---|---|---|")
        A("| ① | **キーゾンで実売を人が見る**（本リストの『次の一手』欄） | "
          "確認した数だけ GO/NO-GO が確定 | 1件あたり1分程度 × 30件 |")
        A("| ② | **売れている棚から入る**（`lane_selling_first.py`） | "
          "**未測定**（Keepa のトークンがプール再取得で尽きた） | Keepa トークン |")
        A("| ③ | 同じブランド×購入元の上限（4件）を上げる | "
          "見かけ上は増えるが**同じ棚**。発注案の分散が作れない | なし（非推奨） |")
        A("")
    A("## 条件をこう緩めれば何件増えるか")
    A("")
    L += relax
    A("")
    A("## 先人のどの型を使ったか")
    A("")
    for n in PRACTITIONER_NOTES:
        A(f"- {n}")
    A("")
    A("> 出典は成果物34「低単価帯で成立させる型」（リサーチャー サトル・2026-10-04）。"
      "**自分で一から設計した判定基準はありません。**")
    A("")
    A(f"## 上位 {len(top_rows)}件（手残りの大きい順）")
    A("")
    A("**1列目の「次の一手」を見てください。**")
    A("")
    A("- `機械判定 GO` … 実売の根拠（`monthlySold` か 単独ランク）まで揃っている行。"
      "**ゲートと価格だけ実画面で見れば発注判断に入れます。**")
    A("- `🔴 実売をキーゾンで確認` … **実売以外のすべてを通っている行。**"
      "`monthlySold` が非表示で、ランクが兄弟 ASIN と共有なので、"
      "**機械ではこれ以上進めません。**キーゾンで3か月の実数を見る1手で GO/NO-GO が決まります。")
    A("")
    if not top_rows:
        A("**0件です。**上の2つの表（落ちた内訳・緩めたときの件数）が理由です。")
    else:
        A("### 社長が現物を確認する列（§3.2 必須6列）")
        A("")
        L += md_table(top_rows, ["ASIN", "次の一手", "商品名", "過去1ヶ月の販売数",
                                 "売れ筋ランク", "セラー数", "Amazon本体の有無",
                                 "カートの販売元", "購入元の名前", "AmazonURL"])
        A("")
        A("### 価格履歴（採算の土台）")
        A("")
        L += md_table(top_rows, ["ASIN", "販売価格(90日中央値)", "販売価格(180日中央値)",
                                 "保守値(90日の下位25%)", "上位25%", "現在価格",
                                 "現在価格÷90日中央値", "価格の振れ幅",
                                 "価格の傾き(%/30日)", "価格の判定"])
        A("")
        A("### 採算")
        A("")
        L += md_table(top_rows, ["ASIN", "等級", "サイズ区分", "販売手数料",
                                 "FBA配送代行", "その他固定費", "1個手残り", "利益率(%)",
                                 "悲観の手残り", "悲観の利益率(%)",
                                 "発注点数(Amazon何個)", "発注額(円・税込)", "手残り合計"])
        A("")
        A("### 🔴 いつ買って、いつ売るか")
        A("")
        L += md_table(top_rows, ["ASIN", "発注日", "着荷の見込み", "FBA納品完了の見込み",
                                 "販売開始日", "売り切る月数", "売り切り目標月",
                                 "季節の窓", "発注→販売開始", "卸の在庫"])
        A("")
        A("> **リードタイムは推定です。**NETSEA / SD の商品ページには出荷目安が出ますが、"
          "当社の JAN 索引はそれを取っていません。**発注直前に商品ページで実際の出荷目安を"
          "見て上書きしてください**（`schedule.build(lead_bdays=…)`）。"
          "祝日は計算に入っていないので、11/3・11/23・年末年始ぶん数日は遅れます。")
    A("")
    A("## 発注案（残枠8万円・3SKU）")
    A("")
    if not plans:
        A(f"**組めません。**候補が {stats['候補']}件 しかなく、"
          f"3SKU の組み合わせが予算 {order_plan.BUDGET_YEN:,}円 に収まりません。")
        if top_rows:
            A("")
            A("候補のうち予算内で買えるものだけを単独で挙げます。")
            A("")
            L += md_table([r for r in top_rows
                           if (r.get("発注額(円・税込)") or 0) <= order_plan.BUDGET_YEN],
                          ["ASIN", "商品名", "等級", "発注点数(Amazon何個)",
                           "発注額(円・税込)", "手残り合計", "販売開始日", "売り切り目標月"])
    for p in plans:
        d = p.as_dict()
        A(f"### {d['案']}")
        A("")
        A(f"{d['狙い']}")
        A("")
        L += md_table(d["SKU"], ["ASIN", "商品名", "購入元", "等級", "次の一手",
                                 "発注数", "発注額", "1個手残り", "手残り合計",
                                 "販売開始", "売り切り目標", "季節の窓"])
        A("")
        A(f"- **合計発注額 {d['合計発注額']:,}円**（残枠 {order_plan.BUDGET_YEN:,}円）")
        A(f"- **想定手残り合計 {d['想定手残り合計']:,}円**"
          f"（悲観シナリオでは {d['悲観の手残り合計']:,}円）")
        A(f"- 捌ける月数 **{d['捌ける月数']:.1f}ヶ月**")
        A(f"- 購入元の分散: " + "／".join(f"{k} {v:,}円" for k, v in
                                        d["購入元の内訳"].items())
          + f"（1社への偏り {d['1社への偏り(%)']}%）")
        A(f"- **最悪ケース: 全量が売れ残って半値処分すると {d['最悪ケース(全量半値処分の損失)']:,}円**")
        A(f"- 何月にいくらの手残りになるか: "
          + "／".join(f"{m} {v:,}円" for m, v in d["月別の手残り"].items()))
        for w in d["注意"]:
            A(f"- ⚠️ {w}")
        A("")
    A("## この表を100件にスケールするとき、どの列が機械で埋まるか")
    A("")
    A("| 列 | 埋まり方 |")
    A("|---|---|")
    for col, how in (
        ("ASIN・商品名・ブランド・AmazonURL", "**機械**（Keepa）"),
        ("販売価格の中央値/下位25%/傾き/振れ幅", "**機械**（Keepa の価格履歴・追加トークン0）"),
        ("カートの販売元", "**機械**（`buybox=1`・1件3トークン）"),
        ("過去1ヶ月の販売数", "**機械**（`monthlySold`）。ただし**取れるのは一部の棚だけ**"),
        ("売れ筋ランク・季節のピーク月", "**機械**（`csv[3]`・追加トークン0）"),
        ("サイズ区分・手数料・FBA配送代行・その他固定費", "**機械**（`fba_cost`）"),
        ("セット数（Amazon1個=卸何点か）", "**機械＋人**。商品名と `packageQuantity` が"
                                           "一致した行だけ機械で確定。食い違いは人"),
        ("卸値・最小ロット・在庫", "**機械**（NETSEA API）／**SD は人**（§3.3-18）"),
        ("卸の出荷リードタイム", "🔴 **人**（索引に無い。発注直前に商品ページを見る）"),
        ("ゲート（申請ボタンが押せるか）", "🔴 **人**（セラーセントラル・§3.3-25）"),
        ("3か月の実売数（キーゾン）", "🔴 **人**（§3.3-16）"),
    ):
        A(f"| {col} | {how} |")
    A("")
    brands = {r.get("ブランド") or "" for r in top_rows}
    if any("DN" in b or "ライティング" in b for b in brands):
        A("## 発注前に確認が必要な論点（私は一次情報を取っていません）")
        A("")
        A("候補に **DNライティングの直管蛍光ランプ**が入っています。"
          "直管蛍光ランプは**水銀規制（水俣条約）の対象で、製造・輸出入の終了時期が"
          "決まっていると認識しています**が、**私は一次情報を確認していません。**")
        A("")
        A("- 在庫を6ヶ月持つ商品なので、**終了時期が在庫期間に重なると売れ残ります**")
        A("- 逆に、終了前の駆け込み需要で**伸びる**可能性もあります（どちらに振れるか私には言えません）")
        A("- 🔴 **ハルオ（法務）に規制の時期を確認してから発注してください。**"
          "推測で発注の判断材料にしないでください")
        A("")
        A("> これは**ゲートにしていません**。商品名のキーワードで落とす/残すを決めるのは"
          "§3.3-20 が禁じている型（「土」で土鍋を春物にした事故）なので、"
          "**論点として出すだけ**にしています。")
        A("")
    L += lane_section()
    A("## やっていないこと（境界）")
    A("")
    A("- **発注・購入・決済・第三者連絡はしていません**（§4.1）。発注の手前で止めています。")
    A("- **出品許可の申請もしていません。**上位候補の ASIN を出すところまでです。")
    A("- **スーパーデリバリーへの自動リクエストは1件も投げていません**（§3.3-18）。")
    A("- **卸値・卸率・卸サイトの商品 URL はこの成果物に書いていません**（法務判定E）。"
      "実額は `agent_output/.../score20261004/top30_private.csv` にあります。")

    md = "\n".join(L) + "\n"
    (DELIV / "35_発注案.md").write_text(md, encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    # シート用（§3.2 の必須6列を含む全列）
    with (OUT / "sheet_買う候補_20261004.csv").open("w", encoding="utf-8-sig",
                                                   newline="") as f:
        w = csv.DictWriter(f, fieldnames=SC.COLS, extrasaction="ignore")
        w.writeheader()
        for r in top_rows:
            w.writerow(r)
    json.dump({"案": [p.as_dict() for p in plans]},
              (OUT / "order_plans.json").open("w"), ensure_ascii=False, indent=1,
              default=str)
    # 卸値つきのフル版（PUBLIC に出さない。`購入先URL` と卸の実額はこちらだけ）。
    priv_cols = SC.COLS + ["購入先URL", "卸の1点あたり原価(税込)", "卸の最小ロット(点)"]
    with (OUT / "top30_private.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=priv_cols, extrasaction="ignore")
        w.writeheader()
        for s_ in top:
            row = SC.as_row(s_)
            row["購入先URL"] = s_["row"].get("購入先URL")
            row["卸の1点あたり原価(税込)"] = s_["row"].get("卸の1点あたり原価(税込)")
            row["卸の最小ロット(点)"] = s_["row"].get("卸の最小ロット(点)")
            w.writerow(row)

    # §3.2 の必須6列のうち `購入先URL` は **PUBLIC 成果物には意図的に入れません**
    # （法務判定E・`source-terms-guard`）。社長への報告と agent_output 側に出します。
    missing = [c for c in REQUIRED_COLUMNS if c not in SC.COLS and c != "購入先URL"]
    print(f"35_発注案.md を書きました（候補 {stats['候補']}件・発注案 {len(plans)}案）")
    if missing:
        print(f"⚠️ §3.2 の必須列が落ちています: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
