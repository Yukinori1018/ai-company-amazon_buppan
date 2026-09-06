#!/usr/bin/env python3
"""母数を新条件（⓪①②③）で検証し、通過分を逐次書き出す夜間ハーネス。

■ 何をするか
  T-20260906-002 で決めた条件を、既存の母数 26,942 件に当てる。

    ⓪ 観測回数ゲート : Keepa が30日で20回以上ランクを見ていること
    ①  ドロップ数     : 30日で 5 以上（社長裁可 X=5）
    ②  カート最終獲得 : 直近30日以内に実セラーがカートを取っていること
    ③  カート不在率   : 直近30日で 0.30 以下

  ①はローカルの keepa_facts.jsonl（既存キャッシュ）で無料で判定できる。
  ⓪は履歴が要るので 1 token/件、②③は offers が要るので約 6.5 token/件。
  **だから2段構えにする。**

■ 中断しても続きから
  評価が終わった ASIN は verified.jsonl に**1件ずつ追記**する。
  再起動時はそれを読んで済んだぶんを飛ばす。全件やり直しはしない。
  ★「取得 → 評価 → 書き出し → 済み印」の順を守る（済み印を先に付けると、
    落ちたときに行が無いのに二度と拾われない）。

■ 止まり方
  1. STOP ファイルがある      → 起動を断る / 走行中なら安全停止
  2. トークンが下限を割った   → 異常終了せず回復を待つ（他の作業を巻き添えにしない）
  3. 通算時間の上限
  4. 全件終わった            → FINISHED を置く
"""
import argparse, gzip, json, os, signal, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
REPO = HERE.parent.parent.parent.parent          # …/ai-company-amazon_buppan
SRC = REPO / "workspace/output/deliverables/T-20260831-006/out"
ENV = REPO / "workspace/output/agent_output/T-20260521-005/code/.env"

VERIFIED = OUT / "verified.jsonl"      # 1行1ASIN。これがチェックポイントそのもの
PASSED = OUT / "passed.jsonl"          # 条件を通ったものだけ（朝、未完走でも候補が組める）
PROGRESS = OUT / "progress.json"
HEARTBEAT = OUT / "heartbeat.json"
LOG = OUT / "run.log"
STOP = HERE / "STOP"
FINISHED = HERE / "FINISHED"

# --- 条件のパラメータ（社長裁可。変えるときはチケットに理由を書くこと）---
MIN_OBS_30 = 20        # ⓠ
MIN_DROPS_30 = 5       # ①
BB_LAST_DAYS = 30      # ②
BB_ABSENT_MAX = 0.30   # ③

# --- トークン運用 ---
TOKEN_FLOOR = 150      # ここを割ったら手を出さない。他の作業ぶんを残す
S1_BATCH = 50          # 1周 ≒ 50 token ≒ 2.5分
S2_BATCH = 20          # 1周 ≒ 130 token ≒ 6.5分（監視できる長さに収める）
KEEPA_EPOCH_MIN = 21564000
DAY = 24 * 60

_stop = False


