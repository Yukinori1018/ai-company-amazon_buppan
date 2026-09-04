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
    # 必要247 − 残高(-101) = 348トークン ÷ 20/分 = 約17分 → 上限900秒でクリップ。
    # sleep は心拍を打つため30秒刻みに割られるので、**合計**で見る。
    assert sum(waited) == 900.0
    assert max(waited) <= 30.0, "長い sleep を丸ごと寝ると待機中に心拍が止まる"


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


def test_バッチを撃てているうちは枯渇と判定しない():
    """2026-08-31 の実走を1,200件で止めた欠陥の回帰テスト。

    残高がしきい値を下回るのは、長時間ジョブでは**正常な定常状態**です
    （待つ → 撃つ → また待つ）。それを「回復しない」と読んで自己停止したため、
    620件を正常に処理しながら「トークンが60分回復しません」と誤報告しました。
    枯渇の定義は「**1件も進まないまま**時間が過ぎた」でなければなりません。
    """
    b = _budget()
    keepa_verify.time.sleep = lambda s: None
    b.note({"tokensLeft": 0, "tokensConsumed": 0, "refillIn": 0}, codes=0)
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    assert b.starved_since is not None
    # 回復を待ったあとバッチが通り、トークンを実際に消費した＝生きている
    b.note({"tokensLeft": 30, "tokensConsumed": 190}, codes=100)
    assert b.starved_since is None
    # 残高は依然しきい値以下だが、進んでいるので止めてはいけない
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    b.starved_since -= keepa_verify.config.KEEPA_STARVATION_MINUTES * 60 + 1
    b.note({"tokensLeft": 30, "tokensConsumed": 190}, codes=100)
    assert b.wait_if_needed(log=lambda m: None, batch_size=100) is True


def test_しきい値は下がる_一度スパイクしても固定されない():
    """旧実装は min_before_batch を書き換えており、しきい値が**下がりませんでした**。

    1回コストが跳ねただけで、以後ずっと余計に待ち続けます（28時間走ると効きます）。
    """
    b = _budget()
    keepa_verify.time.sleep = lambda s: None
    b.note({"tokensLeft": 100, "tokensConsumed": 400, "refillIn": 0}, codes=100)
    high = b.required_for(100)
    b.wait_if_needed(log=lambda m: None, batch_size=100)
    # 以後のバッチが安く済んだら、要求トークンも下がるべき
    b.note({"tokensLeft": 100, "tokensConsumed": 20}, codes=900)
    assert b.required_for(100) < high
