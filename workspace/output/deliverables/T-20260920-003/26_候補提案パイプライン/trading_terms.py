#!/usr/bin/env python3
"""取引条件ゲート — 「その企業から買ったものを Amazon に出してよいか」（CLAUDE.md §3.3-12）。

これは**仕入れ判定の第0問より前**にあります。売れる棚で黒字でも、出してはいけない先から
買えば意味がありません。2026-09-30 の実測で、SD の出展企業は**態度が判明した48社のうち17社
（35%）が Amazon を名指しで不可**でした。

真実はシート `14VnMuvVDYNFlP0uer5y9E2atXnKbNWEHsGMrKk_xl68` のタブ `SD取引条件`（163社）。
`判定` 列の内訳（2026-10-01 実測）:

| 値 | 件数 | 扱い |
|---|---|---|
| `○` | 108 | **候補にしてよい** |
| `×（Amazon名指し不可またはネット販売不可）` | 46 | NO-GO |
| `要確認（△・モール名を要確認）` | 3 | UNKNOWN |
| `不明（ネット販売の記載なし）` | 6 | UNKNOWN |

⚠️ **「不明」を「○」に畳みません。**取引条件表に「ネット販売」の行そのものが無い企業があります。

⚠️ **この表は SD の表です。**NETSEA の仕入れ先はここに載っていないので、
`verdict()` は `None`（＝この表の対象外）を返します。NETSEA 側の同等物は
`deal_net_shop_flag == 'Y'`（`discover.scan_suppliers` が 0トークンで落としている）です。
**載っていないことを「×」とも「○」とも読まないこと**（無いことを根拠にしない）。

企業名はこの表の照合と「購入元の名前」欄までの用途に留めます（名簿化して外部連絡はしない）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CACHE = REPO / "workspace/output/agent_output/T-20260920-003/pipeline/sd_trading_terms.json"

SHEET_ID = "14VnMuvVDYNFlP0uer5y9E2atXnKbNWEHsGMrKk_xl68"
TAB = "SD取引条件"

OK = "○"
NG = "×"
NEEDS_CHECK = "要確認"

# 法人格・記号を落として名寄せする（`maker_direct` と同じ考え方）。
_LEGAL = ("株式会社", "有限会社", "合同会社", "合資会社", "合名会社", "一般社団法人",
          "Co.,Ltd.", "Co., Ltd.", "Co.Ltd", "CO.,LTD", "Inc.", "Ltd.", "LLC", "K.K.")


def normalize(name: str | None) -> str:
    """名寄せ用の鍵。空文字は「照合できない」の意味で、`verdict()` は None を返します。"""
    s = unicodedata.normalize("NFKC", str(name or ""))
    for w in _LEGAL:
        s = s.replace(w, "")
    s = re.sub(r"[\s　・\-−—–_．.,、。「」『』【】\[\]()（）/／]", "", s)
    return s.lower()


def classify(verdict_cell: str | None) -> str:
    """シートの `判定` セル → `○` / `×` / `要確認` の3値。

    セルの文字列は人が書き換える可能性があるので、**先頭1文字だけに頼りません。**
    """
    s = str(verdict_cell or "").strip()
    if not s:
        return NEEDS_CHECK
    if s.startswith("×") or "不可" in s:
        return NG
    if s.startswith("○") and "要確認" not in s and "不明" not in s:
        return OK
    return NEEDS_CHECK          # 「要確認（△…）」「不明（記載なし）」はここ


def _rows_from_sheet() -> list[dict]:
    import supplier_catalog                    # 同じフォルダ。認証をここで作り直さない
    ws = supplier_catalog._client().open_by_key(SHEET_ID).worksheet(TAB)
    values = ws.get_all_values()
    if not values:
        return []
    head = {name: i for i, name in enumerate(values[0])}
    need = ("dealer_id", "出展企業名", "判定")
    missing = [c for c in need if c not in head]
    if missing:
        raise RuntimeError(f"{TAB} タブに必要な列がありません: {missing}（列構成が変わりました）")
    out = []
    for r in values[1:]:
        if len(r) <= head["判定"]:
            continue
        out.append({"dealer_id": r[head["dealer_id"]].strip(),
                    "name": r[head["出展企業名"]].strip(),
                    "verdict_raw": r[head["判定"]].strip(),
                    "verdict": classify(r[head["判定"]])})
    return out


_MEMO: dict = {}


def load(refresh: bool = False, path: Path = CACHE) -> dict:
    """`{"by_id": {...}, "by_name": {...}, "counts": {...}}`。

    シートに触らずに使えるよう `agent_output/` にキャッシュします（夜間走行はネットワークが
    細いので、毎波シートを読みに行かない）。`refresh=True` で取り直します。

    🔴 **表が読めなかったときは例外を投げず、`unavailable` を立てた空の表を返します。**
    そして `verdict()` は「載っていない」ではなく「**表を読めていない**」を返します。
    この2つを混ぜると、ネットワークが死んだ晩に全件 ○ 扱いで走ります
    （「無いこと」と「見られないこと」を同一視する型の事故。CLAUDE.md §3.3-11）。
    """
    if not refresh and _MEMO.get("data") is not None:
        return _MEMO["data"]
    if not refresh and path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            _MEMO["data"] = d
            return d
        except (OSError, ValueError):
            pass
    try:
        rows = _rows_from_sheet()
    except Exception as e:                             # noqa: BLE001 - 読めないことを返す
        d = {"by_id": {}, "by_name": {}, "counts": {}, "total": 0,
             "unavailable": f"SD取引条件の表を読めませんでした: {e}"}
        _MEMO["data"] = d
        return d
    data = {
        "by_id": {r["dealer_id"]: r for r in rows if r["dealer_id"]},
        "by_name": {normalize(r["name"]): r for r in rows if r["name"]},
        "counts": {v: sum(1 for r in rows if r["verdict"] == v) for v in (OK, NG, NEEDS_CHECK)},
        "total": len(rows),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    _MEMO["data"] = data
    return data


def verdict(supplier_name: str | None = None, dealer_id: str | None = None,
            table: dict | None = None) -> tuple[str | None, str]:
    """`(○ / × / 要確認 / None, 人が読める理由)`。

    **None は「この表の対象外」**で、「○」でも「×」でもありません。
    NETSEA の仕入れ先はここに載っていないので必ず None になります。
    """
    t = table if table is not None else load()
    if t.get("unavailable"):
        # **「載っていない」ではなく「見られていない」。**混ぜると全件 ○ 扱いで走ります。
        return NEEDS_CHECK, t["unavailable"]
    if dealer_id:
        r = (t.get("by_id") or {}).get(str(dealer_id).strip())
        if r:
            return r["verdict"], f"SD取引条件（dealer {dealer_id}）: {r['verdict_raw']}"
    key = normalize(supplier_name)
    if key:
        r = (t.get("by_name") or {}).get(key)
        if r:
            return r["verdict"], f"SD取引条件（{r['name']}）: {r['verdict_raw']}"
    return None, ("SD取引条件の表に載っていません"
                  "（この表は SD の163社ぶん。NETSEA の先は対象外です）。"
                  "**載っていないことを ○ とも × とも読みません。**")


def gate(source: str | None, supplier_name: str | None = None,
         dealer_id: str | None = None, table: dict | None = None) -> tuple[str, str]:
    """候補1行に掛けるゲート。戻り値は `("PASS"|"FAIL"|"UNKNOWN", 理由)`。

    - SD 由来の行（`source` に `sd` を含む）… `○` だけ PASS。`×` は FAIL、それ以外は UNKNOWN
    - それ以外（NETSEA 由来など）… この表の対象外なので PASS
      （NETSEA 側は `deal_net_shop_flag == 'Y'` で 0トークンで落としてあります）
    """
    t = table if table is not None else load()
    v, why = verdict(supplier_name, dealer_id, t)
    is_sd = "sd" in str(source or "").lower() or "スーパーデリバリー" in str(source or "")
    if not is_sd:
        if t.get("unavailable"):
            # NETSEA の先はこの表に載っていないので、表が読めなくても判定は変わらない。
            return "PASS", ("NETSEA 由来のため SD取引条件の対象外です"
                            f"（なお表は読めていません: {t['unavailable']}）。")
        if v == NG:
            # SD 由来でなくても、同じ企業が × と判っているなら拾う（名寄せが当たった場合）。
            return "FAIL", why + " ／ SD 以外の経路でも、この企業は Amazon 不可です。"
        return "PASS", ("NETSEA 由来のため SD取引条件の対象外です"
                        "（ネット販売可のフラグは取得時に確認済み）。")
    if v == OK:
        return "PASS", why
    if v == NG:
        return "FAIL", why
    if v == NEEDS_CHECK:
        return "UNKNOWN", why + " ／ △・記載なしは個別に確認が必要です。"
    return "UNKNOWN", why + " ／ SD 由来なのに表に無いので、取引条件を確認してください。"


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="SD取引条件の表を取り込む／引く")
    ap.add_argument("--refresh", action="store_true", help="シートから取り直す")
    ap.add_argument("names", nargs="*", help="引きたい企業名")
    a = ap.parse_args()
    t = load(refresh=a.refresh)
    print(f"{TAB}: {t['total']}社 / 内訳 {t['counts']}")
    for n in a.names:
        v, why = verdict(n, table=t)
        print(f"  {n} → {v}  {why}")