def log(msg):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def api_key():
    k = os.environ.get("KEEPA_API_KEY")
    if k:
        return k
    for line in open(ENV):
        if line.startswith("KEEPA_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("KEEPA_API_KEY が無い")


def _raw(path, params, timeout=300):
    q = urllib.parse.urlencode(dict(params, key=api_key(), domain=5))
    req = urllib.request.Request(f"https://api.keepa.com/{path}?{q}",
                                 headers={"Accept-Encoding": "gzip"})
    b = urllib.request.urlopen(req, timeout=timeout).read()
    return json.loads(gzip.decompress(b) if b[:2] == b"\x1f\x8b" else b)


def call(path, params, label, tries=6):
    """リトライ＋指数バックオフ。1件の失敗で全体を落とさない。"""
    for i in range(tries):
        try:
            return _raw(path, params)
        except urllib.error.HTTPError as e:
            body = e.read()[:200]
            if e.code == 402:
                log(f"!! HTTP 402 契約が無効（{label}）。リトライしても直らないので停止する")
                raise SystemExit(2)
            wait = min(30 * (2 ** i), 600)
            log(f"   {label} HTTP {e.code} → {wait}s 待って再試行 ({i+1}/{tries}) {body}")
        except Exception as e:
            wait = min(30 * (2 ** i), 600)
            log(f"   {label} 通信エラー {e} → {wait}s 待って再試行 ({i+1}/{tries})")
        if _sleep(wait):
            break
    log(f"   {label} は {tries} 回失敗した。この束は飛ばして次へ進む")
    return {}


def tokens_left():
    d = call("token", {}, "token残高", tries=3)
    return d.get("tokensLeft")


def _sleep(sec):
    """止めろと言われたら即座に返る sleep。True なら停止要求。"""
    end = time.time() + sec
    while time.time() < end:
        if _stop or STOP.exists():
            return True
        time.sleep(min(5, max(0, end - time.time())))
    return _stop or STOP.exists()


def wait_for_tokens(need, label):
    """枯渇しても異常終了しない。回復（20/分）を待つ。下限バッファは常に残す。"""
    while True:
        if _stop or STOP.exists():
            return False
        left = tokens_left()
        if left is None:
            if _sleep(60):
                return False
            continue
        if left - need >= TOKEN_FLOOR:
            return True
        short = need + TOKEN_FLOOR - left
        wait = min(900, max(60, int(short / 20 * 60)))
        beat({"state": "トークン待ち", "tokensLeft": left, "need": need,
              "waitSec": wait, "label": label})
        log(f"   トークン {left}（必要 {need}+下限 {TOKEN_FLOOR}）→ {wait}s 待つ")
        if _sleep(wait):
            return False


def beat(extra=None):
    d = {"ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    d.update(extra or {})
    HEARTBEAT.write_text(json.dumps(d, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- 判定ロジック
def obs30(p, now_km):
    sr = (p.get("csv") or [None] * 4)[3]
    if not sr:
        return 0
    return sum(1 for t in sr[0::2] if t >= now_km - 30 * DAY)


def buybox(p, now_km):
    """(最後に実セラーがカートを取った日数前, 直近30日の不在率)。

    Keepa の約束事: "-1"=カート無し / "-2"=資格なし / それ以外=実セラーID
    """
    h = p.get("buyBoxSellerIdHistory") or []
    ts, ids = h[0::2], h[1::2]
    if not ts:
        return None, None
    last = None
    for t, sid in zip(ts, ids):
        if sid not in ("-1", "-2"):
            last = int(t)
    cut = now_km - 30 * DAY
    absent = total = 0
    for k in range(30):
        at = cut + k * DAY
        sid = None
        for t, s in zip(ts, ids):
            if int(t) <= at:
                sid = s
            else:
                break
        if sid is None:
            continue
        total += 1
        if sid in ("-1", "-2"):
            absent += 1
    return ((now_km - last) / DAY if last else None,
            absent / total if total else None)


# ---------------------------------------------------------------- 本体
def load_done():
    """verified.jsonl から (stage1済み, stage2済み) を復元する。

    ★段ごとに別の辞書に入れること。1つの辞書に asin をキーで入れると、
      後から書かれた stage2 の行が stage1 の行を上書きしてしまい、
      再開のたびに stage1 を取り直す（1件1トークンの無駄が毎回出る）。
    """
    d1, d2 = {}, {}
    if VERIFIED.exists():
        for line in VERIFIED.open():
            try:
                r = json.loads(line)
            except Exception:
                continue      # 途中で落ちて千切れた最終行は捨てる
            (d1 if r.get("stage") == 1 else d2)[r["asin"]] = r
    return d1, d2


def append(path, rec):
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def build_queue():
    """①をローカルで当てて、API を掛ける対象だけを作る。

    ①（ドロップ数）は既存キャッシュ keepa_facts.jsonl で判定できる＝**無料**。
    ここで 26,942 → 数千に落ちるので、API 予算はそのぶん②③に回せる。
    """
    facts = {}
    for line in (SRC / "keepa_facts.jsonl").open():
        try:
            r = json.loads(line)
            facts[r["asin"]] = r
        except Exception:
            pass
    import csv
    rows = list(csv.DictReader((SRC / "candidates.csv").open(encoding="utf-8-sig")))

    def num(x):
        try:
            return float((x or "").replace(",", "").replace("%", ""))
        except Exception:
            return None

    q = []
    for r in rows:
        a = r.get("ASIN")
        if not a:
            continue
        f = facts.get(a) or {}
        if (f.get("drops30") or 0) < MIN_DROPS_30:
            continue                       # ① で落とす（無料）
        if not (r.get("Amazon価格") or "").strip():
            continue                       # 価格が取れない＝採算が出せない
        q.append((a, num(r.get("利益率%")) if num(r.get("利益率%")) is not None else -999))
    # ★利益率の高い順に処理する。朝までに完走しなくても、
    #   一番使える候補から順に埋まっているようにするため。
    q.sort(key=lambda x: -x[1])
    seen, order = set(), []
    for a, _ in q:
        if a not in seen:
            seen.add(a)
            order.append(a)
    return order


def stage1(chunk, done):
    """ⓠ観測回数を取る（1 token/件）。①はローカルで済ませてある。

    **1ブロックだけ**処理して返る。ブロック単位で stage2 まで通すことで、
    朝までに完走しなくても「上位から順に完全に検証済み」の状態を作る。
    """
    now_km = int(time.time() / 60) - KEEPA_EPOCH_MIN
    chunk = [a for a in chunk if a not in done]
    if chunk:
        if not wait_for_tokens(len(chunk) + 5, "stage1"):
            return False
        d = call("product", {"asin": ",".join(chunk), "stats": 365}, "stage1")
        got = {p["asin"]: p for p in d.get("products", [])}
        for a in chunk:
            p = got.get(a)
            if p is None:
                rec = {"asin": a, "stage": 1, "ok": False, "why": "取得できず"}
            else:
                s = p.get("stats") or {}
                n30 = obs30(p, now_km)
                dr = s.get("salesRankDrops30")
                ok = n30 >= MIN_OBS_30 and (dr or 0) >= MIN_DROPS_30
                rec = {"asin": a, "stage": 1, "ok": ok, "n30": n30,
                       "drops_ok": (dr or 0) >= MIN_DROPS_30,
                       "why": None if ok else ("⓪観測回数不足" if n30 < MIN_OBS_30
                                               else "①ドロップ数不足")}
            append(VERIFIED, rec)       # ← 書いてから済み印（順序が命）
            done[a] = rec
    return True


def stage2(cands, done2):
    """②③を取る（offers=20&buybox=1。約 6.5 token/件）。**1ブロックずつ**返る。"""
    now_km = int(time.time() / 60) - KEEPA_EPOCH_MIN
    todo = [a for a in cands if a not in done2]
    for i in range(0, len(todo), S2_BATCH):
        if _stop or STOP.exists():
            return False
        chunk = todo[i:i + S2_BATCH]
        if not wait_for_tokens(int(len(chunk) * 6.5) + 10, "stage2"):
            return False
        d = call("product", {"asin": ",".join(chunk), "stats": 365,
                             "offers": 20, "buybox": 1}, "stage2")
        got = {p["asin"]: p for p in d.get("products", [])}
        for a in chunk:
            p = got.get(a)
            if p is None:
                rec = {"asin": a, "stage": 2, "ok": False, "why": "取得できず"}
            else:
                days, rate = buybox(p, now_km)
                c2 = days is not None and days <= BB_LAST_DAYS
                c3 = rate is not None and rate <= BB_ABSENT_MAX
                why = None if (c2 and c3) else (
                    "②カート最終獲得が古い" if not c2 else "③カート不在率が高い")
                rec = {"asin": a, "stage": 2, "ok": c2 and c3,
                       "bb_last_days": None if days is None else round(days, 1),
                       "bb_absent": None if rate is None else round(rate, 3),
                       "is_child": bool(p.get("parentAsin"))
                                   or (p.get("variationCount") or 0) > 1,
                       "why": why}
            append(VERIFIED, rec)
            if rec["ok"]:
                append(PASSED, rec)     # ★通過分は逐次。朝、未完走でも候補が組める
            done2[a] = rec
    return True


def main():
    global _stop
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-hours", type=float, default=11.0)
    ap.add_argument("--limit", type=int, default=0, help="対象を先頭 N 件に絞る（試走用）")
    a = ap.parse_args()

    if STOP.exists():
        print(f"STOP ファイルがあります: {STOP}\n"
              f"走らせたいなら消してください:  rm '{STOP}'")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    FINISHED.unlink(missing_ok=True)

    def onsig(*_):
        global _stop
        _stop = True
        log("!! 停止シグナルを受けた。区切りまで進めて終わる")
    signal.signal(signal.SIGTERM, onsig)
    signal.signal(signal.SIGINT, onsig)

    t0 = time.time()
    queue = build_queue()
    if a.limit:
        queue = queue[:a.limit]
    log(f"=== 開始 === ①ローカル通過 {len(queue):,} 件が API 検証の対象 "
        f"(ⓠ>={MIN_OBS_30} / ①>={MIN_DROPS_30} / ②<={BB_LAST_DAYS}日 / ③<={BB_ABSENT_MAX})")

    d1, d2 = load_done()
    log(f"再開: stage1 済み {len(d1):,} / stage2 済み {len(d2):,}")

    # ★ブロック単位で stage1 → stage2 まで通し切る。
    #   全件 stage1 を先に回すと、一番使いたい上位の候補が
    #   最後まで②③未検証のまま残る（朝、使える候補がゼロになる）。
    ok = True
    for bi in range(0, len(queue), S1_BATCH):
        if _stop or STOP.exists():
            ok = False
            log("!! 停止要求。ここまでの結果は全て書き出し済み")
            break
        if (time.time() - t0) / 3600 >= a.max_hours:
            ok = False
            log(f"!! 通算 {a.max_hours}h に達した。安全に終わる")
            break
        block = queue[bi:bi + S1_BATCH]
        if not stage1(block, d1):
            ok = False
            break
        cands = [x for x in block if d1.get(x, {}).get("ok")]
        if cands and not stage2(cands, d2):
            ok = False
            break
        n_pass = sum(1 for r in d2.values() if r.get("ok"))
        done_n = min(bi + S1_BATCH, len(queue))
        beat({"state": "走行中", "検証済み": done_n, "母数": len(queue),
              "①⓪通過": sum(1 for r in d1.values() if r.get("ok")),
              "最終通過": n_pass,
              "経過h": round((time.time() - t0) / 3600, 2)})
        PROGRESS.write_text(json.dumps(
            {"母数": len(queue), "検証済み": done_n,
             "stage1通過": sum(1 for r in d1.values() if r.get("ok")),
             "stage2実施": len(d2), "最終通過": n_pass,
             "経過h": round((time.time() - t0) / 3600, 2),
             "完走": False}, ensure_ascii=False, indent=2))
        log(f"[{done_n:,}/{len(queue):,}] ⓠ①通過={len(cands)}/{len(block)} "
            f"最終通過累計={n_pass} 経過={(time.time()-t0)/3600:.2f}h")

    n_pass = sum(1 for r in d2.values() if r.get("ok"))
    PROGRESS.write_text(json.dumps(
        {"母数": len(queue), "検証済み": len(d1),
         "stage1通過": sum(1 for r in d1.values() if r.get("ok")),
         "stage2実施": len(d2), "最終通過": n_pass,
         "経過h": round((time.time() - t0) / 3600, 2),
         "完走": bool(ok)}, ensure_ascii=False, indent=2))
    log(f"=== 終了 === 最終通過 {n_pass} 件 / 検証済み {len(d1):,}/{len(queue):,} "
        f"/ 経過 {(time.time()-t0)/3600:.2f}h / 完走={ok}")
    # ★--limit を付けた試走で FINISHED を書いてはいけない。
    #   監督ループは FINISHED を見て起動を見送るので、
    #   試走の置き土産が本番の夜間走行をまるごと止めてしまう（実際に踏んだ）。
    if ok and not a.limit:
        FINISHED.write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    beat({"state": "終了", "passed": n_pass, "completed": bool(ok)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
