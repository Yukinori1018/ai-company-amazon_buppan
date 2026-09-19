"""(a) 業界団体の名簿ページから、社名・電話番号・FAX・自社HP・取扱品目を抜く。

既存CSV（T-20260915-003）は社名しか抜いていなかった。同じページに残り4項目が
載っている団体があるので、そこを拾い直すのがこのスクリプト。

入力: agent_output/T-20260915-003/sources_html/ に保存済みの HTML（2026-09-15 取得）
      → ネットには一切アクセスしない。法務判定（05）を待たずに回せる。
出力: agent_output/T-20260920-002/S-F/assoc_<団体ID>.jsonl（団体ごとに都度保存）

    python3 scripts/maker_list/build_associations.py
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse, urlunparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maker_list import config as C
from maker_list.parsers import associations as A

# 「トップページではない」ことが明らかなパス。表示用URLはここだけ削る。
_JUNK_PATHS = ("privacy-policy", "privacypolicy", "sitemap", "/index.html", "/index.php")


def tidy_url(u: str) -> str:
    if not u:
        return ""
    p = urlparse(u)
    if any(j in p.path.lower() for j in _JUNK_PATHS):
        return urlunparse((p.scheme, p.netloc, "/", "", "", ""))
    return u


def origin(u: str) -> str:
    """巡回の起点にするトップページURL。"""
    if not u:
        return ""
    p = urlparse(u)
    return urlunparse((p.scheme, p.netloc, "/", "", "", "")) if p.netloc else ""


def main() -> int:
    os.makedirs(C.WORK_DIR, exist_ok=True)
    today = C.today()
    grand = []
    print(f"{'団体':12} {'行':>5} {'TEL':>5} {'FAX':>5} {'HP':>5} {'品目':>5}  備考")
    for aid, (name, url, cat, files) in A.ASSOCIATIONS.items():
        paths = [os.path.join(C.SOURCES_HTML, f) for f in files]
        raws = [open(p, encoding="utf-8", errors="ignore").read()
                for p in paths if os.path.exists(p)]
        if not raws:
            print(f"{aid:12} {'-':>5}  キャッシュHTMLなし（{files}）")
            continue
        rows = A.PARSERS[aid](raws, url)
        for r in rows:
            r["自社HP"] = tidy_url(r["自社HP"])
            r["HP起点"] = origin(r["自社HP"])
            r["カテゴリ"] = cat
            r["名簿"] = name
            r["名簿URL"] = url
            r["取得日"] = "2026-09-15"   # 保存済みHTMLの取得日。今日ではない。
            r["取得元"] = f"業界団体名簿（{name}）"
        # 団体ごとに都度書く（途中で落ちても部分成果が残る）
        out = os.path.join(C.WORK_DIR, f"assoc_{aid}.jsonl")
        with open(out, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        note = "※一覧に社名のみ。詳細ページの取得は法務判定(05)待ち" \
            if aid in A.NEEDS_DETAIL_PAGES else ""
        print(f"{aid:12} {len(rows):5} "
              f"{sum(1 for r in rows if r['電話番号']):5} "
              f"{sum(1 for r in rows if r['FAX番号']):5} "
              f"{sum(1 for r in rows if r['自社HP']):5} "
              f"{sum(1 for r in rows if r['取扱品目']):5}  {note}")
        grand += rows

    print(f"\n合計 {len(grand)}行 / TEL {sum(1 for r in grand if r['電話番号'])} "
          f"/ FAX {sum(1 for r in grand if r['FAX番号'])} "
          f"/ HP {sum(1 for r in grand if r['自社HP'])} "
          f"/ 品目 {sum(1 for r in grand if r['取扱品目'])}")
    print(f"出力先: {C.WORK_DIR}/assoc_*.jsonl（実行日 {today}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
