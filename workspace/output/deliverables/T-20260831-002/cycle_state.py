"""周回状態の純ロジック（T-20260831-002）。

常時稼働の一番難しいところは「母数が枯れる」ことです。同じ条件を回し続けると
`seen_asins.txt` が全部弾いて、**新規0件のままトークンだけ焼く**。

ここはその制御だけを持つモジュールです。**ファイル I/O も API 呼び出しもしません。**
だから全部テストできます（`test_cycle_state.py`）。実際に走らせるのは `always_on.py`。

## 掘り切ったらどうするか（2026-08-31 社長判断）

> 「尽きたら、尽きたと言って、リサーチを終了してもらって結構です。
>   そのあとは、任意のタイミングで、リサーチを指示します。」

つまり **自動で再訪しません。** 全シャードを掘り切ったら停止し、そう報告して終わります。
再開は社長の明示的な指示（`list-builder.sh resume-research`）だけです。

    全シャードを掘り切った
      ↓
    halted に「母数を掘り尽くしました」を書いて停止
      ↓ **再起動しても再探索を始めない**（exhausted を状態ファイルに永続化してあるため）
    社長の再開指示 → exhausted を空にして次の周へ
      → `seen_asins.txt` は消さないので、次の周に積まれるのは**本当の新規だけ**

`exhausted` をメモリ上だけに持つと、launchd の KeepAlive が再起動するたびに
25シャードを頭から探索し直し、**1日28,800トークンを新規0件のために焼き続けます**。
だからここは必ずディスクへ書きます。

## 「掘り切った」と書いてよいのは正常な0件のときだけ

API エラーを掘り切りと記録すると、**「尽きました」という報告そのものが嘘になります。**
区別は `scan_v14.py` の Finder 呼び出し側で行い、障害時は `ALERT` を書いて止まります。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

# --- 設定（ここだけ見れば挙動が分かる）------------------------------------
MAX_CONSECUTIVE_ERRORS = 5       # スキャナが連続でこれだけ異常終了したら自動停止
MAX_ZERO_NEW_SESSIONS = 8        # 新規0件のセッションがこれだけ続いたら自動停止
LOW_YIELD_PER_1K = 20.0          # 1000トークンあたりの新規取得件数がこれを割ったら警告
HEALTHY_YIELD_PER_1K = 116.0     # 実測 8.6トークン/件 → 116件/1000トークンが健全値
# S2: 1セッション（6時間）走って **新規候補0件なのにトークンを3,000以上焼いた** ら止める。
# 「動いているが無価値」を放置しないための線。掘り切り（＝クールダウン）とは別物。
BURN_TOKENS_WITHOUT_RESULT = 3000
# S1: 24時間の新規取得がこれを割ったら「探索は終わった」とみなして警告を出す
LOW_INTAKE_PER_DAY = 200

ISO = "%Y-%m-%dT%H:%M:%S"


def now_iso(now: dt.datetime) -> str:
    return now.strftime(ISO)


def parse_iso(text: Optional[str]) -> Optional[dt.datetime]:
    if not text:
        return None
    try:
        return dt.datetime.strptime(text, ISO)
    except ValueError:
        return None


def new_state(now: dt.datetime) -> dict:
    return {
        "ticket": "T-20260831-002",
        "cycle": 1,
        "cycle_started_at": now_iso(now),
        "exhausted": {},          # band ラベル -> 掘り切った時刻（★必ず永続化する）
        "exhausted_at": None,     # 全シャードを掘り切った時刻
        "halted": None,           # 自動停止の理由。None なら稼働中
        "sessions": 0,
        "consecutive_errors": 0,
        "zero_new_sessions": 0,
        "last_rollup_date": None,
        "totals": {"processed": 0, "tokens": 0, "cycles_completed": 0},
        "daily": {},              # "YYYY-MM-DD" -> {processed, go, tokens, sessions}
    }


# --- どのシャードを飛ばすか -------------------------------------------------
def skip_bands(state: dict, all_bands: list) -> list:
    """今の周ですでに掘り切ったシャード。scan_v14 に --skip-bands で渡す。

    飛ばさないと、セッションのたびに全25帯の Finder を引き直して
    1帯20トークン × 25 = 500トークン（＝25分ぶん）を無駄にします。
    """
    done = set(state.get("exhausted") or {})
    return [b for b in all_bands if b in done]


def cycle_complete(state: dict, all_bands: list) -> bool:
    done = set(state.get("exhausted") or {})
    return bool(all_bands) and set(all_bands) <= done


# --- セッション1回ぶんの反映 -------------------------------------------------
def note_session(state: dict, result: dict, all_bands: list, now: dt.datetime) -> dict:
    """スキャナ1セッションの結果を状態に畳み込む。

    result: {"ok": bool, "exhausted": [band...], "processed": int,
             "go": int, "tokens": int, "stop_reason": str}
    """
    state["sessions"] = state.get("sessions", 0) + 1

    if result.get("ok"):
        state["consecutive_errors"] = 0
    else:
        state["consecutive_errors"] = state.get("consecutive_errors", 0) + 1
        if state["consecutive_errors"] >= MAX_CONSECUTIVE_ERRORS:
            state["halted"] = (f"スキャナが{state['consecutive_errors']}回連続で異常終了しました"
                               f"（最後の理由: {result.get('stop_reason') or '不明'}）")

    exhausted = dict(state.get("exhausted") or {})
    for band in result.get("exhausted") or []:
        exhausted.setdefault(band, now_iso(now))
    state["exhausted"] = exhausted

    processed = int(result.get("processed") or 0)
    tokens = int(result.get("tokens") or 0)
    day = now.strftime("%Y-%m-%d")
    d = state.setdefault("daily", {}).setdefault(
        day, {"processed": 0, "go": 0, "tokens": 0, "sessions": 0})
    d["processed"] += processed
    d["go"] += int(result.get("go") or 0)
    d["tokens"] += tokens
    d["sessions"] += 1

    totals = state.setdefault("totals", {"processed": 0, "tokens": 0, "cycles_completed": 0})
    totals["processed"] = totals.get("processed", 0) + processed
    totals["tokens"] = totals.get("tokens", 0) + tokens

    # 新規0件が続いたら「壊れたまま回り続けている」可能性。掘り切り（周回完了）とは別物。
    if processed == 0 and result.get("ok"):
        state["zero_new_sessions"] = state.get("zero_new_sessions", 0) + 1
    else:
        state["zero_new_sessions"] = 0

    if cycle_complete(state, all_bands):
        mark_exhausted(state, now)
    elif (result.get("ok") and int(result.get("go") or 0) == 0
            and tokens > BURN_TOKENS_WITHOUT_RESULT and not state.get("halted")):
        # S2: 走ってはいるが何も生んでいない。トークンを焼いているだけ。
        state["halted"] = (f"1セッションで新規候補0件のままトークンを{tokens}消費しました"
                           f"（S2: 上限{BURN_TOKENS_WITHOUT_RESULT}）。"
                           "母数が枯れたか、抽出条件が何も拾えなくなっています")
    elif (state["zero_new_sessions"] >= MAX_ZERO_NEW_SESSIONS
            and not state.get("halted")):
        state["halted"] = (f"新規0件のセッションが{state['zero_new_sessions']}回続きました。"
                           "抽出条件が母数を取れなくなっている可能性があります")
    return state


def mark_exhausted(state: dict, now: dt.datetime) -> dict:
    """母数を掘り尽くした。**止まって、そう報告して終わる。**（2026-08-31 社長判断）

    自動で再訪はしません。再開は社長の明示的な指示だけです。
    """
    state["exhausted_at"] = now_iso(now)
    state["totals"]["cycles_completed"] = state["totals"].get("cycles_completed", 0) + 1
    total = state["totals"].get("processed", 0)
    state["halted"] = (
        f"母数を掘り尽くしました（{state.get('cycle', 1)}周目・全シャード完了・"
        f"このジョブでの取得 {total}件）。リサーチを終了します。"
        "再開は社長の指示で `list-builder.sh resume-research`")
    return state


def resume_research(state: dict, now: dt.datetime) -> dict:
    """社長の指示で次の周を始める。**このコマンドでしか再探索は始まりません。**

    `exhausted` を空にするだけで `seen_asins.txt` は触りません。
    だから次の周に積まれるのは **前回以降に Keepa の母集団へ入ってきた商品だけ**です。
    """
    state["exhausted"] = {}
    state["exhausted_at"] = None
    state["halted"] = None
    state["consecutive_errors"] = 0
    state["zero_new_sessions"] = 0
    state["cycle"] = state.get("cycle", 1) + 1
    state["cycle_started_at"] = now_iso(now)
    return state


def pause_reason(state: dict, now: dt.datetime) -> Optional[str]:
    """今このセッションを走らせるべきでないなら理由を返す。走ってよいなら None。"""
    if state.get("halted"):
        return f"停止中: {state['halted']}"
    return None


# --- 新規獲得率 -------------------------------------------------------------
def yield_per_1k(day: dict) -> Optional[float]:
    """1000トークンあたり何件の新規商品を取れたか。母数が枯れると0へ近づく。"""
    tokens = int(day.get("tokens") or 0)
    if tokens <= 0:
        return None
    return round(int(day.get("processed") or 0) / tokens * 1000, 1)


def daily_report(state: dict, days: int = 7) -> list:
    """直近 days 日の日次サマリ（新しい順）。"""
    out = []
    for key in sorted(state.get("daily", {}), reverse=True)[:days]:
        d = state["daily"][key]
        out.append({"date": key, "processed": d.get("processed", 0),
                    "go": d.get("go", 0), "tokens": d.get("tokens", 0),
                    "yield_per_1k": yield_per_1k(d), "sessions": d.get("sessions", 0)})
    return out


def intake_warning(state: dict, threshold: int = LOW_INTAKE_PER_DAY) -> Optional[str]:
    """直近の丸1日の新規取得が細ったら知らせる（＝母数の底が近い）。

    止めはしません。止めるのは「全シャード掘り切り」か S2/S3/S5 です。
    """
    rows = daily_report(state, days=3)
    if len(rows) < 2:            # 丸1日ぶんのデータが揃うまでは判断しない
        return None
    full_day = rows[1]           # 直近の「終わった日」
    if full_day["processed"] >= threshold:
        return None
    return (f"新規取得が細っています（{full_day['date']}: {full_day['processed']}件・"
            f"目安 {threshold}件）。探索フェーズは実質終わりです。"
            "巡回モード（鮮度の古い順に取り直す）への切替か、抽出条件の見直しが要ります")


def yield_warning(state: dict, threshold: float = LOW_YIELD_PER_1K) -> Optional[str]:
    """新規獲得率が落ちていたら警告文。健全なら None。

    「枯れているのに回し続ける」のが最悪なので、ここで必ず声を上げます。
    条件そのものを緩めるかどうかは社長判断（仕入れ方針 v1.3 の変更）です。
    """
    rows = [r for r in daily_report(state, days=3) if r["yield_per_1k"] is not None]
    if not rows:
        return None
    latest = rows[0]
    if latest["yield_per_1k"] >= threshold:
        return None
    return (f"新規獲得率が落ちています（{latest['date']}: "
            f"{latest['yield_per_1k']}件/1000トークン・健全値 {HEALTHY_YIELD_PER_1K}）。"
            "母数が枯れかけています。抽出条件の見直し（価格帯の拡張・drops下限の緩和・"
            "COUNT_NEW帯の拡張）を検討してください＝社長判断です")
