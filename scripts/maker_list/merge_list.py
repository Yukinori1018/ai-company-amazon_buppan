"""(a)(b) の結果を既存CSVに重ねて、電話をかけられるリストにする。

出力は2種類。用途が違うので分けてある。
  10_メーカーリスト_全項目.csv … 監査用。値ごとに「出典」と「取得日」が付く
  11_メーカーリスト_電話用.csv/.html … 社長用。列を9つに絞った、上から順にかける画面

出力先は deliverables/<ticket>/out/（.gitignore 済み）。
電話番号を PUBLIC リポに置くのは **NO**（05_リスト拡充の法務判定 §3-2）。
理由は4つ（個情法27条／NAPAC の不許諾宣言／push の不可逆性／iタウンページ11条2項）。

out/ は .gitignore 対象＝worktree が消えると一緒に消えるので、
**同じ実行の中で**リポ外の素材フォルダへコピーするところまでを1セットにしている（05 §3-2）。

    python3 scripts/maker_list/merge_list.py
"""

from __future__ import annotations

import csv
import glob
import html
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maker_list import config as C
from maker_list.extract import ec
from maker_list.extract.htmlutil import norm_name

# 値と一緒に出典・取得日を持たせる列
TRACED = ["電話番号", "FAX番号", "自社HP", "取扱品目", "主な製品", "自社EC"]
# 05 §2-4：全レコードに source_url と fetched_at（JST）を必須列として持たせる。
BACKUP_DIR = os.path.expanduser(
    "~/Documents/AI Company 素材/Amazon物販事業/maker-list-20260920")

FULL_COLUMNS = (
    ["優先度", "社名", "カテゴリ", "規模区分", "従業員数",
     "電話番号", "番号の種別", "FAX番号", "自社HP", "問い合わせURL",
     "取扱品目", "主な製品", "自社EC", "自社EC根拠", "モール出店", "卸OEM記載",
     "所在地", "名簿", "会員種別", "名簿URL", "区分", "確度", "接触状況", "最終接触日"]
    + [f"{c}_{s}" for c in TRACED for s in ("出典", "取得日時")]
)
# 社長が電話をかける画面。列は11。監査列（出典・取得日時）はこちらには出さない。
# 「取扱品目」＝名簿に書いてあった事実／「サイト説明」＝自社HPの title と meta から
# 機械が拾った文なので要確認、と欄の名前で区別する（混ぜると確度が分からなくなる）。
OWNER_COLUMNS = ["優先度", "社名", "電話番号", "番号の種別", "取扱品目",
                 "サイト説明（要確認）", "自社HP", "自社EC", "モール出店",
                 "規模区分", "カテゴリ"]


def _load_jsonl(pattern: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(C.WORK_DIR, pattern))):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def priority(r: dict) -> str:
    """電話をかける順番。材料が揃っていない今の状態で言える範囲だけで決める。

      S = 電話番号があり、何を作っているか分かり、ネット直販の形跡が無い
          （＝「ネット販売に疎い中小メーカー」という本丸の定義に最も近い）
      A = 電話番号があり、何を作っているか分かる（EC はやっている）
      B = 電話番号はあるが、何を作っているか未取得（電話前に自分で調べる必要あり）
      C = 電話番号が無い（メール／FAX の対象）

    規模（従業員数）は gBizINFO 申請待ちで大半が空なので、**今は使っていない**。
    申請が下りたら S の条件に「従業員20人以下」を足すこと。
    """
    if not r.get("電話番号"):
        return "C"
    # 名簿の取扱品目は事実。自社HPの説明文は「製品を語っているか」を見てから採る
    # （社名と定型文だけの説明を「分かっている」に数えない）。
    knows_product = bool(r.get("取扱品目")) or ec.has_product_signal(r.get("主な製品", ""))
    if not knows_product:
        return "B"
    no_ec = (r.get("自社EC", "未確認") == "未確認"
             and r.get("モール出店", "未確認") == "未確認")
    return "S" if no_ec else "A"


