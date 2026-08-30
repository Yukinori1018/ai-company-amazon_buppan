"""周回状態の純ロジック（T-20260831-002）。

常時稼働の一番難しいところは「母数が枯れる」ことです。同じ条件を回し続けると
`seen_asins.txt` が全部弾いて、**新規0件のままトークンだけ焼く**。

ここはその制御だけを持つモジュールです。**ファイル I/O も API 呼び出しもしません。**
だから全部テストできます（`test_cycle_state.py`）。実際に走らせるのは `always_on.py`。

## 周回の考え方

    1周 = 全シャード（価格帯25本）を掘り切るまで
      ↓ 掘り切った
    クールダウン（既定7日）… 走らない。Keepa の母集団に新商品が入るのを待つ
      ↓ 明けた
    次の周へ。cursors をリセットし、exhausted を空にする
      → `seen_asins.txt` は消さないので、2周目以降に積まれるのは**本当の新規だけ**

再訪は無駄ではありません。`salesRankDrops30` は直近30日の指標なので、
条件に入ってくる商品が毎週入れ替わります。ただし**取れる数は必ず減る**ので、
「新規獲得率」を毎日記録して、下がったら警告を出します（＝条件見直しの合図）。
条件そのものを緩めるのは社長判断（仕入れ方針 v1.3 の変更）なので、機械は警告までです。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

# --- 設定（ここだけ見れば挙動が分かる）------------------------------------
REVISIT_COOLDOWN_DAYS = 7        # 1周し切ったあと、次の周まで空ける日数
MAX_CONSECUTIVE_ERRORS = 5       # スキャナが連続でこれだけ異常終了したら自動停止
MAX_ZERO_NEW_SESSIONS = 8        # 新規0件のセッションがこれだけ続いたら自動停止
LOW_YIELD_PER_1K = 20.0          # 1000トークンあたりの新規取得件数がこれを割ったら警告
HEALTHY_YIELD_PER_1K = 116.0     # 実測 8.6トークン/件 → 116件/1000トークンが健全値

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
        "cooldown_until": None,
        "exhausted": {},          # band ラベル -> 掘り切った時刻
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
def note_session(state: dict, result: dict, all_bands: list, now: dt.datetime,
                 cooldown_days: int = REVISIT_COOLDOWN_DAYS) -> dict:
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
        start_cooldown(state, now, cooldown_days)
    elif (state["zero_new_sessions"] >= MAX_ZERO_NEW_SESSIONS
            and not state.get("halted")):
        state["halted"] = (f"新規0件のセッションが{state['zero_new_sessions']}回続きました。"
                           "抽出条件が母数を取れなくなっている可能性があります")
    return state


def start_cooldown(state: dict, now: dt.datetime, days: int = REVISIT_COOLDOWN_DAYS) -> dict:
    """1周し切った。次の周まで走らない（走っても新規0件でトークンを焼くだけ）。"""
    state["cooldown_until"] = now_iso(now + dt.timedelta(days=days))
    state["totals"]["cycles_completed"] = state["totals"].get("cycles_completed", 0) + 1
    return state


def maybe_start_new_cycle(state: dict, now: dt.datetime) -> bool:
    """クールダウンが明けていたら次の周を始める。始めたら True。

    `exhausted` を空にするだけで `seen_asins.txt` は触りません。
    だから2周目に積まれるのは **前回以降にKeepaの母集団へ入ってきた商品だけ**です。
    """
    until = parse_iso(state.get("cooldown_until"))
    if until is None or now < until:
        return False
    state["cooldown_until"] = None
    state["exhausted"] = {}
    state["cycle"] = state.get("cycle", 1) + 1
    state["cycle_started_at"] = now_iso(now)
    state["zero_new_sessions"] = 0
    return True


def pause_reason(state: dict, now: dt.datetime) -> Optional[str]:
    """今このセッションを走らせるべきでないなら理由を返す。走ってよいなら None。"""
    if state.get("halted"):
        return f"自動停止中: {state['halted']}"
    until = parse_iso(state.get("cooldown_until"))
    if until and now < until:
        rest = until - now
        return (f"周回クールダウン中（{state['totals'].get('cycles_completed', 0)}周完了・"
                f"あと {rest.days}日{rest.seconds // 3600}時間）")
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
