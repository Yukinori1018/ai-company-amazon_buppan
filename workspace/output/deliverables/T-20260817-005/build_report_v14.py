"""scan_v14 の CSV から、社長がそのまま使える成果物を作る（トークン消費0）。

出力（`v14/` 配下）:
  00_サマリ.md        … 何件取れたか・何をどう絞ったか・正直な注意
  00_候補リスト.html  … 並べ替え・絞り込みができる1枚もの（社長の既定の好み＝テキスト+HTML併出力）

走行中でも安全に呼べる（CSV を読むだけ・冪等）。

    python3 build_report_v14.py
"""
from __future__ import annotations

import csv
import html
import json
import statistics
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "v14"
CSV_ALL = OUT / "01_候補プール_全件.csv"
CSV_GO = OUT / "02_候補リスト_社長用.csv"
CSV_MAKER = OUT / "03_メーカー名寄せ.csv"
PROGRESS = OUT / "progress.json"
SUMMARY_MD = OUT / "00_サマリ.md"
REPORT_HTML = OUT / "00_候補リスト.html"

# HTML に出す列（社長が見る12列 + 交渉に効く2列）。全39列は CSV 側で見てもらう。
SHOW = ["メーカー/ブランド", "商品名", "想定仕入れ金額(上限)", "Amazon価格",
        "仕入れ掛け率上限%", "実セラー数", "想定月販", "消化月数", "カテゴリ",
        "FBAサイズ", "リスク区分"]


