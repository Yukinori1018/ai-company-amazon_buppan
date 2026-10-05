"""追加候補（11_追加候補.csv）に gBizINFO の規模を付け、窓口集めのキューを出す（T-20260930-001 / 2026-10-05）。

    python3 36_size_additions.py           # gBiz を引く（1.15秒/件・キャッシュ済みは0回）→ 11 上書き＋12 出力

判定（カズヨ指示 2026-10-05）
- 大手 = 従業員300人超 または 資本金3億円超（gBiz で法人が1社に決まったとき）、または既知の大手リスト（maker_rules.known_big）
- 大手は除外せず「大手」列に印を付けるだけ。キューからは外す
- gBiz で1社に決まらない（一致なし・同名複数）・決まったが従業員も資本金も未登録 → 「規模不明」
- 照合は T-20260831-004 の 32_resolve_size.resolve() をそのまま使う（同名複数は推測で1社に決めない）。
  メーカー名で一致しなければブランドでもう一度引く

キューの順（12_窓口集めキュー.csv）
  1 印なし・要確認なし・中小 → 2 印あり・要確認なし・中小 → 3 規模不明（要確認なし）
  各層の中は 優先度A → 該当ASIN数 → 月販 の順。大手・要確認（本人カート疑い）はキューに入れない。
出力は Keepa の加工値（売価・月販）を含むので agent_output（Git 除外）に置く。
"""
from __future__ import annotations

import csv
import importlib.util
import shutil
from collections import Counter
from pathlib import Path

import maker_rules as R

REPO = Path(__file__).resolve().parents[4]
T4 = REPO / "workspace/output/deliverables/T-20260831-004"
WORK = REPO / "workspace/output/agent_output/T-20260930-001"

spec = importlib.util.spec_from_file_location("resolve_size", T4 / "32_resolve_size.py")
RS = importlib.util.module_from_spec(spec); spec.loader.exec_module(RS)


def size_of(client, maker: str, brand: str) -> dict:
    rec = RS.resolve(client, maker) if maker else {"理由コード": "U3"}
    if rec["理由コード"] == "U3" and brand and R._n(brand) != R._n(maker):
        rb = RS.resolve(client, brand)
        if rb["理由コード"] != "U3":
            rec = rb
    return rec


def label(rec: dict, kb: str) -> tuple[str, str]:
    """(大手の印, 規模の文言)"""
    code = rec.get("理由コード", "U3")
    emp, cap, name = rec.get("従業員数", ""), rec.get("資本金", ""), rec.get("gBiz商号", "")
    detail = "・".join(x for x in (name, f"従業員{emp}人" if emp != "" else "", f"資本金{int(cap) / 1e8:.1f}億円" if cap != "" else "") if x)
    if code in ("L1", "L2"):
        return "大手", f"大手（{detail}）"
    if kb:
        return "大手", f"大手（既知リスト：{kb}）"
    if code.startswith("M"):
        return "", f"中小（{detail}）"
    if code == "U1":
        return "", f"規模不明（{name}・従業員/資本金の登録なし）"
    if code == "U2":
        return "", f"規模不明（同名の法人が{rec.get('候補件数')}社）"
    return "", "規模不明（gBiz で一致なし）"


def main() -> None:
    src = WORK / "11_追加候補.csv"
    v1 = WORK / "11_追加候補_v1.csv"
    if not v1.exists():
        shutil.copy(src, v1)
    rows = list(csv.DictReader(v1.open(encoding="utf-8-sig")))
    client = RS.gb.GBizInfo(WORK / "gbiz")
    for i, r in enumerate(rows):
        brand = r["ブランド"].split(" / ")[0]
        rec = size_of(client, r["メーカー名"], brand)
        r["大手"], r["規模"] = label(rec, R.known_big(brand, r["メーカー名"]))
        r["法人番号(gBiz)"] = rec.get("法人番号", "")
        r["規模の注意"] = rec.get("照合の注意", "")
        if i % 50 == 0:
            client.flush(); print(f"{i}/{len(rows)} live={client.live_calls}", flush=True)
    client.flush()

    cols = list(rows[0].keys())
    with src.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)

    def tier(r):
        if r["大手"] or r["要確認"]:
            return None
        small = r["規模"].startswith("中小")
        if small and not r["印"]:
            return 1
        if small:
            return 2
        return 3
    q = [r for r in rows if tier(r)]
    num = lambda x: float(x) if x not in ("", None) else 0
    q.sort(key=lambda r: (tier(r), r["優先度"] != "A", -num(r["該当ASIN数"]), -num(r["過去1ヶ月の販売数(代表)"])))
    out = WORK / "12_窓口集めキュー.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["順位", "層", "メーカー名", "ブランド", "代表ASIN", "AmazonURL", "該当ASIN数", "月販", "売価",
                    "印", "要確認", "規模", "カート保持セラー"])
        names = {1: "1 印なし・中小", 2: "2 印あり・中小", 3: "3 規模不明"}
        for i, r in enumerate(q, 1):
            w.writerow([i, names[tier(r)], r["メーカー名"], r["ブランド"], r["代表ASIN"], r["Amazon URL"], r["該当ASIN数"],
                        r["過去1ヶ月の販売数(代表)"], r["代表の売価"], r["印"], r["要確認"], r["規模"], r["カート保持セラー(代表)"]])
    c = Counter(tier(r) for r in q)
    print(f"DONE 追加候補 {len(rows)} / 大手 {sum(1 for r in rows if r['大手'])}"
          f"（gBiz {sum(1 for r in rows if r['大手'] and not r['規模'].startswith('大手（既知'))}・既知リスト {sum(1 for r in rows if r['規模'].startswith('大手（既知'))}）"
          f" / 中小 {sum(1 for r in rows if r['規模'].startswith('中小'))} / 規模不明 {sum(1 for r in rows if r['規模'].startswith('規模不明'))}"
          f" / キュー {len(q)}（層1 {c[1]}・層2 {c[2]}・層3 {c[3]}）", flush=True)
    print("規模不明の内訳", Counter(r["規模"][:12] for r in rows if r["規模"].startswith("規模不明")))


if __name__ == "__main__":
    main()
