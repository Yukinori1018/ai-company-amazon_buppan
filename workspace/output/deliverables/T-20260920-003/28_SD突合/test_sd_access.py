#!/usr/bin/env python3
"""SD への取得の縛りを**ネットワークなしで**検査する。

    python3 test_sd_access.py

何を守っているかを、ここだけ読んで分かるようにしてあります。

    1. 間隔が守られること（待ち時間を記録して検査）
    2. 1日の上限・1セッションの上限で止まること
    3. 🔴 **429 を1件の失敗として飲み込まないこと**（同型を2日で2回踏んだ）
    4. 429 でその日が打ち切られ、**同日中は再開しないこと**
    5. 翌日は間隔が倍になり、最上段で止まること
    6. 429 なしが連続3日で1段戻ること（2日では戻らないこと）
    7. 日付が変わると回数が戻り、**間隔は戻らないこと**
    8. **プロセスを再起動しても回数・間隔・打ち切りが戻らないこと**
    9. 上限を引数で緩める口が無いこと／全件スキャン（レーンC）の口が無いこと
   10. 通信の指紋を偽装するライブラリに触っていないこと
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _backoff                                                      # noqa: E402
import _budget                                                       # noqa: E402
import _fetch                                                        # noqa: E402
import sd_dealer_index                                               # noqa: E402
import sd_dealer_terms                                               # noqa: E402
import sd_jan_lookup                                                 # noqa: E402
from _budget import (LANE_A, LANE_B, Budget, BudgetExceeded, DayCutOff,  # noqa: E402
                     NotAttended, SessionLimitReached)

FAILS: list[str] = []
COUNT = 0


def ok(cond, msg: str) -> None:
    global COUNT
    COUNT += 1
    if cond:
        print(f"  ok   {msg}")
    else:
        print(f"  FAIL {msg}")
        FAILS.append(msg)


def section(title: str) -> None:
    print(f"\n── {title}")


class Clock:
    """時計と sleep を差し替える。**実際には1秒も待たない。**"""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.t = start
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, sec: float) -> None:
        self.slept.append(sec)
        self.t += sec


def budget(dirpath, *, lane=LANE_A, today="2026-10-01", clock=None):
    clock = clock or Clock()
    b = Budget(dirpath, attended=True, lane=lane, today=today,
               sleep=clock.sleep, now=clock.now)
    b.clock = clock                      # テストから覗くためだけ
    return b


# ─────────────────────────────────────────────────────────────────────────────


def test_suspension_released() -> None:
    section("停止フラグ")
    ok(_budget.SUSPENDED is False, "SUSPENDED は解除されている（2026-10-01・秘書カズヨ）")
    src = open(os.path.join(HERE, "_budget.py"), encoding="utf-8").read()
    ok("解除者 ＝ 秘書カズヨ" in src, "解除者がコメントに書かれている")
    ok("T-20260920-003" in src and "2026-10-01" in src, "根拠チケットと解除日が書かれている")


def test_lane_constants() -> None:
    section("レーンの上限（定数）")
    ok((LANE_A.max_per_day, LANE_A.base_interval) == (30, 10.0),
       "レーンA = 1日30件・間隔10.0秒")
    ok(LANE_A.max_per_session == 0, "レーンAにセッション上限は無い")
    ok((LANE_B.max_per_day, LANE_B.base_interval, LANE_B.max_per_session) == (50, 3.0, 20),
       "レーンB = 1日50・1セッション20・間隔3.0秒")
    ok(_backoff.steps_for(10.0) == [10.0, 20.0, 40.0, 80.0, 160.0],
       "レーンAの段は 10→20→40→80→160 秒")
    ok(_backoff.steps_for(3.0) == [3.0, 6.0, 12.0, 24.0, 48.0],
       "レーンBの段は 3→6→12→24→48 秒")


def test_attended_required() -> None:
    section("在席の必須")
    with tempfile.TemporaryDirectory() as d:
        try:
            Budget(d, attended=False, lane=LANE_A, today="2026-10-01")
            ok(False, "--attended なしは例外になる")
        except NotAttended:
            ok(True, "--attended なしは NotAttended で止まる（無人運転不可）")
        rc = sd_jan_lookup.main(["--jan", "4901234567894", "--state-dir", d])
        ok(rc == 1, "sd_jan_lookup は --attended なしで終了コード1（1件も投げない）")
        ok(not os.listdir(d), "カウンタファイルすら作らない")


def test_interval_enforced() -> None:
    section("間隔")
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        b = budget(d, clock=clock)
        b.take()
        ok(clock.slept == [], "1件目は待たない")
        b.take()
        ok(clock.slept == [10.0], "2件目は10.0秒待つ")
        clock.t += 4.0                                   # 外で4秒経った
        b.take()
        ok(abs(clock.slept[-1] - 6.0) < 1e-6, "外で4秒経っていれば残りの6.0秒だけ待つ")
        clock.t += 60.0
        b.take()
        ok(len(clock.slept) == 2, "間隔より長く空いていれば待たない")


def test_daily_cap() -> None:
    section("1日の上限")
    with tempfile.TemporaryDirectory() as d:
        b = budget(d)
        for _ in range(30):
            b.take()
        ok(b.remaining == 0, "30件で残り0")
        try:
            b.take()
            ok(False, "31件目は例外")
        except BudgetExceeded:
            ok(True, "31件目は BudgetExceeded（待っても今日は増えない）")


def test_session_cap_lane_b() -> None:
    section("1セッションの上限（レーンB）")
    with tempfile.TemporaryDirectory() as d:
        b = budget(d, lane=LANE_B)
        for _ in range(20):
            b.take()
        try:
            b.take()
            ok(False, "21件目は例外")
        except SessionLimitReached:
            ok(True, "21件目は SessionLimitReached（1日の上限はまだ残っている）")
        ok(b.remaining == 30, "1日の上限は 50-20=30 残っている")
        b2 = budget(d, lane=LANE_B)                     # 新しいセッション
        b2.take()
        ok(b2.session_used == 1 and b2.remaining == 29,
           "セッションを分ければ続けられる（1日の残りは引き継ぐ）")


def test_429_is_not_swallowed() -> None:
    section("🔴 429 を1件の失敗として飲み込まない")
    calls = []

    def opener(req, timeout=0):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    try:
        _fetch.fetch("https://example.invalid/x", opener=opener)
        ok(False, "429 は例外になる")
    except _fetch.RateLimited:
        ok(True, "429 は専用の RateLimited（Failed に混ぜない）")
    except _fetch.Failed:
        ok(False, "429 が Failed に落ちている＝1件の失敗として飲み込まれる")
    ok(len(calls) == 1, "429 で自動リトライしない（1回しか叩かない）")

    calls.clear()

    def opener503(req, timeout=0):
        calls.append(req.full_url)
        raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, None)

    try:
        _fetch.fetch("https://example.invalid/x", opener=opener503)
        ok(False, "503 は例外になる")
    except _fetch.RateLimited:
        ok(True, "503 も RateLimited（相手が止めてくれと言っている扱い）")
    ok(len(calls) == 1, "503 でも自動リトライしない")

    def opener404(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    try:
        _fetch.fetch("https://example.invalid/x", opener=opener404)
        ok(False, "404 は例外になる")
    except _fetch.RateLimited:
        ok(False, "404 を RateLimited にしてはいけない")
    except _fetch.Failed:
        ok(True, "404 は Failed（こちらは1件ぶんの失敗）")

    def ok200(req, timeout=0):
        return io.BytesIO("<html>ok</html>".encode())

    ok(_fetch.fetch("https://example.invalid/x", opener=ok200) == "<html>ok</html>",
       "200 は本文を返す")


def test_day_cut_off_and_step_up() -> None:
    section("429 → その日は打ち切り・翌日は倍")
    with tempfile.TemporaryDirectory() as d:
        b = budget(d, today="2026-10-01")
        b.take()
        nxt = b.note_rate_limited()
        ok(nxt == 20.0, "429 で間隔が 10.0 → 20.0 に上がる")
        try:
            b.take()
            ok(False, "打ち切った後に take できてはいけない")
        except DayCutOff:
            ok(True, "打ち切り後の take は DayCutOff")
        try:
            budget(d, today="2026-10-01")
            ok(False, "同日に再起動して再開できてはいけない")
        except DayCutOff:
            ok(True, "**同日中はプロセスを再起動しても再開しない**")

        b2 = budget(d, today="2026-10-02")
        ok(b2.interval == 20.0, "翌日は間隔20.0秒で再開できる")
        ok(b2.remaining == 30, "翌日は回数が30に戻る")
        b2.note_rate_limited()
        ok(budget(d, today="2026-10-03").interval == 40.0, "もう1度429で40.0秒")
        for day, want in (("2026-10-03", 80.0), ("2026-10-04", 160.0), ("2026-10-05", 160.0)):
            bb = budget(d, today=day)
            bb.note_rate_limited()
            ok(bb.interval == want, f"{day} の429で間隔 {want} 秒（最上段で止まる）")
        ok(budget(d, today="2026-10-06").interval == 160.0, "最上段 160 秒を超えない")


def test_step_down_after_three_clean_days() -> None:
    section("429 なしが連続3日 → 1段戻す")
    with tempfile.TemporaryDirectory() as d:
        b = budget(d, today="2026-10-01")
        b.take()
        b.note_rate_limited()
        b2 = budget(d, today="2026-10-02")
        b2.take()
        b2.note_rate_limited()
        ok(budget(d, today="2026-10-03").interval == 40.0, "前提：間隔は40.0秒まで上がった")

        for day in ("2026-10-03", "2026-10-04"):
            bb = budget(d, today=day)
            bb.take()
            ok(bb.finish() is False, f"{day}：きれいな日2日までは段を戻さない")
        ok(budget(d, today="2026-10-05").interval == 40.0, "2日では 40.0 秒のまま")

        b5 = budget(d, today="2026-10-05")
        b5.take()
        ok(b5.finish() is True, "3日目で段を戻す")
        ok(budget(d, today="2026-10-06").interval == 20.0, "40.0 → 20.0 秒に1段だけ戻る")

        # 同じ日に2回走っても二重計上しない
        b6 = budget(d, today="2026-10-06")
        b6.take()
        b6.finish()
        again = budget(d, today="2026-10-06")
        again.take()
        again.finish()
        state = json.load(open(os.path.join(d, LANE_A.backoff_path_name), encoding="utf-8"))
        ok(state["clean_days"] == 1, "同じ日に2回走っても きれいな日は1日ぶんしか数えない")

        # 走らなかった日は数えない（＝ take が0件なら finish は何もしない）
        idle = budget(d, today="2026-10-07")
        ok(idle.finish() is False, "1件も走らなかった日は数えない")
        state = json.load(open(os.path.join(d, LANE_A.backoff_path_name), encoding="utf-8"))
        ok(state["clean_days"] == 1, "走っていない日は何の証拠にもならない")


def test_429_resets_clean_days() -> None:
    section("429 はきれいな日の数え直し")
    with tempfile.TemporaryDirectory() as d:
        b = budget(d, today="2026-10-01")
        b.take()
        b.note_rate_limited()                             # 20.0 秒へ
        for day in ("2026-10-02", "2026-10-03"):
            bb = budget(d, today=day)
            bb.take()
            bb.finish()
        b4 = budget(d, today="2026-10-04")
        b4.take()
        b4.note_rate_limited()                            # 40.0 秒へ・clean_days は 0 に
        state = json.load(open(os.path.join(d, LANE_A.backoff_path_name), encoding="utf-8"))
        ok(state["clean_days"] == 0, "429 が出たら きれいな日の連続は 0 に戻る")
        for day in ("2026-10-05", "2026-10-06"):
            bb = budget(d, today=day)
            bb.take()
            bb.finish()
        ok(budget(d, today="2026-10-07").interval == 40.0,
           "429 のあとは改めて3日続かないと戻らない")


def test_restart_restores_state() -> None:
    section("プロセス再起動後の復元")
    with tempfile.TemporaryDirectory() as d:
        clock = Clock()
        b = budget(d, today="2026-10-01", clock=clock)
        for _ in range(5):
            b.take()
        ok(b.remaining == 25, "5件使った")
        clock2 = Clock(start=clock.t + 1.0)               # 1秒後に別プロセスが起きた
        b2 = budget(d, today="2026-10-01", clock=clock2)
        ok(b2.remaining == 25, "**再起動しても使い切った回数は戻らない**")
        b2.take()
        ok(abs(clock2.slept[0] - 9.0) < 1e-6, "直前のリクエストからの経過も引き継ぐ（残り9秒待つ）")

    with tempfile.TemporaryDirectory() as d:
        b = budget(d, today="2026-10-01")
        b.take()
        b.note_rate_limited()
        ok(budget(d, today="2026-10-02").interval == 20.0,
           "**再起動しても間隔は10秒に戻らない**")


def test_handwritten_state_cannot_loosen() -> None:
    section("状態ファイルを手で書き換えても緩まない")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, LANE_A.backoff_path_name)
        json.dump({"base_interval": 10.0, "interval": 2.0}, open(path, "w"))
        ok(budget(d).interval == 10.0, "段より速い値（2.0秒）は base の10.0秒に戻される")
        json.dump({"base_interval": 10.0, "interval": 15.0}, open(path, "w"))
        ok(budget(d).interval == 20.0, "段の間の値（15.0秒）は**遅い側**の20.0秒に寄せる")
        json.dump({"base_interval": 10.0, "interval": 9999.0}, open(path, "w"))
        ok(budget(d).interval == 160.0, "段より遅い値は最上段に丸める")
        open(path, "w").write("{壊れた")
        ok(budget(d).interval == 10.0, "壊れていたら base から始める（例外で死なない）")

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, LANE_A.backoff_path_name)
        json.dump({"base_interval": 3.0, "interval": 6.0}, open(path, "w"))
        ok(budget(d).interval == 10.0, "別レーンの base が書かれていたら引き継がない")


def test_no_loosening_arguments() -> None:
    section("上限を引数で緩める口が無い")
    for mod, name in ((sd_jan_lookup, "sd_jan_lookup"),
                      (sd_dealer_terms, "sd_dealer_terms"),
                      (sd_dealer_index, "sd_dealer_index")):
        src = open(os.path.join(HERE, f"{name}.py"), encoding="utf-8").read()
        for bad in ("--sleep", "--max-per-day", "--interval", "--limit", "--no-attended"):
            ok(f'"{bad}"' not in src, f"{name} に {bad} が無い")
        ok("--attended" in src, f"{name} は --attended を要求する")


def test_no_full_scan_path() -> None:
    section("レーンC（全件スキャン）の口が無い")
    for name in ("sd_dealer_terms", "sd_dealer_index"):
        src = open(os.path.join(HERE, f"{name}.py"), encoding="utf-8").read()
        ok('"--dealers"' not in src, f"{name} に全社 TSV を渡す --dealers が無い")
        ok("approved_by_secretary" not in src, f"{name} に全件スキャン再開フラグが無い")
        ok('"--dealer-ids"' in src, f"{name} は対象を --dealer-ids で明示させる")
    ok(sd_dealer_terms.read_dealer_ids("12345, 67890 ,12345") == ["12345", "67890"],
       "--dealer-ids は重複を落として順番を保つ")


def code_only(path: str) -> str:
    """コメントと文字列リテラルを落として**実際のコードだけ**を返す。

    説明文で禁止手段の名前に触れることは許す（禁止の理由を書くために必要）。
    検査したいのは「実際に使っているか」なので、名前の出現だけで落とさない。
    """
    import tokenize
    out = []
    with open(path, "rb") as fh:
        for tok in tokenize.tokenize(fh.readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    return " ".join(out).lower()


def test_no_fingerprint_spoofing() -> None:
    section("🔴 通信の指紋を偽装しない（CLAUDE.md §3.3-14）")
    banned = ("curl_impersonate", "curl_cffi", "tls_client",
              "undetected_chromedriver", "selenium", "playwright", "ja3")
    for name in ("_fetch", "_budget", "_backoff",
                 "sd_jan_lookup", "sd_dealer_terms", "sd_dealer_index"):
        src = code_only(os.path.join(HERE, f"{name}.py"))
        hits = [b for b in banned if b in src]
        ok(not hits, f"{name}.py は指紋偽装の手段を使っていない"
                     + (f"（見つかった: {hits}）" if hits else ""))
        ok("subprocess" not in src,
           f"{name}.py は外部の HTTP クライアントをサブプロセスで呼ばない")


def test_lookup_stops_on_rate_limit() -> None:
    section("🔴 sd_jan_lookup は429で全体を止める（残りを投げない）")
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.jsonl")
        janfile = os.path.join(d, "jans.txt")
        open(janfile, "w").write("\n".join(f"49012345678{i:02d}" for i in range(5)))
        tried: list[str] = []

        def fake_fetch(url, **kw):
            tried.append(url)
            if len(tried) == 1:
                return ('<div class="itembox-parts"><div class="item-name">'
                        '<a href="/p/r/pd_p/1234567/">テスト商品</a></div>'
                        'registBtn/999999</div>')
            raise _fetch.RateLimited("SD が HTTP 429 を返しました（テスト）")

        real = sd_jan_lookup.fetch
        sd_jan_lookup.fetch = fake_fetch
        try:
            rc = sd_jan_lookup.main(
                ["--jan-file", janfile, "--out", out, "--attended", "--state-dir", d],
                sleep=lambda s: None)
        finally:
            sd_jan_lookup.fetch = real

        ok(rc == 5, "429 を踏んだ実行の終了コードは 5（0 ではない）")
        ok(len(tried) == 2, "429 が出たところで止まる（残り3件は投げない）")
        lines = [json.loads(l) for l in open(out, encoding="utf-8")]
        ok(len(lines) == 1, "429 の行は結果として書かない（0件に化けさせない）")
        ok(lines[0]["hit_count"] == 1 and lines[0]["hits"][0]["dealer_id"] == "999999",
           "ヒットした1件は正しく保存されている")
        state = json.load(open(os.path.join(d, LANE_A.backoff_path_name), encoding="utf-8"))
        ok(state["interval"] == 20.0, "間隔が20.0秒に上がっている")
        ok(state["last_429_date"], "429 の日付が記録されている")
        rc2 = sd_jan_lookup.main(
            ["--jan-file", janfile, "--out", out, "--attended", "--state-dir", d],
            sleep=lambda s: None)
        ok(rc2 == 5, "同じ日にもう一度起動しても 5 で止まる（同日中の再試行はしない）")


def test_lookup_clean_run() -> None:
    section("sd_jan_lookup の正常系（429 なし）")
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "out.jsonl")
        janfile = os.path.join(d, "jans.txt")
        open(janfile, "w").write("# コメント行\n4901234567894\n4901234567895\n")
        real = sd_jan_lookup.fetch
        sd_jan_lookup.fetch = lambda url, **kw: "<html>ヒットなし</html>"
        try:
            rc = sd_jan_lookup.main(
                ["--jan-file", janfile, "--out", out, "--attended", "--state-dir", d],
                sleep=lambda s: None)
        finally:
            sd_jan_lookup.fetch = real
        ok(rc == 0, "終了コード 0")
        ok(len(open(out, encoding="utf-8").read().strip().split("\n")) == 2,
           "コメント行を除いた2件ぶん書かれる")
        used = json.load(open(os.path.join(d, f"{LANE_A.label}_budget_"
                                          f"{_budget.datetime.date.today().isoformat()}.json"),
                              encoding="utf-8"))
        ok(used["used"] == 2, "回数カウンタが2件ぶん増えている")


def main() -> int:
    print("SD への取得の縛りを検査します（ネットワークには一切つなぎません）")
    for fn in (test_suspension_released, test_lane_constants, test_attended_required,
               test_interval_enforced, test_daily_cap, test_session_cap_lane_b,
               test_429_is_not_swallowed, test_day_cut_off_and_step_up,
               test_step_down_after_three_clean_days, test_429_resets_clean_days,
               test_restart_restores_state, test_handwritten_state_cannot_loosen,
               test_no_loosening_arguments, test_no_full_scan_path,
               test_no_fingerprint_spoofing, test_lookup_stops_on_rate_limit,
               test_lookup_clean_run):
        fn()
    print(f"\n{COUNT - len(FAILS)}/{COUNT} 通過")
    for f in FAILS:
        print(f"  FAIL {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
