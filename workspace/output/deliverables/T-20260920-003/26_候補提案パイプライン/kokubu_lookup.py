#!/usr/bin/env python3
"""問屋 国分ネット卸（netton.kokubu.jp）の商品ページを、Amazon 起点の JAN で1件ずつ引く。

2026-10-12 サトル（T-20260920-003）。法務判定50「条件つき可」の §5 をそのまま実装した。

守っている条件（法務判定50 §5 の番号）
  1  間隔 10秒以上・同時1
  2  1日の総リクエスト数の永続カウンタ（日付キー・プロセスをまたいで積算）。開始500回/日
  3  段階的な引き上げ：停止トリガが14日連続で出なければ1,000→2,000回/日（天井）
  5  照会順は呼び出し側が「売れている順」に並べて渡す
  6  停止トリガ：403/429/5xx/タイムアウト30秒/応答がその日の中央値の3倍超/
     CAPTCHA・ログイン要求・アクセス制限の画面 → その日は打ち切り
  7  再開：翌日は間隔2倍・回数半分。7日内2回目→7日停止。3回目→打ち切り（国分には連絡しない）
  8  同じ JAN の再取得は7日に1回まで
  9  冒頭で規約と robots.txt を取得し、前回とハッシュが違えばその日は実行しない
  10 名乗る UA（ブラウザを装わない）
  11 取る項目：商品名・JAN・入数・値段（税抜・バラ・推奨売価）・賞味期限・取り寄せ表示。画像・説明文は取らない
  13 取得ログ（URL・時刻・間隔・応答コード・UA）を全件記録
  14 「無し」と「取得失敗」を分ける（存在しない JAN も 200 で返るので中身で判定）

やらないこと：ログインしたセッション・検索窓の裏の外部検索サービス・推測した検索引数・JAN の総当たり・
TLS 指紋の偽装・酒類の照会（呼び出し側で除外）。

🔴 値段は会員制卸の取引条件として扱う。出力は agent_output にだけ置く（PUBLIC リポ）。

使い方
    python3 kokubu_lookup.py <JAN を1行1件で並べたファイル（売れている順）>
"""
from __future__ import annotations

import gzip
import hashlib
import html as H
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

WORK = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260920-003/kokubu")
STATE = WORK / "state.json"          # カウンタ・トリガ履歴・規約ハッシュ
LOG = WORK / "access_log.jsonl"      # 条件13
OUT = WORK / "lookup.jsonl"          # 結果（JAN ごと・追記）
RAW = WORK / "raw"                   # 生 HTML（gzip）
BASE = "https://netton.kokubu.jp"
UA = "SatoySelect-lookup/1.0 (wholesale catalog check; contact: satoyselect@gmail.com)"
INTERVAL0, DAILY_STEPS = 10.0, (500, 1000, 2000)


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {"days": {}, "triggers": [], "terms_hash": None, "level": 0, "backoff": 0,
            "halted": False, "last_fetch": {}}


def save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1))


def log(rec: dict) -> None:
    with LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def get(url: str, last: list[float], interval: float) -> tuple[int, bytes, float]:
    wait = interval - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    code, body = 0, b""
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, body = e.code, b""
    except Exception as e:   # タイムアウト・接続失敗
        code, body = -1, str(e).encode()
    dt = time.time() - t0
    last[0] = time.time()
    log({"t": datetime.now().isoformat(timespec="seconds"), "url": url, "code": code,
         "sec": round(dt, 2), "interval": interval, "ua": UA})
    return code, body, dt


