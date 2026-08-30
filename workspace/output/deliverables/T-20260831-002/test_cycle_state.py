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


def test_finishing_every_band_starts_a_cooldown_instead_of_spinning():
    """全帯を掘り切ったら、走り続けずにクールダウンへ入る（新規0件でトークンを焼かない）。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS), BANDS, T0)
    assert cs.cycle_complete(s, BANDS)
    assert s["cooldown_until"] is not None
    assert "クールダウン" in cs.pause_reason(s, T0)


def test_cooldown_blocks_then_a_new_cycle_starts():
    """クールダウン中は走らない。明けたら掘り切りの印が消えて次の周が始まる。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS), BANDS, T0)

    still = T0 + dt.timedelta(days=cs.REVISIT_COOLDOWN_DAYS - 1)
    assert cs.maybe_start_new_cycle(s, still) is False
    assert cs.pause_reason(s, still) is not None

    after = T0 + dt.timedelta(days=cs.REVISIT_COOLDOWN_DAYS, seconds=1)
    assert cs.maybe_start_new_cycle(s, after) is True
    assert s["cycle"] == 2
    assert s["exhausted"] == {}
    assert cs.skip_bands(s, BANDS) == []
    assert cs.pause_reason(s, after) is None


def test_consecutive_errors_halt_the_job():
    """壊れたまま回り続けない。連続異常終了で自分から止まる。"""
    s = cs.new_state(T0)
    for _ in range(cs.MAX_CONSECUTIVE_ERRORS):
        cs.note_session(s, result(ok=False, processed=0, tokens=0), BANDS, T0)
    assert s["halted"]
    assert "異常終了" in s["halted"]
    assert "自動停止中" in cs.pause_reason(s, T0)


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


def test_completing_a_cycle_is_not_mistaken_for_a_failure():
    """掘り切りは「異常」ではない。クールダウンに入るだけで halted にはしない。"""
    s = cs.new_state(T0)
    cs.note_session(s, result(exhausted=BANDS, processed=0, tokens=500), BANDS, T0)
    assert s["halted"] is None
    assert s["cooldown_until"] is not None


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
