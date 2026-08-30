"""常駐ジョブのガード条件のテスト（T-20260831-002）。

**「暴走しない」は口約束ではなく、ここで固定します。**
実際の Keepa は一切叩きません（スキャナ呼び出しを差し替えます）。

    python3 -m pytest test_always_on.py -q
"""
from __future__ import annotations

import json

import pytest

import always_on as ao
import cycle_state as cs


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """出力先を tmp に、スキャナ呼び出しとロールアップを偽物に差し替える。"""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    v14 = tmp_path / "v14"
    v14.mkdir()

    monkeypatch.setattr(ao, "STATE_DIR", state_dir)
    monkeypatch.setattr(ao, "STATE_FILE", state_dir / "cycle.json")
    monkeypatch.setattr(ao, "LOG", state_dir / "always_on.log")
    monkeypatch.setattr(ao, "STOP_FILE", v14 / "STOP")
    monkeypatch.setattr(ao, "PROGRESS", v14 / "progress.json")
    monkeypatch.setattr(ao, "SCAN_LOG", v14 / "scan_v14.log")
    monkeypatch.setattr(ao, "DAILY_DIR", tmp_path / "daily")

    bands = [f"band{i}" for i in range(3)]
    monkeypatch.setattr(ao, "all_bands", lambda: bands)

    calls = {"scan": 0, "rollup": 0}
    outcome = {"value": {"ok": True, "exhausted": [], "processed": 120,
                         "go": 80, "tokens": 1000, "stop_reason": "時間"}}

    def fake_scan(skip):
        calls["scan"] += 1
        calls["last_skip"] = list(skip)
        return outcome["value"]

    monkeypatch.setattr(ao, "run_scanner", fake_scan)
    monkeypatch.setattr(ao, "run_rollup", lambda: calls.__setitem__("rollup", calls["rollup"] + 1))
    monkeypatch.setattr(ao, "sleep_interruptible", lambda s: None)
    monkeypatch.setattr(ao, "free_gb", lambda: 200.0)

    return type("Box", (), {"tmp": tmp_path, "v14": v14, "state_dir": state_dir,
                            "calls": calls, "outcome": outcome, "bands": bands})


def read_state(sandbox) -> dict:
    return json.loads((sandbox.state_dir / "cycle.json").read_text(encoding="utf-8"))


# --- 暴走防止 ---------------------------------------------------------------
def test_stop_file_prevents_the_scanner_from_running(sandbox):
    """STOP ファイル1つで止まる。これが社長に案内している唯一の止め方。"""
    (sandbox.v14 / "STOP").write_text("stop")
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 0


def test_low_disk_prevents_the_scanner_from_running(sandbox, monkeypatch):
    """ディスクを食い潰さない。空きが下限を割ったら走らない。"""
    monkeypatch.setattr(ao, "free_gb", lambda: 1.0)
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 0


def test_halted_state_prevents_the_scanner_from_running(sandbox):
    """自動停止したら、次に人が見るまで走らない。"""
    ao.save_state(dict(cs.new_state(__import__("datetime").datetime.now()),
                       halted="テスト用の自動停止"))
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 0


def test_cooldown_prevents_the_scanner_from_running(sandbox):
    """1周し切ったあとは走らない（走っても新規0件でトークンを焼くだけ）。"""
    import datetime as dt
    now = dt.datetime.now()
    s = cs.new_state(now)
    cs.note_session(s, {"ok": True, "exhausted": sandbox.bands, "processed": 10,
                        "go": 5, "tokens": 100, "stop_reason": ""}, sandbox.bands, now)
    ao.save_state(s)
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 0


# --- 正常系 -----------------------------------------------------------------
def test_a_normal_session_runs_and_records_progress(sandbox):
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 1
    st = read_state(sandbox)
    assert st["totals"]["processed"] == 120
    assert st["sessions"] == 1
    assert st["halted"] is None


def test_exhausted_bands_are_passed_to_the_scanner_as_skips(sandbox):
    """2回目のセッションでは掘り切った帯を渡す＝Finder のトークンを払わない。"""
    sandbox.outcome["value"] = {"ok": True, "exhausted": ["band1"], "processed": 50,
                                "go": 30, "tokens": 500, "stop_reason": ""}
    ao.loop(once=True)
    assert sandbox.calls["last_skip"] == []
    ao.loop(once=True)
    assert sandbox.calls["last_skip"] == ["band1"]


def test_rollup_runs_once_a_day(sandbox):
    ao.loop(once=True)
    ao.loop(once=True)
    assert sandbox.calls["rollup"] == 1     # 同じ日なら2回目は走らない


# --- 結果の読み取り ----------------------------------------------------------
def test_a_stale_progress_file_counts_as_a_failed_session(sandbox):
    """progress.json が更新されていない = スキャナが何も残さず落ちた、と扱う。

    ここを甘くすると、落ち続けているのに「正常」と記録され、自動停止が働きません。
    """
    p = sandbox.v14 / "progress.json"
    p.write_text(json.dumps({"counts": {"processed": 999}}), encoding="utf-8")
    res = ao.read_session_result(p.stat().st_mtime, 0)
    assert res["ok"] is False
    assert res["processed"] == 0


def test_a_fresh_progress_file_is_parsed(sandbox):
    p = sandbox.v14 / "progress.json"
    before = 0.0
    p.write_text(json.dumps({
        "counts": {"processed": 300, "go": 200},
        "keepa": {"tokens_consumed": 2580},
        "cursor": {"exhausted": ["band0"]},
        "stop_reason": "通算 6.0 時間に達しました",
    }, ensure_ascii=False), encoding="utf-8")
    res = ao.read_session_result(before, 0)
    assert res == {"ok": True, "exhausted": ["band0"], "processed": 300,
                   "go": 200, "tokens": 2580,
                   "stop_reason": "通算 6.0 時間に達しました"}


def test_a_corrupt_state_file_does_not_kill_the_job(sandbox):
    """状態ファイルが壊れても止まらない。作り直して走り続ける。"""
    (sandbox.state_dir / "cycle.json").write_text("{ これは JSON ではない", encoding="utf-8")
    ao.loop(once=True)
    assert sandbox.calls["scan"] == 1
