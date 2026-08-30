"""周回ロジックのテスト（T-20260831-002）。

常時稼働で一番怖いのは「壊れていることに誰も気づかないまま何日も回る」ことです。
だから **止まるべきときに止まる** ことと、**飛ばすべき帯を飛ばす** ことを固定します。

    python3 -m pytest test_cycle_state.py -q
"""
from __future__ import annotations

import datetime as dt

import cycle_state as cs

BANDS = [f"band{i}" for i in range(5)]
T0 = dt.datetime(2026, 9, 1, 10, 0, 0)


def result(ok=True, exhausted=(), processed=100, go=70, tokens=860, reason=""):
    return {"ok": ok, "exhausted": list(exhausted), "processed": processed,
            "go": go, "tokens": tokens, "stop_reason": reason}


def test_exhausted_bands_are_skipped_next_session():
    """掘り切った帯は次のセッションで Finder を叩かない（1帯20トークンの無駄を消す）。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=["band0", "band2"]), BANDS, T0)
    assert cs.skip_bands(s, BANDS) == ["band0", "band2"]


def test_finishing_every_band_stops_and_says_so():
    """★2026-08-31 社長判断。母数が尽きたら止まって「尽きた」と言って終わる。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS), BANDS, T0)
    assert cs.cycle_complete(s, BANDS)
    assert s["exhausted_at"]
    assert "掘り尽くしました" in s["halted"]
    assert "掘り尽くしました" in cs.pause_reason(s, T0)


def test_exhaustion_survives_a_restart_and_does_not_re_explore():
    """★これが無いと KeepAlive が10秒ごとに25シャードを再探索し、
    1日28,800トークンを新規0件のために焼き続けます。"""
    import json
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS), BANDS, T0)
    after_restart = json.loads(json.dumps(s, ensure_ascii=False))     # プロセス再起動を模す
    assert cs.pause_reason(after_restart, T0 + dt.timedelta(days=30)) is not None
    assert cs.skip_bands(after_restart, BANDS) == BANDS


def test_only_an_explicit_instruction_restarts_the_research():
    """再開は社長の指示だけ。時間の経過では絶対に再開しない。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS), BANDS, T0)
    much_later = T0 + dt.timedelta(days=365)
    assert cs.pause_reason(s, much_later) is not None       # 1年経っても止まったまま

    cs.resume_research(s, much_later)
    assert s["cycle"] == 2
    assert s["exhausted"] == {}
    assert s["halted"] is None
    assert cs.skip_bands(s, BANDS) == []
    assert cs.pause_reason(s, much_later) is None


def test_consecutive_errors_halt_the_job():
    """壊れたまま回り続けない。連続異常終了で自分から止まる。"""
    s = cs.new_state(T0)
    for _ in range(cs.MAX_CONSECUTIVE_ERRORS):
        cs.note_session(s, result(ok=False, processed=0, tokens=0), BANDS, T0)
    assert s["halted"]
    assert "異常終了" in s["halted"]
    assert "停止中" in cs.pause_reason(s, T0)


def test_one_success_resets_the_error_counter():
    s = cs.new_state(T0)
    for _ in range(cs.MAX_CONSECUTIVE_ERRORS - 1):
        cs.note_session(s, result(ok=False, processed=0, tokens=0), BANDS, T0)
    cs.note_session(s, result(), BANDS, T0)
    assert s["consecutive_errors"] == 0
    assert s["halted"] is None


def test_zero_new_sessions_halt_the_job():
    """正常終了でも新規0件が続くなら、母数が取れていない。止めて報告する。"""
    s = cs.new_state(T0)
    for _ in range(cs.MAX_ZERO_NEW_SESSIONS):
        cs.note_session(s, result(processed=0, go=0, tokens=500), BANDS, T0)
    assert s["halted"]
    assert "新規0件" in s["halted"]


def test_exhaustion_is_reported_as_exhaustion_not_as_an_error():
    """掘り切りは「異常」ではない。停止理由に必ず「掘り尽くした」と書く。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS, processed=0, tokens=500), BANDS, T0)
    assert "掘り尽くしました" in s["halted"]
    assert "異常" not in s["halted"]


def test_yield_warning_fires_only_when_the_pool_dries_up():
    healthy = cs.new_state(T0)
    cs.note_session(healthy, result(processed=100, tokens=860), BANDS, T0)
    assert cs.yield_warning(healthy) is None          # 116件/1000tok

    dry = cs.new_state(T0)
    cs.note_session(dry, result(processed=5, tokens=1000), BANDS, T0)
    assert "新規獲得率が落ちています" in cs.yield_warning(dry)


def test_yield_per_1k_is_none_without_token_spend():
    assert cs.yield_per_1k({"processed": 0, "tokens": 0}) is None
    assert cs.yield_per_1k({"processed": 100, "tokens": 1000}) == 100.0


def test_daily_totals_accumulate_across_sessions():
    s = cs.new_state(T0)
    cs.note_session(s, result(processed=100, go=70, tokens=860), BANDS, T0)
    cs.note_session(s, result(processed=150, go=90, tokens=1290), BANDS,
                    T0 + dt.timedelta(hours=6))
    today = s["daily"]["2026-09-01"]
    assert today == {"processed": 250, "go": 160, "tokens": 2150, "sessions": 2}
    assert s["totals"]["processed"] == 250


def test_state_survives_a_json_round_trip():
    """状態はプロセス再起動をまたぐ。JSON で往復して壊れないこと。"""
    import json
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=["band1"]), BANDS, T0)
    again = json.loads(json.dumps(s, ensure_ascii=False))
    assert cs.skip_bands(again, BANDS) == ["band1"]
    assert cs.pause_reason(again, T0) is None