def text(b: bytes) -> str:
    for enc in ("cp932", "utf-8"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("cp932", "replace")


BLOCK_WORDS = ("captcha", "アクセスが制限", "アクセス制限", "ログインしてください", "Access Denied")


def blocked(t: str) -> bool:
    low = t.lower()
    return any(w.lower() in low for w in BLOCK_WORDS)


def _strip(x: str) -> str:
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def _yen(x: str):
    m = re.search(r"([\d,]+)", H.unescape(x or "").replace("\uffe5", "").replace("\u00a5", ""))
    return int(m.group(1).replace(",", "")) if m else None


def parse(t: str, jan: str) -> dict:
    """商品ページ（2026-10-12 実測の構造）から条件11の項目だけ取る。"""
    h1 = re.search(r'<h1 class="goods_name_">(.*?)</h1>', t, re.S)
    name = _strip(re.sub(r'<span class="reduce_tax">.*?</span>', "", h1.group(1), flags=re.S)) if h1 else ""
    path = re.search(r'<div class="navitopicpath_">(.*?)</div>', t, re.S)
    cat = _strip(path.group(1)).replace("問屋 国分ネット卸：トップ", "").strip(" >") if path else ""
    spec = {}
    for th, td in re.findall(r"<th>(.*?)</th>\s*<td[^>]*>(.*?)</td>", t, re.S):
        k = _strip(th).rstrip(":： ").strip()
        spec.setdefault(k, []).append(_strip(td))
    code = (spec.get("JANコード") or [""])[0]
    case = _yen((spec.get("販売価格(税抜)") or [""])[0])
    bara = _yen((spec.get("販売価格バラ(税抜)") or [""])[0])
    btn = re.search(r'<div class="buttons_">(.*?)</div>', t, re.S)
    btn = btn.group(1) if btn else ""
    rec = {"jan": jan, "name": name, "category": cat, "JANコード": code,
           "販売価格(税抜)": case, "販売価格バラ(税抜)": bara,
           "入数(販売価格÷バラ)": (round(case / bara) if case and bara else None),
           "推奨売価(税抜)": (spec.get("推奨売価(税抜)") or [""])[0],
           "サイズ(バラ)": (spec.get("サイズ(バラ)") or [""])[0],
           "賞味期限": (spec.get("賞味期限") or [""])[0],
           "買物かごボタン": "買物かごへ" in btn,
           "取り寄せボタン": "取り寄せ" in btn,
           "在庫": ("在庫あり" if "買物かごへ" in btn else "取り寄せ" if "取り寄せ" in btn
                   else "品切れ（在庫お問合せ）" if "在庫お問合せ" in btn else "不明"),
           "酒類": bool(re.search(r"酒|ビール|ワイン|焼酎|リキュール", cat))}
    if name and code:
        rec["status"] = "有り"
    elif not name and not code:
        rec["status"] = "無し"          # 存在しない JAN も 200 で空ページ（条件14）
    else:
        rec["status"] = "取得失敗"      # 片方だけ取れた＝構造が違う。「無し」に畳まない
    return rec


def run(jans: list[str]) -> dict:
    WORK.mkdir(parents=True, exist_ok=True)
    s = load_state()
    today = date.today().isoformat()
    if s.get("halted"):
        return {"結果": "打ち切り済み（停止トリガ3回）。秘書に報告済みのはず。再開しない"}
    if s.get("stop_until") and today < s["stop_until"]:
        return {"結果": f"{s['stop_until']} まで停止中（条件7）"}
    if s["days"].get(today, {}).get("tripped"):
        return {"結果": "本日は停止トリガが出たので再試行しない（条件6）"}
    # 条件3・7：その日の上限と間隔
    recent = [d for d in s["triggers"] if d >= (date.today() - timedelta(days=14)).isoformat()]
    level = s.get("level", 0)
    first = min(s["days"]) if s["days"] else today
    if not recent and (date.fromisoformat(today) - date.fromisoformat(first)).days >= 14 * (level + 1):
        level = min(level + 1, len(DAILY_STEPS) - 1)
    s["level"] = level
    back = s.get("backoff", 0)
    interval = INTERVAL0 * (2 ** back)
    cap = int(DAILY_STEPS[level] / (2 ** back))
    day = s["days"].setdefault(today, {"count": 0, "times": [], "tripped": False})
    last = [0.0]

    def trip(why: str) -> dict:
        day["tripped"] = True
        s["triggers"].append(today)
        wk = [d for d in s["triggers"] if d >= (date.today() - timedelta(days=7)).isoformat()]
        s["backoff"] = back + 1
        if len(wk) >= 3:
            s["halted"] = True
        elif len(wk) == 2:
            s["stop_until"] = (date.today() + timedelta(days=7)).isoformat()
        save_state(s)
        return {"結果": f"停止トリガ：{why}。本日は打ち切り", "照会": day["count"]}

    # 条件9：規約と robots.txt の変更検知
    if day["count"] == 0 and not day.get("terms_checked"):
        hs = []
        for u in (BASE + "/shop/contents3/agreement.aspx", BASE + "/robots.txt"):
            code, body, dt = get(u, last, interval)
            day["count"] += 1
            if code in (403, 429) or code >= 500 or code == -1:
                return trip(f"{u} が {code}")
            digest = hashlib.sha256(re.sub(rb"\s+", b"", body)).hexdigest() if code == 200 else ""
            hs.append(f"{code}:{digest}")
        h = "|".join(hs)
        if s.get("terms_hash") and s["terms_hash"] != h:
            save_state(s)
            return {"結果": "規約か robots.txt が前回と違う。本日は実行しない（条件9）・秘書に報告"}
        s["terms_hash"] = h
        day["terms_checked"] = True
        save_state(s)

    done = {}
    for line in OUT.open() if OUT.exists() else []:
        o = json.loads(line)
        done[o["jan"]] = o.get("fetched_day", "")
    n_new = 0
    for jan in jans:
        if day["count"] >= cap:
            break
        prev = done.get(jan)
        if prev and prev >= (date.today() - timedelta(days=7)).isoformat():
            continue        # 条件8
        url = f"{BASE}/shop/g/g{jan}/"
        code, body, dt = get(url, last, interval)
        day["count"] += 1
        day["times"].append(round(dt, 2))
        if code in (403, 429) or code >= 500 or code == -1:
            return trip(f"{jan} の応答 {code}")
        med = statistics.median(day["times"]) if len(day["times"]) >= 5 else None
        if med and dt > 3 * med and dt > 2:
            return trip(f"応答 {dt:.1f}秒（中央値 {med:.1f}秒の3倍超）")
        t = text(body)
        if code == 200:   # 条件12：生 HTML は agent_output にだけ（90日で整理・削除は §4.1）
            RAW.mkdir(parents=True, exist_ok=True)
            (RAW / f"{jan}.html.gz").write_bytes(gzip.compress(body))
        if blocked(t):
            return trip("アクセス制限・ログイン要求の画面")
        rec = parse(t, jan) if code == 200 else {"jan": jan, "status": "取得失敗", "code": code}
        rec["fetched_day"] = today
        rec["fetched"] = datetime.now().isoformat(timespec="seconds")
        with OUT.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        n_new += 1
        if n_new % 10 == 0:
            save_state(s)
    # 7日間トリガが出なければ1段戻す
    if back and not [d for d in s["triggers"] if d >= (date.today() - timedelta(days=7)).isoformat()]:
        s["backoff"] = back - 1
    save_state(s)
    return {"結果": "完了", "本日の照会": day["count"], "上限": cap, "間隔": interval, "今回の新規": n_new}


if __name__ == "__main__":
    jans = [x.strip() for x in Path(sys.argv[1]).read_text().split() if re.fullmatch(r"\d{8,13}", x.strip())]
    print(json.dumps(run(jans), ensure_ascii=False, indent=1))
