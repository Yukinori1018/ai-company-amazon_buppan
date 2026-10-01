#!/usr/bin/env python3
"""【レーンB・併用】**発注候補に挙がった社だけ**の「取引条件」を人が在席して1社ずつ読む。

なぜこれが要るのか
    一括申請で卸価格が見える取引先は 2,176社ある（2026-09-30）。しかし**申請が通ったことと
    Amazon で売ってよいことは別**。人気順 N=55 のサンプルでは、態度が判明した48社のうち
    **17社（35%）が「Amazon.co.jp はご遠慮ください」と名指し**していた。
    **仕入れ判定の第0問より前**にある確認（CLAUDE.md §3.3-12）。

🔴 2026-10-01、**全件スキャン（レーンC）の経路を削除した。**
    2,176社を舐めるのではなく、**発注候補に挙がった社の dealer_id を引数で明示して引く**。
    歩留まり15%なら、網羅の85%は捨てるための作業（CLAUDE.md §3.3-18）。
    `--dealers <TSV>` で全社リストを渡す口はもう無い。`--dealer-ids` で明示した社だけが対象。

🔴 上限（`_budget.py` の `LANE_B` で定数固定。**引数では緩められない**）
    * **間隔3.0秒から**（429 が出たら翌日は 6→12→24→48 秒）
    * **1セッション20リクエスト・1日50リクエスト**
    * **`--attended` 必須。**無人運転は不可

取るページ（非ログインで 200）
    /p/do/dpsl/dcc/<dealer_id>/   取引条件の○△×表・販売規制・注意事項

🔴 出力の置き場
    このページには**送料表の実額が載っている**。SD 会員規約17条1項により会員限定情報なので、
    **出力は必ず `workspace/output/agent_output/` の下に置く**（Git 追跡外）。
    PUBLIC リポの deliverables には**判定（○/△/×/不明）と率だけ**を書く。

使い方
    python3 sd_dealer_terms.py --dealer-ids 12345,67890 --out <agent_output/.../sd> --attended
    python3 sd_dealer_terms.py --dealer-ids @candidates.txt --out ... --attended

終了コード
    0 正常 / 1 引数か在席の不備 / 2 Cloudflare / 4 停止中 / 5 429 でその日を打ち切った
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time

BASE = "https://www.superdelivery.com"
LABELS = ["ネット販売", "消費者への直送", "仕入れ前の販売", "画像転載", "代金引換"]
AMZ = re.compile(r"Amazon|amazon|アマゾン|ＡＭＡＺＯＮ")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, RateLimited, fetch               # noqa: E402
from _budget import (LANE_B, Budget, BudgetExceeded, DayCutOff,      # noqa: E402
                     NotAttended, SessionLimitReached, Suspended)


def mark_of(cell_html: str) -> str:
    """○△×は文字ではなく Font Awesome のアイコン。**テキスト化では消えるので HTML で見る。**"""
    if "fa-xmark" in cell_html or "fa-times" in cell_html or "×" in cell_html:
        return "×"
    if "triangle" in cell_html or "△" in cell_html:
        return "△"
    if "fa-circle" in cell_html or "○" in cell_html:
        return "○"
    txt = re.sub(r"<[^>]+>", "", cell_html).strip()
    return txt[:12] if txt else ""


def parse_terms(page: str) -> dict:
    out: dict[str, str] = {}
    for label in LABELS:
        m = re.search(r"<t[hd][^>]*>\s*" + re.escape(label) + r"\s*</t[hd]>\s*<td[^>]*>(.*?)</td>",
                      page, re.S)
        out[label] = mark_of(m.group(1)) if m else "記載なし"
    return out


def plain(page: str) -> str:
    t = re.sub(r"(?s)<(script|style).*?</\1>", "", page)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def judge(terms: dict, amz_ctx: list[str]) -> str:
    """Amazon で売ってよいかの判定。**推測で埋めない。**

    ×          … ネット販売が× もしくは Amazon を名指しで不可としている
    要確認     … ネット販売が△（多くは Amazon 名指し）。文脈を人が読む
    ○          … ネット販売が○ かつ Amazon の名指しなし
    不明        … ネット販売の記載がない（**○に畳まない**。CLAUDE.md §3.3-12）
    """
    net = terms.get("ネット販売", "")
    named_ng = any(re.search(r"(遠慮|不可|禁止|お断り|NG)", c) for c in amz_ctx)
    if net == "×" or named_ng:
        return "×"
    if net == "△":
        return "要確認"
    if net == "○":
        return "○"
    return "不明"


def read_dealer_ids(spec: str) -> list[str]:
    """`12345,67890` か `@file`（1行1ID）。**全社リストを渡す口は作らない。**"""
    if spec.startswith("@"):
        path = spec[1:]
        raw = [l.split("\t")[0].strip() for l in open(path, encoding="utf-8")]
    else:
        raw = spec.replace("\n", ",").split(",")
    ids = [re.sub(r"\D", "", s) for s in raw]
    return [i for i in dict.fromkeys(ids) if i]


def read_names(path: str | None) -> dict[str, str]:
    names: dict[str, str] = {}
    if not path or not os.path.exists(path):
        return names
    for line in open(path, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0] not in ("dealer_id", ""):
            names[p[0].strip()] = p[1].strip()
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dealer-ids", required=True,
                    help="発注候補に挙がった社の dealer_id。`12345,67890` か `@file`。"
                         "**明示した社だけが対象**（全件スキャンの経路は無い）")
    ap.add_argument("--out", required=True, help="agent_output 配下のディレクトリ")
    ap.add_argument("--names-tsv", help="dealer_id<TAB>name の TSV（表示名の補完にだけ使う）")
    ap.add_argument("--attended", action="store_true",
                    help="人が在席していることを明示する。**付けないと動かない**")
    ap.add_argument("--keep-raw", action="store_true",
                    help="送料表を含む本文も保存する（agent_output 限定・PUBLIC リポには出さない）")
    args = ap.parse_args(argv)

    if "agent_output" not in os.path.abspath(args.out):
        print("■ --out は agent_output 配下にしてください（送料表は会員限定情報）", file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)

    try:
        budget = Budget(args.out, attended=args.attended, lane=LANE_B)
    except Suspended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 4
    except NotAttended as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 1
    except DayCutOff as exc:
        print(f"■ {exc}", file=sys.stderr)
        return 5
    print(budget.describe(), flush=True)

    sink_path = os.path.join(args.out, "sd_dealer_terms.jsonl")
    prog_path = os.path.join(args.out, "sd_terms_progress.json")
    prog = (json.load(open(prog_path, encoding="utf-8")) if os.path.exists(prog_path)
            else {"done": {}, "failed": {}})
    prog.setdefault("done", {})
    prog.setdefault("failed", {})

    names = read_names(args.names_tsv)
    wanted = read_dealer_ids(args.dealer_ids)
    todo = [d for d in wanted if d not in prog["done"]]
    print(f"指定 {len(wanted)}社・未取得 {len(todo)}社（済 {len(prog['done'])}）", flush=True)
    if not todo:
        budget.finish()
        print("取るものがありません", flush=True)
        return 0

    rate_limited = False
    try:
        with open(sink_path, "a", encoding="utf-8") as sink:
            for n, did in enumerate(todo, 1):
                name = names.get(did, "")
                try:
                    budget.take()
                    page = fetch(f"{BASE}/p/do/dpsl/dcc/{did}/")
                except SessionLimitReached as exc:
                    print(f"■ {exc}", flush=True)
                    break
                except BudgetExceeded as exc:
                    print(f"■ {exc}", flush=True)
                    break
                except RateLimited as exc:
                    # 🔴 1件の失敗として飲み込まない
                    nxt = budget.note_rate_limited()
                    rate_limited = True
                    print(f"■ {exc}\n  → 本日はここで打ち切ります。明日は間隔 {nxt:.1f} 秒で再開します。",
                          flush=True)
                    break
                except Blocked as exc:
                    print(f"■ Cloudflare に止められました（{exc}）。保存して終了します。", flush=True)
                    break
                except Failed as exc:
                    prog["failed"][did] = str(exc)[:200]
                    print(f"  × {did} {name}: {exc}", flush=True)
                    continue
                terms = parse_terms(page)
                flat = plain(page)
                ctx = [m.group(0) for m in
                       re.finditer(r".{70}(?:Amazon|amazon|アマゾン).{90}", flat)][:4]
                rec = {"dealer_id": did, "dealer_name": name, **terms,
                       "amazon_mentioned": bool(AMZ.search(flat)),
                       "amazon_context": ctx,
                       "judge": judge(terms, ctx),
                       "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
                if args.keep_raw:
                    rec["raw_text"] = flat[:6000]
                sink.write(json.dumps(rec, ensure_ascii=False) + "\n")
                sink.flush()
                prog["done"][did] = rec["judge"]
                print(f"  {n}/{len(todo)} {did} {name}: "
                      f"ネット販売={terms['ネット販売']} 判定={rec['judge']}", flush=True)
    finally:
        with open(prog_path, "w", encoding="utf-8") as fh:
            json.dump(prog, fh, ensure_ascii=False, indent=1)
        if budget.finish():
            print(f"■ 429 なしが続いたので間隔を1段戻しました → {budget.interval:.1f} 秒", flush=True)
    print(f"完了。{budget.describe()}", flush=True)
    return 5 if rate_limited else 0


if __name__ == "__main__":
    sys.exit(main())
