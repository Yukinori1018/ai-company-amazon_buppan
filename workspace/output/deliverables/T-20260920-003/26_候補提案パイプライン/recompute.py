#!/usr/bin/env python3
"""台帳の採算を**トークン0で**引き直す（2026-10-01 の単位ずれの是正）。

なぜ必要か
----------
2026-10-01、`B0FNWB76NG`（カップ麺 110g・18食入り）を
**卸率5.2%・利益率75.5%・1個手残り +3,706円** として台帳に書きました。
正しくは **Amazon の1個 ＝ 卸18点**で、原価は 268円ではなく 4,824円 ＝ **▲778円/個**。
原因は商品名の「18食入り」を単品と読んだこと（`set_count` の取りこぼし）です。

直したのは3つで、**どれも Keepa を1トークンも使いません**（売価・手数料・FBA は発掘時の値）。

1. `set_count`: 「N食入り」「2P」型は 1 と決め打たず **None（UNKNOWN）**
2. `candidate_pipeline`: **卸率15%未満 / 利益率50%超は UNKNOWN**（単位ずれの番兵）
3. `candidate_pipeline`: **1 SKU の発注額が8万円超は NO-GO**（残枠を超える案は出さない）

やらないこと
------------
- **Keepa を叩き直しません。**売価は取得時点のものなので、ここで出る数字は
  「あの時の売価での再計算」です。発注の直前には人が実画面で見ます（§3.3）。
- **人が実画面で確認した行は上書きしません**（`ledger_sheet.update_row` が守ります）。
- **数字を黙って直しません。**変わった行は差分を印字し、理由を `判定理由` に残します。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "24_カート保持者ガード"))

import candidate_pipeline as CP            # noqa: E402
import candidate_sources as sources        # noqa: E402
import json                                # noqa: E402
import ledger_sheet                        # noqa: E402
import fba_cost
import profit                              # noqa: E402
import set_count                           # noqa: E402
from verdict import FAIL, GO, NO_GO, PASS, UNKNOWN  # noqa: E402

CACHE = (sources.REPO / "workspace/output/agent_output/T-20260920-003/pipeline/discovered.json")
C = {n: i for i, n in enumerate(ledger_sheet.COLUMNS)}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("円", "").strip())
    except (TypeError, ValueError):
        return None


def recompute_one(cand: dict, row: list) -> tuple[list, str] | None:
    """1行ぶん引き直す。(新しい行, 何が変わったか) か、変える必要がなければ None。

    ⚠️ **売価は台帳の値を使う。**発掘キャッシュの売価は取得時点のもので、台帳の値は
    段B（§3.3 判定）で取り直した**より新しい**値です。キャッシュ側で計算し直すと、
    **新しい売価を古い売価で黙って上書き**します（最初そう書いて、利益率が24.7→30.4 の
    ように勝手に動きました）。直したいのは**原価の単位だけ**なので、原価だけ差し替える。

    手数料（販売手数料＋FBA）は台帳に列が無いので、**恒等式から引き算で取り出す**:

        1個粗利 = 売価 − 手数料 − 原価   →   手数料 = 売価 − 原価 − 1個粗利
        （原価 = 売価 × 卸率。どちらも台帳の列）

    こうすると、**原価以外は1円も動きません。**
    """
    sell = _num(row[C["Amazon価格"]])
    gross_old = _num(row[C["1個粗利(円)"]])
    ratio_old = _num(row[C["卸率(売価比)"]])
    qty_old = _num(row[C["発注点数"]])
    wholesale, pack = cand.get("unit_cost_incl"), cand.get("pack") or 1
    ms = cand.get("monthly_sold")

    mult, set_note = set_count.cost_multiplier(cand.get("title"))

    econ = None
    if (mult is not None and wholesale and sell and gross_old is not None
            and ratio_old is not None):
        # ⚠️ **丸めた卸率から原価を復元してはいけない。**
        # 卸率は小数1桁に丸めて保存されているので、そこから戻した原価は数円ずれ、
        # その誤差が手数料に入り、**走らせるたびに1個粗利が数円ずつ動きます**
        # （最初そう書いて、同じ入力で 1969 → 1964 → … と漂いました。冪等でない是正は是正ではない）。
        # 本当の原価は「卸の1点 × 整数」なので、**整数倍の中から一番近いものを選ぶ**。
        # これで元の値を厳密に復元でき、2回目以降は1円も動きません。
        target = sell * ratio_old / 100.0
        k = max(1, min(range(1, set_count.MAX_PLAUSIBLE + 1),
                       key=lambda n: abs(wholesale * n - target)))
        cost_old = wholesale * k
        fees = sell - cost_old - gross_old          # 販売手数料＋FBA（台帳の数字から復元）
        cost_new = wholesale * mult
        qty = profit.order_qty(ms, set_count.order_lot_in_amazon_units(pack, mult))
        gross_new = int(round(sell - fees - cost_new))
        # 🔴 2026-10-04: その他固定費は一律206円ではなく**サイズ区分別**（成果物33）。
        # ここは台帳から「販売手数料＋FBA」を合算で復元しているのでサイズ区分が分かりません。
        # **推測で埋めず、`fba_cost.grade()` に区分 None を渡して UNKNOWN にします**
        # （区分で 222円〜1,756円まで動くため）。区分が要るなら `regrade.py` を使ってください。
        g = fba_cost.grade(sell, cost_new, None)
        econ = profit.Economics(
            sell=int(round(sell)), unit_cost_incl=int(round(cost_new)),
            referral_fee_yen=int(round(fees)), fba_yen=0,
            gross_per_unit=gross_new,
            margin_pct=round(gross_new / sell * 100, 1),
            other_unit_costs=0, net_per_unit=gross_new,
            net_margin_pct=round(gross_new / sell * 100, 1),
            qty=qty, order_total=int(round(cost_new)) * qty,
            months_to_sell=round(qty / ms, 1) if ms else None,
            half_disposal_loss=int(round(cost_new)) * qty
            - max(0, int(round(sell / 2 * 0.9 - 500))) * qty,
            cost_ratio_pct=round(cost_new / sell * 100, 1),
            size_tier=None, grade=g.grade, grade_reason=g.reason,
        )

    econ_status, econ_reason = CP.economics_status(econ, ms, set_note)
    old_verdict = row[C["判定"]]

    if econ_status == FAIL:
        verdict = NO_GO
    elif old_verdict == NO_GO:
        verdict = NO_GO                     # 他のゲートで既に落ちている
    elif econ_status == UNKNOWN:
        verdict = UNKNOWN
    else:
        verdict = old_verdict               # 採算 PASS。他のゲートの結論を維持

    new = list(row)
    if econ:
        new[C["卸率(売価比)"]] = f"{econ.cost_ratio_pct}%"
        new[C["発注点数"]] = str(econ.qty)
        new[C["発注額(円・税込)"]] = str(econ.order_total)
        new[C["1個粗利(円)"]] = str(econ.gross_per_unit)
        new[C["利益率(%)"]] = str(econ.margin_pct)
        new[C["売り切る月数"]] = str(econ.months_to_sell) if econ.months_to_sell else ""
        new[C["半値処分時の損失(円)"]] = str(econ.half_disposal_loss)
    elif mult is None:
        # 単位が読めない＝採算を出してはいけない。**古い数字を残さず空にする。**
        for col in ("卸率(売価比)", "発注点数", "発注額(円・税込)", "1個粗利(円)",
                    "利益率(%)", "売り切る月数", "半値処分時の損失(円)"):
            new[C[col]] = ""
    new[C["判定"]] = verdict

    # ⚠️ **自分が前回書いた節も剥がす。**「再計算.」を剥がさずに追記していたため、
    # 走らせるたびに判定理由が伸び、**毎回240行が「変わった」ことになっていました。**
    parts = [x for x in row[C["判定理由"]].split("／")
             if not any(k in x for k in ("採算.", "単位.", "再計算."))]
    parts.append(f" 採算. {econ_reason}")
    if set_note and "単品" not in set_note:
        parts.append(f" 単位. {set_note}")
    parts.append(f" 再計算. {date.today().isoformat()} 単位ずれの是正で原価だけ引き直し"
                 "（売価・手数料は台帳の値のまま・Keepa 未再取得）")
    new[C["判定理由"]] = "／".join(parts)[:1000]

    def norm(cells: list) -> list:
        """セルの比較用に正規化する。Sheets は "34.8%" を "34.80%" として返すので、
        **書式の違いだけで「変わった」と数えない**（240行を毎回書き直していた）。"""
        out = []
        for v in cells:
            v = str(v).strip()
            # Sheets は "34.8%"→"34.80%"、"2.0"→"2" のように**書式を変えて返す**。
            # 数として同じものを「変わった」と数えないために、数値は共通の形に揃える。
            if v.endswith("%"):
                n = _num(v)
                v = f"{n:.1f}%" if n is not None else v
            else:
                n = _num(v)
                if n is not None and v and v[0].isdigit() or (n is not None and v.startswith("-")):
                    v = f"{n:.2f}"
            out.append(v)
        return out

    if norm(new) == norm(row):
        return None
    bits = []
    if new[C["判定"]] != old_verdict:
        bits.append(f"{old_verdict}→{new[C['判定']]}")
    for col, label in (("利益率(%)", "利益率"), ("1個粗利(円)", "1個粗利"),
                       ("発注額(円・税込)", "発注額"), ("卸率(売価比)", "卸率")):
        if norm([new[C[col]]]) != norm([row[C[col]]]):
            bits.append(f"{label} {row[C[col]] or '-'}→{new[C[col]] or '-'}")
    if not bits:
        bits.append("判定理由のみ")
    return new, f"{row[C['ASIN']]} " + " ／ ".join(bits)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="台帳に書き戻す（既定は試算だけ）")
    a = ap.parse_args()

    cands = json.loads(CACHE.read_text(encoding="utf-8"))["candidates"]
    ws = ledger_sheet.open_tab()
    values = ws.get_all_values()
    state = ledger_sheet.read_state(ws)

    changed, skipped_human, no_input = [], 0, 0
    for i, row in enumerate(values[1:], start=2):
        if len(row) < len(ledger_sheet.COLUMNS):
            continue
        asin = row[C["ASIN"]]
        cand = cands.get(asin)
        if not cand:
            no_input += 1               # 発掘キャッシュに入力が無い（過去セッションの行）
            continue
        if state.is_human_verified(asin):
            skipped_human += 1
            continue
        out = recompute_one(cand, row)
        if out:
            changed.append((i, *out))

    print(f"台帳 {len(values) - 1}行 / 入力が揃う {len(values) - 1 - no_input}行 / "
          f"人が確認済みで触らない {skipped_human}行 / **変わる {len(changed)}行**")
    for _i, _new, diff in changed:
        print("  " + diff)
    vc = [d.split()[1] for _i, _n, d in changed if "→" in d.split()[1]]
    from collections import Counter
    print("判定が変わる行:", dict(Counter(vc)) or "なし")

    if not a.apply:
        print("\n試算のみ。書き戻すには --apply を付けてください。")
        return 0

    # ⚠️ **1行ずつ送らない。**Sheets の書き込みは60リクエスト/分で、240行で 429 になる
    # （2026-10-01 に実際に止まり、半分だけ書けた状態になりました）。
    n = ledger_sheet.update_rows([(i, new) for i, new, _d in changed], ws, state)
    print(f"\n台帳を更新しました（{n}行）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
