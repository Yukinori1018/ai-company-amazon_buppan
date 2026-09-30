#!/usr/bin/env python3
"""取引企業ごとの「取引条件」を非ログインで取り、Amazon で売ってよい社だけを切り出す。

なぜこれを最初にやるのか
    一括申請で卸価格が見える取引先は 2,176社ある（2026-09-30）。しかし**申請が通ったことと
    Amazon で売ってよいことは別**。人気順 N=55 のサンプルでは、態度が判明した48社のうち
    **17社（35%）が「Amazon.co.jp はご遠慮ください」と名指し**していた。
    2,176社に当てると 700社前後が不可の見込み。**商品を列挙する前にここを落とす**のが安い。

取るページ（いずれも非ログインで 200）
    /p/do/dpsl/dcc/<dealer_id>/   取引条件の○△×表・販売規制・注意事項

🔴 出力の置き場
    このページには**送料表の実額が載っている**。SD 会員規約17条1項により会員限定情報なので、
    **出力は必ず `workspace/output/agent_output/` の下に置く**（Git 追跡外）。
    PUBLIC リポの deliverables には**判定（○/△/×/不明）と率だけ**を書く。
    そのため本スクリプトは送料表を保存しない（`--keep-raw` を付けたときだけ保存する）。

使い方
    python3 sd_dealer_terms.py --dealers <TSV> --out <agent_output/.../sd> [--limit 300] [--sleep 4.0]
    同じコマンドで再開する（1社ごとに保存）。
"""
from __future__ import annotations
import argparse, gzip, html, json, os, re, sys, time, urllib.error, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
BASE = "https://www.superdelivery.com"
LABELS = ["ネット販売", "消費者への直送", "仕入れ前の販売", "画像転載", "代金引換"]
AMZ = re.compile(r"Amazon|amazon|アマゾン|ＡＭＡＺＯＮ")


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fetch import Blocked, Failed, fetch  # noqa: E402

UA = ""  # 実際の User-Agent は _fetch.py が持つ


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
    不明        … ネット販売の記載がない
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dealers", required=True)
    ap.add_argument("--out", required=True, help="agent_output 配下のディレクトリ")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=4.0)
    ap.add_argument("--keep-raw", action="store_true",
                    help="送料表を含む本文も保存する（agent_output 限定・PUBLIC リポには出さない）")
    args = ap.parse_args()

    if "agent_output" not in os.path.abspath(args.out):
        print("■ --out は agent_output 配下にしてください（送料表は会員限定情報）", file=sys.stderr)
        return 1
    os.makedirs(args.out, exist_ok=True)
    sink_path = os.path.join(args.out, "sd_dealer_terms.jsonl")
    prog_path = os.path.join(args.out, "sd_terms_progress.json")
    prog = json.load(open(prog_path)) if os.path.exists(prog_path) else {"done": {}, "failed": {}}

    dealers = []
    for line in open(args.dealers, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and p[0] not in ("dealer_id", ""):
            dealers.append((p[0].strip(), p[1].strip()))
    todo = [d for d in dealers if d[0] not in prog["done"]]
    if args.limit:
        todo = todo[: args.limit]
    print(f"対象 {len(todo)}社（済 {len(prog['done'])} / 全 {len(dealers)}）", flush=True)

    with open(sink_path, "a", encoding="utf-8") as sink:
        for n, (did, name) in enumerate(todo, 1):
            try:
                page = fetch(f"{BASE}/p/do/dpsl/dcc/{did}/")
            except Blocked as exc:
                print(f"■ Cloudflare に止められました（{exc}）。保存して終了します。", flush=True)
                json.dump(prog, open(prog_path, "w"), ensure_ascii=False, indent=1)
                return 2
            except Failed as exc:
                prog["failed"][did] = str(exc)[:200]
                json.dump(prog, open(prog_path, "w"), ensure_ascii=False, indent=1)
                print(f"  × {did} {name}: {exc}", flush=True)
                time.sleep(args.sleep)
                continue
            terms = parse_terms(page)
            flat = plain(page)
            ctx = [m.group(0) for m in re.finditer(r".{70}(?:Amazon|amazon|アマゾン).{90}", flat)][:4]
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
            json.dump(prog, open(prog_path, "w"), ensure_ascii=False, indent=1)
            print(f"  {n}/{len(todo)} {did} {name}: ネット販売={terms['ネット販売']} 判定={rec['judge']}", flush=True)
            time.sleep(args.sleep)
    print("完了", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