def main() -> int:
    os.makedirs(C.OUT_DIR, exist_ok=True)
    base = list(csv.DictReader(open(C.BASE_CSV, encoding="utf-8-sig")))
    assoc = {norm_name(r["社名"]): r for r in _load_jsonl("assoc_*.jsonl")}
    crawl = {norm_name(r["社名"]): r for r in _load_jsonl("maker_pages*.jsonl")}

    out_rows: list[dict] = []
    stats = {k: 0 for k in
             ["電話番号", "FAX番号", "自社HP", "取扱品目", "主な製品", "自社EC有", "モール有",
              "規模区分", "問い合わせURL"]}
    src_count = {"名簿": 0, "自社HP": 0, "なし": 0}
    unreached = 0

    for b in base:
        key = norm_name(b["社名"])
        a = assoc.get(key, {})
        c = crawl.get(key, {})
        r: dict = {col: "" for col in FULL_COLUMNS}
        r.update({
            "社名": b["社名"],
            "カテゴリ": b.get("カテゴリ", ""),
            "名簿": b.get("名簿", ""),
            "会員種別": b.get("会員種別", ""),
            "名簿URL": b.get("名簿URL", ""),
            "区分": b.get("区分", ""),
            "従業員数": b.get("従業員数（gBizINFO）", ""),
            "所在地": a.get("所在地", ""),
            "接触状況": "未",
        })

        def put(col: str, value: str, src: str, date: str) -> None:
            if value and not r.get(col):
                r[col] = value
                if col in TRACED:
                    r[f"{col}_出典"] = src
                    r[f"{col}_取得日時"] = date

        # ① 業界団体名簿（構造化されていて信頼度が高いので先に入れる）
        if a:
            d = a.get("取得時刻") or a.get("取得日", "")
            s = a.get("出典URL") or a.get("名簿URL", "")
            put("電話番号", a.get("電話番号", ""), s, d)
            put("FAX番号", a.get("FAX番号", ""), s, d)
            put("自社HP", a.get("自社HP", ""), s, d)
            put("取扱品目", a.get("取扱品目", ""), s, d)
            if a.get("電話番号"):
                r["番号の種別"] = _kind(a["電話番号"])
                src_count["名簿"] += 1
        # ② メーカー自社HP
        if c:
            d = c.get("取得時刻") or c.get("取得日", "")
            s = (c.get("見たページ") or [c.get("HP起点", "")])[0]
            if not c.get("到達"):
                unreached += 1
            was_empty = not r["電話番号"]
            put("電話番号", c.get("電話番号", ""), s, d)
            put("FAX番号", c.get("FAX番号", ""), s, d)
            put("主な製品", c.get("主な製品", ""), s, d)
            if c.get("自社EC", "未確認") != "未確認":
                put("自社EC", c["自社EC"], s, d)
                r["自社EC根拠"] = c.get("自社EC根拠", "")
            if c.get("モール", "未確認") != "未確認":
                r["モール出店"] = c["モール"]
            if c.get("卸OEM記載", "未確認") != "未確認":
                r["卸OEM記載"] = c["卸OEM記載"]
            if c.get("問い合わせURL"):
                r["問い合わせURL"] = c["問い合わせURL"]
            if was_empty and c.get("電話番号"):
                r["番号の種別"] = c.get("番号の種別", "")
                src_count["自社HP"] += 1

        # 空欄の意味を2種類に分ける（「未調査」で濁さない）
        if not r["自社EC"]:
            r["自社EC"] = "未確認"
        if not r["モール出店"]:
            r["モール出店"] = "未確認"
        if not r["規模区分"]:
            r["規模区分"] = "未取得（gBizINFO申請待ち）" if not r["従業員数"] else _size(r["従業員数"])
        if not r["電話番号"]:
            src_count["なし"] += 1
        r["確度"] = "確定（出典あり）" if r["電話番号"] else "未取得"
        r["優先度"] = priority(r)
        out_rows.append(r)

        for k in ("電話番号", "FAX番号", "自社HP", "取扱品目", "主な製品", "問い合わせURL"):
            stats[k] += bool(r[k])
        stats["自社EC有"] += r["自社EC"] != "未確認"
        stats["モール有"] += r["モール出店"] != "未確認"
        stats["規模区分"] += not r["規模区分"].startswith("未取得")

    # ── 出力 ────────────────────────────────────────────────────
    full = os.path.join(C.OUT_DIR, "10_メーカーリスト_全項目.csv")
    with open(full, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FULL_COLUMNS)
        w.writeheader()
        w.writerows(out_rows)

    rank = {"S": 0, "A": 1, "B": 2, "C": 3}
    ordered = sorted(out_rows, key=lambda r: (rank[r["優先度"]], r["カテゴリ"], r["社名"]))
    owner = [{
        "優先度": r["優先度"], "社名": r["社名"], "電話番号": r["電話番号"],
        "番号の種別": r["番号の種別"],
        "取扱品目": r["取扱品目"][:60],
        "サイト説明（要確認）": r["主な製品"][:70],
        "自社HP": r["自社HP"], "自社EC": r["自社EC"], "モール出店": r["モール出店"],
        "規模区分": "未取得" if r["規模区分"].startswith("未取得") else r["規模区分"],
        "カテゴリ": r["カテゴリ"],
    } for r in ordered]
    ocsv = os.path.join(C.OUT_DIR, "11_メーカーリスト_電話用.csv")
    with open(ocsv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OWNER_COLUMNS)
        w.writeheader()
        w.writerows(owner)

    summary = {
        "実行日": C.today(), "総行数": len(out_rows), "充足": stats,
        "電話番号の出典内訳": src_count,
        "自社HPに到達できなかった社": unreached,
        "優先度": {k: sum(1 for r in out_rows if r["優先度"] == k) for k in "SABC"},
    }
    with open(os.path.join(C.OUT_DIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    _write_html(os.path.join(C.OUT_DIR, "11_メーカーリスト_電話用.html"), owner, summary)
    _backup(summary)
    _purge_old_cache()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n出力: {C.OUT_DIR}")
    print(f"リポ外バックアップ: {BACKUP_DIR}")
    return 0


def _backup(summary: dict) -> None:
    """リポ外の素材フォルダへ複製する（05 §3-2 の指定）。

    out/ は .gitignore 対象なので、worktree が消えると成果物ごと消える。
    「あとでコピーする」は必ず忘れるので、生成と同じ実行の中でここまでやる。
    """
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for fn in ("10_メーカーリスト_全項目.csv", "11_メーカーリスト_電話用.csv",
               "11_メーカーリスト_電話用.html", "summary.json"):
        src = os.path.join(C.OUT_DIR, fn)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, fn))
    open(os.path.join(BACKUP_DIR, "README.md"), "w", encoding="utf-8").write(
        f"""# メーカーリスト（電話番号入り）— リポ外バックアップ

- 由来チケット: T-20260920-002（S-F / IT エンジニア タカシ）
- 生成日: {summary['実行日']}
- 生成元: `scripts/maker_list/merge_list.py`（リポジトリ内）
- 行数: {summary['総行数']} / 電話番号 {summary['充足']['電話番号']}件

## なぜリポ外なのか

法務判定 `05_リスト拡充の法務判定.md` §3-2 で、**電話番号を PUBLIC リポジトリに
置くのは NO** と判定されています（個人情報保護法27条／NAPAC の不許諾宣言／
GitHub への push が不可逆であること／iタウンページ規約11条2項）。
リポジトリ内の `workspace/output/deliverables/T-20260920-002/out/` にも同じものが
ありますが、あちらは `.gitignore` 対象で、worktree が消えると一緒に消えます。
**長期保存の正はこのフォルダです。**

## 扱い

- 社内限定。第三者への提供・再公開はしない
- 利用目的は「当社のメーカー仕入れに係る取引先候補の調査、連絡、商談管理」に限る（05 §3-1）
- 掲載元から削除の要望が来たら、`出典` 列を頼りに該当行を削除する
- NAPAC 由来の行（161社）は再公開が一切できない
""")


