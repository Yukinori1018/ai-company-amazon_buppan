"""トークン予算のテスト。**実時間は待たない**（sleep を差し替える）。

ここが甘いと、残高がマイナスまで突っ込んで Keepa 側の制限に触れます。
実際に 100件バッチが190トークン掛かり、残高がマイナス101まで落ちました。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import keepa_verify  # noqa: E402


def _budget():
    return keepa_verify.TokenBudget(min_before_batch=120)


def test_実績が無いうちは1件1トークンで見積もる():
    b = _budget()
    assert b.tokens_per_code == 1.0


def test_実測レートは消費トークンと投げた件数から出る():
    b = _budget()
    b.note({"tokensLeft": 1000, "tokensConsumed": 190}, codes=100)
    assert abs(b.tokens_per_code - 1.9) < 1e-9


def test_必要トークンは実測レートに安全代を掛けた値():
    b = _budget()
    b.note({"tokensLeft": 1000, "tokensConsumed": 190}, codes=100)
    # 100件 × 1.9 × 1.3 = 247
    assert b.required_for(100) == 247


def test_必要トークンは下限を下回らない():
    b = _budget()
    b.note({"tokensLeft": 1000, "tokensConsumed": 5}, codes=100)
    assert b.required_for(10) == 120        # 実測どおりだと極小になるので下限で止める


def test_残高が足りていれば待たない():
    b = _budget()
    b.note({"tokensLeft": 1200, "tokensConsumed": 0}, codes=0)
    waited = []
    keepa_verify.time.sleep = lambda s: waited.append(s)
    assert b.wait_if_needed(log=lambda m: None, batch_size=100) is True
    assert waited == []


def test_残高がマイナスなら不足分まで含めて待つ():
    b = _budget()
    b.note({"tokensLeft": -101, "tokensConsumed": 190, "refillIn": 0}, codes=100)
    waited = []
    keepa_verify.time.sleep = lambda s: waited.append(s)
    assert b.wait_if_needed(log=lambda m: None, batch_size=100) is True
    # 必要247 − 残高(-101) = 348トークン ÷ 20/分 = 約17分 → 上限900秒でクリップ
    assert waited and waited[0] == 900.0


def test_回復しないまま制限時間を過ぎたら諦める():
    b = _budget()
    b.note({"tokensLeft": 0, "tokensConsumed": 100, "refillIn": 0}, codes=100)
    keepa_verify.time.sleep = lambda s: None
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    # 枯渇の開始時刻を制限時間より前に偽装する
    b.starved_since -= keepa_verify.config.KEEPA_STARVATION_MINUTES * 60 + 1
    assert b.wait_if_needed(log=lambda m: None, batch_size=100) is False


def test_回復したら枯渇タイマーは解除される():
    b = _budget()
    b.note({"tokensLeft": 0, "tokensConsumed": 0, "refillIn": 0}, codes=0)
    keepa_verify.time.sleep = lambda s: None
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    assert b.starved_since is not None
    b.note({"tokensLeft": 1200, "tokensConsumed": 0}, codes=0)
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    assert b.starved_since is None
