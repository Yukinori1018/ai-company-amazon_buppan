"""心拍のテスト。

**この仕組みが無くて2回失敗しています。**
  朝  night-shift が814回 exit 127 で死に続け、14日間気づけなかった
  夕方 再起動したつもりが pkill しか走っておらず、ps には稼働中に見えた

守るべき性質は1つ:
  **「待っている」と「死んでいる」が、外から見て違って見えること。**
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import heartbeat, keepa_verify  # noqa: E402


def test_心拍を打つと現在地が読める(tmp_path):
    hb = heartbeat.Heartbeat(tmp_path / "hb.json")
    hb.beat("段3 Keepa検証", done=60, total=740, tokens_left=120)
    got = heartbeat.read(tmp_path / "hb.json")
    assert got["phase"] == "段3 Keepa検証"
    assert got["done"] == 60 and got["total"] == 740


def test_上書きであって追記ではない(tmp_path):
    hb = heartbeat.Heartbeat(tmp_path / "hb.json")
    hb.beat("A", done=1)
    hb.beat("B", done=2)
    got = heartbeat.read(tmp_path / "hb.json")
    assert got["phase"] == "B" and got["done"] == 2


def test_差し替えは原子的で読み手が壊れたJSONを見ない(tmp_path):
    # 書きかけを読ませないため tmp → os.replace で差し替えている。
    hb = heartbeat.Heartbeat(tmp_path / "hb.json")
    for i in range(30):
        hb.beat("段3", done=i)
        assert heartbeat.read(tmp_path / "hb.json")["done"] == i
    assert not (tmp_path / "hb.tmp").exists()


def test_新しい心拍は稼働中と表示される(tmp_path):
    hb = heartbeat.Heartbeat(tmp_path / "hb.json")
    hb.beat("段3 Keepa検証", done=60, total=740)
    line = heartbeat.describe(tmp_path / "hb.json")
    assert "稼働中" in line and "60/740" in line


def test_古い心拍は停止の疑いと表示される(tmp_path):
    path = tmp_path / "hb.json"
    heartbeat.Heartbeat(path).beat("段3", done=1, total=10)
    # 更新時刻を閾値より前に偽装する
    payload = heartbeat.read(path)
    payload["updated_epoch"] = time.time() - heartbeat.STALE_SECONDS - 60
    path.write_text(json.dumps(payload), encoding="utf-8")
    line = heartbeat.describe(path)
    assert "停止の疑い" in line


def test_心拍ファイルが無くても落ちない(tmp_path):
    assert "ありません" in heartbeat.describe(tmp_path / "none.json")
    assert heartbeat.read(tmp_path / "none.json") == {}


def test_壊れた心拍ファイルでも落ちない(tmp_path):
    path = tmp_path / "hb.json"
    path.write_text("{壊れ", encoding="utf-8")
    assert heartbeat.read(path) == {}
    assert "ありません" in heartbeat.describe(path)


def test_書き込みに失敗しても本体を止めない(tmp_path):
    # 心拍のために仕事を落とすのは本末転倒。
    hb = heartbeat.Heartbeat(tmp_path / "sub" / "hb.json")
    hb.path = Path("/no/such/dir/hb.json")
    hb.beat("段3")          # 例外が飛ばないこと


def test_トークン待機中も心拍が打たれる():
    """**これが今回の核心。** 15分の待機中に心拍が止まると、

    「トークンを待っている」と「死んでいる」が外から同じに見える。
    実際にその取り違えをやった。
    """
    budget = keepa_verify.TokenBudget(min_before_batch=120)
    budget.note({"tokensLeft": 0, "tokensConsumed": 100, "refillIn": 0}, codes=100)
    ticks = []
    keepa_verify.time.sleep = lambda s: None       # 実時間は待たない
    slept = []
    keepa_verify.time.sleep = lambda s: slept.append(s)
    budget.wait_if_needed(log=lambda m: None, batch_size=100,
                          on_tick=lambda rest: ticks.append(rest))
    # 待機は30秒刻みに割られ、その回数ぶん心拍が打たれる。
    assert len(ticks) == len(slept) > 1
    assert max(slept) <= 30.0, "丸ごと寝ると待機中に心拍が止まり、死んでいるのと同じに見える"
    assert ticks[0] > ticks[-1] and ticks[-1] == 0