def _purge_old_cache(days: int = 7) -> None:
    """HTML キャッシュは7日で捨てる（05 §3-2：全文の恒久保存はしない）。"""
    if not os.path.isdir(C.CACHE_DIR):
        return
    limit = time.time() - days * 86400
    for fn in os.listdir(C.CACHE_DIR):
        p = os.path.join(C.CACHE_DIR, fn)
        if os.path.isfile(p) and os.path.getmtime(p) < limit:
            os.remove(p)


def _kind(num: str) -> str:
    from maker_list.extract.phone import classify
    return classify(num)


def _size(emp: str) -> str:
    try:
        n = int(str(emp).replace(",", "").strip())
    except (TypeError, ValueError):
        return "未取得（gBizINFO申請待ち）"
    if n <= 20:
        return "S：小規模（20人以下）"
    if n <= 100:
        return "M：小（21〜100人）"
    if n <= 300:
        return "L：中（101〜300人）"
    return "X：除外（301人以上）"


def _write_html(path: str, rows: list[dict], summary: dict) -> None:
    def td(v: str, col: str) -> str:
        v = html.escape(str(v or ""))
        if col == "自社HP" and v:
            return f'<td><a href="{v}" target="_blank" rel="noopener">{v[:40]}</a></td>'
        if col == "電話番号" and v:
            return f'<td class="tel">{v}</td>'
        if col == "優先度":
            return f'<td class="p p{v}">{v}</td>'
        return f"<td>{v}</td>"

    s = summary["充足"]
    n = summary["総行数"]
    head = "".join(f"<th>{html.escape(c)}</th>" for c in OWNER_COLUMNS)
    body = "\n".join(
        "<tr>" + "".join(td(r[c], c) for c in OWNER_COLUMNS) + "</tr>" for r in rows)
    doc = f"""<!doctype html><html lang="ja"><meta charset="utf-8">
<title>メーカーリスト（電話用） {summary['実行日']}</title>
<style>
 body{{font-family:-apple-system,"Hiragino Sans",sans-serif;margin:24px;color:#222}}
 h1{{font-size:20px}} .note{{color:#666;font-size:13px;line-height:1.7}}
 table{{border-collapse:collapse;font-size:13px;margin-top:16px}}
 th,td{{border:1px solid #ddd;padding:5px 8px;text-align:left;vertical-align:top}}
 th{{background:#f4f6f8;position:sticky;top:0}}
 .tel{{font-weight:600;white-space:nowrap;font-variant-numeric:tabular-nums}}
 .p{{font-weight:700;text-align:center}} .pS{{background:#ffe8e8}} .pA{{background:#fff4e0}}
 .pB{{background:#f2f2f2}} .pC{{background:#fafafa;color:#999}}
 .k{{display:inline-block;margin-right:18px}} .k b{{font-size:18px}}
</style>
<h1>メーカーリスト（電話用）— {n}社</h1>
<p class="note">
<span class="k">電話番号 <b>{s['電話番号']}</b> / {n}（{s['電話番号']/n*100:.1f}%）</span>
<span class="k">自社HP <b>{s['自社HP']}</b>（{s['自社HP']/n*100:.1f}%）</span>
<span class="k">取扱品目（名簿） <b>{s['取扱品目']}</b></span>
<span class="k">サイト説明 <b>{s['主な製品']}</b></span>
<span class="k">EC信号 <b>{s['自社EC有']}</b></span>
<br>優先度 S={summary['優先度']['S']} / A={summary['優先度']['A']}
 / B={summary['優先度']['B']} / C={summary['優先度']['C']}（C＝電話番号なし＝メール・FAX対象）
<br><b>S</b>＝電話番号あり・何を作っているか分かる・ネット直販の形跡なし（本丸の定義に最も近い）。
上から順にかけてください。規模区分は gBizINFO の利用申請が下りるまで大半が「未取得」です。
<br>電話番号の出典と取得日は <code>10_メーカーリスト_全項目.csv</code> の各列に入っています。
</p>
<table><thead><tr>{head}</tr></thead><tbody>
{body}
</tbody></table></html>"""
    open(path, "w", encoding="utf-8").write(doc)


if __name__ == "__main__":
    raise SystemExit(main())