def _rows(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _median(rows, key):
    vals = [v for v in (_num(r.get(key)) for r in rows) if v is not None]
    return round(statistics.median(vals)) if vals else "—"


def build_summary(go, all_rows, makers, prog) -> str:
    reasons = {}
    for r in all_rows:
        if r.get("判定") == "候補":
            continue
        for reason in (r.get("見送り理由") or "").split(" / "):
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
    top_reasons = sorted(reasons.items(), key=lambda kv: -kv[1])[:8]
    cats = {}
    for r in go:
        c = (r.get("カテゴリ") or "").split(" > ")[0] or "（不明）"
        cats[c] = cats.get(c, 0) + 1
    top_cats = sorted(cats.items(), key=lambda kv: -kv[1])[:10]
    risky = sum(1 for r in go if r.get("リスク区分"))
    big = sum(1 for r in go if r.get("規模フラグ") == "大手/海外疑い")
    k = (prog.get("keepa") or {})
    c = (prog.get("counts") or {})

    lines = [
        "# メーカー仕入れ 候補プール v14 — サマリ",
        "",
        f"生成: {time.strftime('%Y-%m-%d %H:%M')}　/　チケット: T-20260817-005",
        "",
        "## 結論",
        "",
        f"- **社長が連絡できる候補: {len(go)}件 / メーカー {len(makers)}社**",
        f"- 処理した商品: {c.get('processed', len(all_rows))}件（うち実セラー数を実測したのは "
        f"{c.get('offers_verified', '—')}件）",
        f"- 消費トークン: {k.get('tokens_consumed', '—')} / 経過 {prog.get('elapsed_hhmm', '—')}",
        f"- 停止理由: **{prog.get('stop_reason') or '走行中'}**",
        "",
        "## 社長の使い方",
        "",
        "1. `03_メーカー名寄せ.csv` を上から見る（**該当商品数が多い順**＝1社で複数SKU取れる可能性が高い順）",
        "2. `メーカー検索(Google)` のリンクから会社概要・問い合わせ先を引く",
        "3. 連絡して、`想定仕入れ金額の中央値` **以下**で卸してもらえるか聞く",
        "4. 個別商品の上限額は `02_候補リスト_社長用.csv` の `想定仕入れ金額(上限)` 列",
        "",
        "## 想定仕入れ金額(上限) の意味",
        "",
        "**「この金額以下で仕入れられれば、純利益率20%（会社KPI）を確保できる」上限**です。",
        "赤字ラインではありません（赤字ラインは `赤字ライン(これ以上は赤字)` 列）。",
        "基準売価は「現在の新品最安値」と「2026-02-23以降の最安値」の**小さい方**＝値下がりを織り込んだ保守側。",
        "",
        "## 数字の目安",
        "",
        f"- 想定仕入れ金額(上限) の中央値: **{_median(go, '想定仕入れ金額(上限)')}円**",
        f"- Amazon価格の中央値: {_median(go, 'Amazon価格')}円",
        f"- 仕入れ掛け率上限の中央値: {_median(go, '仕入れ掛け率上限%')}%",
        f"- 消化月数の中央値: {_median(go, '消化月数')}ヶ月",
        "",
        "## カテゴリ分布（候補）",
        "",
        "| カテゴリ | 件数 |", "|---|---|",
    ]
    lines += [f"| {c_} | {n} |" for c_, n in top_cats]
    lines += [
        "",
        "## 落とした理由の内訳",
        "",
        "| 理由 | 件数 |", "|---|---|",
    ]
    lines += [f"| {r} | {n} |" for r, n in top_reasons]
    lines += [
        "",
        "## 正直な注意（鵜呑みにしないでください）",
        "",
        f"1. **リスク区分あり {risky}件**（リチウム/電源系・電気製品）。PSE・FBA危険物・返品率→ODR に直結します。"
        "初回テストで避けるかは社長判断。",
        f"2. **大手/海外疑い {big}件**。レビュー件数フィルタを撤廃したぶん、発売直後の大手SKUも入ります。"
        "`規模フラグ` 列で見分けてください。",
        "3. **販売手数料率は `calc/fees.py` の表**を使っており、2026/4 改定前の値である疑いを経理ハジメが指摘しています。"
        "そのため料率に **+1.0ポイントの安全マージン**を乗せて、上限が甘くならないようにしています。",
        "4. **FBA在庫保管手数料は推定です**（繁忙期レートで保守側）。公式の実額とはズレます。",
        "5. **消化月数はゲートではありません**（社長方針: 順位付けに労力を割かない）。並べ替えの目安としてだけ見てください。",
        "6. **出品制限（ゲート）は未確認**です。発注前にワンクリック解除テストが必要です。",
        "",
        "## §4.1（社長承認が必要）",
        "",
        "- メーカーへの実連絡・見積依頼（第三者連絡）",
        "- 初回発注（金銭）",
        "- Keepa 上位プランへの変更（課金）",
    ]
    return "\n".join(lines) + "\n"


def build_html(go, makers, prog) -> str:
    """依存ゼロの1枚もの。並べ替え・絞り込みができれば十分（YAGNI）。"""
    head = "".join(f"<th data-i='{i}'>{html.escape(c)}</th>" for i, c in enumerate(SHOW))
    body = []
    for r in go:
        tds = []
        for c in SHOW:
            v = r.get(c, "")
            if c == "商品名":
                url = html.escape(r.get("Amazonページ", ""))
                keepa = html.escape(r.get("Keepaリンク", ""))
                tds.append(f"<td class='name'><a href='{url}' target='_blank' rel='noopener'>"
                           f"{html.escape(v)}</a> <a class='kp' href='{keepa}' "
                           f"target='_blank' rel='noopener'>Keepa</a></td>")
            elif c == "メーカー/ブランド":
                g = html.escape(r.get("メーカー検索(Google)", ""))
                tds.append(f"<td class='maker'><a href='{g}' target='_blank' rel='noopener'>"
                           f"{html.escape(v)}</a></td>")
            elif c in ("想定仕入れ金額(上限)", "Amazon価格"):
                tds.append(f"<td class='num money'>{html.escape(v)}</td>")
            elif c in ("仕入れ掛け率上限%", "実セラー数", "想定月販", "消化月数"):
                tds.append(f"<td class='num'>{html.escape(v)}</td>")
            elif c == "リスク区分":
                cls = "risk" if v else ""
                tds.append(f"<td class='{cls}'>{html.escape(v)}</td>")
            else:
                tds.append(f"<td>{html.escape(v)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    k = prog.get("keepa") or {}
    meta = (f"候補 {len(go)}件 / メーカー {len(makers)}社 ・ "
            f"消費 {k.get('tokens_consumed', '—')}トークン ・ "
            f"経過 {prog.get('elapsed_hhmm', '—')} ・ "
            f"停止理由 {html.escape(str(prog.get('stop_reason') or '走行中'))}")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>メーカー仕入れ 候補プール v14</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font-family: -apple-system, "Hiragino Sans", sans-serif; margin: 0; padding: 16px;
        background: #fff; color: #111; }}
 h1 {{ font-size: 18px; margin: 0 0 4px; }}
 .meta {{ color: #666; font-size: 13px; margin-bottom: 12px; }}
 .tools {{ margin-bottom: 10px; display: flex; gap: 8px; flex-wrap: wrap; }}
 input, select {{ padding: 6px 8px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px; }}
 table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
 th, td {{ border-bottom: 1px solid #e5e5e5; padding: 6px 8px; text-align: left;
           vertical-align: top; }}
 th {{ position: sticky; top: 0; background: #fafafa; cursor: pointer; white-space: nowrap; }}
 th:hover {{ background: #eee; }}
 td.num {{ text-align: right; white-space: nowrap; }}
 td.money {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
 td.name {{ max-width: 460px; }}
 td.maker {{ white-space: nowrap; font-weight: 600; }}
 td.risk {{ color: #b45309; }}
 a {{ color: #0b57d0; text-decoration: none; }}
 a:hover {{ text-decoration: underline; }}
 .kp {{ font-size: 11px; color: #888; }}
 tr:nth-child(even) {{ background: #fcfcfc; }}
</style></head><body>
<h1>メーカー仕入れ 候補プール v14（T-20260817-005）</h1>
<div class="meta">{meta}<br>
 <b>想定仕入れ金額(上限)</b> = この金額以下で仕入れられれば純利益率20%を確保できる上限（赤字ラインではありません）。
 メーカー名をクリックすると連絡先の検索、商品名をクリックすると Amazon ページが開きます。</div>
<div class="tools">
 <input id="q" placeholder="メーカー名・商品名・カテゴリで絞り込み" size="40">
 <select id="risk"><option value="">リスク区分: すべて</option>
  <option value="none">リスク区分なしだけ</option>
  <option value="any">リスク区分ありだけ</option></select>
 <span id="count"></span>
</div>
<table id="t"><thead><tr>{head}</tr></thead><tbody>
{"".join(body)}
</tbody></table>
<script>
const tb = document.querySelector('#t tbody');
const rows = Array.from(tb.rows);
const riskCol = {SHOW.index("リスク区分")};
function apply() {{
  const q = document.getElementById('q').value.trim().toLowerCase();
  const rk = document.getElementById('risk').value;
  let n = 0;
  for (const r of rows) {{
    const hasRisk = r.cells[riskCol].textContent.trim() !== '';
    let ok = !q || r.textContent.toLowerCase().includes(q);
    if (ok && rk === 'none') ok = !hasRisk;
    if (ok && rk === 'any') ok = hasRisk;
    r.style.display = ok ? '' : 'none';
    if (ok) n++;
  }}
  document.getElementById('count').textContent = n + ' 件表示';
}}
document.getElementById('q').addEventListener('input', apply);
document.getElementById('risk').addEventListener('change', apply);
let dir = {{}};
document.querySelectorAll('#t th').forEach(th => th.addEventListener('click', () => {{
  const i = +th.dataset.i;
  dir[i] = !dir[i];
  const val = r => {{
    const t = r.cells[i].textContent.trim();
    const n = parseFloat(t.replace(/,/g, ''));
    return isNaN(n) ? t : n;
  }};
  rows.sort((a, b) => {{
    const x = val(a), y = val(b);
    if (typeof x === 'number' && typeof y === 'number') return dir[i] ? x - y : y - x;
    return dir[i] ? String(x).localeCompare(String(y), 'ja')
                  : String(y).localeCompare(String(x), 'ja');
  }});
  rows.forEach(r => tb.appendChild(r));
}}));
apply();
</script></body></html>
"""


def main() -> None:
    go = _rows(CSV_GO)
    all_rows = _rows(CSV_ALL)
    makers = _rows(CSV_MAKER)
    prog = json.loads(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    SUMMARY_MD.write_text(build_summary(go, all_rows, makers, prog), encoding="utf-8")
    REPORT_HTML.write_text(build_html(go, makers, prog), encoding="utf-8")
    print(f"候補 {len(go)}件 / メーカー {len(makers)}社 → {SUMMARY_MD.name} / {REPORT_HTML.name}")


if __name__ == "__main__":
    main()
