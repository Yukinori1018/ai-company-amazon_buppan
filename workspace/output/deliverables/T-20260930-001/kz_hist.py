"""キーゾン式の販売数推定（Keepa 売れ筋ランク履歴 csv[3] から）— T-20260930-001 タカシ 2026-10-16

CLAUDE.md §3.3-16（2026-10-11 更新）：キーゾンの「過去1/2/3ヶ月目の販売数」は Keepa から再現できる。
式＝30日ごとに「売れ筋ランクが直前の観測より3%超よくなった回数」。原典は
agent_output/T-20260920-003/ledger20261010/kz_estimate.py（キーゾン実画面 25 ASIN×3か月で 69/75 完全一致・最大誤差1個）。
ここでは入口基準 #1（月販 ≥ 50）の「実画面で表示なし」の行に、この推定を添えるために使う。

推定の限界（判定理由に必ず添える）
  - バリエーションの子は兄弟とランクを共有する＝family 合計（キーゾンも同じ値を出す）
  - 観測1回の間に2個以上売れると1回に潰れる＝検算できたのは月0〜13個。月13個を超える商品は過小に出る可能性
  - 月の観測が10回未満なら 0 と区別できない（観測少）

取得：history=1 の product は stats と同じく 1 token/ASIN。手元に履歴が無い ASIN だけを取る。
      生レスポンスは agent_output/T-20260930-001/raw/kzhist_*.json.gz（PUBLIC リポに出さない＝Keepa 規約）。
      ファイル名を prod* にしないのは、criteria_check.load_keepa_cache（prod* を後勝ちで読む）の結果を変えないため。

    python3 kz_hist.py fetch B006WJULPM B00HR12JEA      # 残高が足りなければ取らずに「未確認（トークン）」で終わる
    python3 kz_hist.py show  B006WJULPM                 # 手元の履歴で推定を表示（0 token）
"""
from __future__ import annotations

import gzip
import json
import sys
import time
from datetime import datetime, timedelta

import keepa_io

T0 = 21564000          # Keepa 時刻（分）の起点
THR = 0.03             # 3% を超えてランクが良くなったら1個
VALIDATED_MAX = 13     # 検算できた月販の上限
MIN_OBS = 10


def _keepa_day(m: int) -> str:
    return (datetime(1970, 1, 1) + timedelta(minutes=m + T0, hours=9)).strftime('%m/%d')


def months(p: dict, now: int) -> tuple[list[int], list[int]]:
    """直近30日・31〜60日・61〜90日の推定販売数と、その窓の観測回数。kz_estimate.py と同じ式。"""
    c = ((p.get('csv') or [None] * 4) + [None] * 4)[3] or []
    ps = [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]
    out, obs = [], []
    for k in (1, 2, 3):
        lo, hi = now - 30 * k * 1440, now - 30 * (k - 1) * 1440
        n = o = 0
        prev = None
        for t, r in ps:
            if r <= 0:          # ランクなし（-1）を挟んだら直前値をリセット
                prev = None
                continue
            if lo <= t < hi:
                o += 1
                if prev is not None and (prev - r) / prev > THR:
                    n += 1
            prev = r
        out.append(n)
        obs.append(o)
    return out, obs


def _badge(p: dict) -> tuple[int, str] | None:
    """Keepa が記録した Amazon の「過去1か月で◯点購入」表示の最新値と、その値に変わった日。変化時だけ記録される。"""
    h = p.get('monthlySoldHistory') or []
    if len(h) < 2:
        return None
    return h[-1], _keepa_day(h[-2])


def load() -> dict[str, dict]:
    """raw/kzhist_*.json.gz を読み、ASIN → 推定 の辞書を返す（新しいファイルが勝つ）。"""
    idx: dict[str, dict] = {}
    for fn in sorted(keepa_io.RAW.glob('kzhist_*.json.gz')):
        d = json.loads(gzip.decompress(fn.read_bytes()))
        now = d['fetched'] // 60 - T0
        for p in d.get('products') or []:
            if not (p and p.get('asin')):
                continue
            if not ((p.get('csv') or [None] * 4) + [None] * 4)[3]:
                idx[p['asin']] = {'none': True}
                continue
            m, obs = months(p, now)
            idx[p['asin']] = {'m': m, 'obs': obs, 'family': bool(p.get('parentAsin')),
                              'badge': _badge(p), 'day': datetime.fromtimestamp(d['fetched']).strftime('%m/%d')}
    return idx


def text(e: dict | None) -> str:
    """判定理由に添える文。区切りに「・」を使わない（criteria_check.reason_tags が「・」で割るため）。"""
    if not e:
        return ''
    if e.get('none'):
        return 'キーゾン式推定：Keepa にランク履歴なし'
    m, obs = e['m'], e['obs']
    s = f'キーゾン式推定（直近30日 {m[0]}個 3か月 {m[0]}/{m[1]}/{m[2]} {e["day"]}取得）'
    notes = []
    if e['family']:
        notes.append('バリエーションの子＝family 共有の値')
    if any(o < MIN_OBS for o in obs):
        notes.append('観測少 ' + '/'.join(map(str, obs)))
    notes.append(f'月{VALIDATED_MAX}個超は過小に出る可能性')
    if e.get('badge') and e['badge'][0] >= 50:
        notes.append(f'Keepa の表示履歴は{e["badge"][0]}+（{e["badge"][1]}〜）で実画面と食い違い')
    return s + ' ' + ' '.join(notes)


def fetch(asins: list[str], log=print) -> list[str]:
    """手元に履歴が無い ASIN だけを history=1 で取る。取れなかった ASIN を返す（残高不足なら待たない）。"""
    have = load()
    need = [a for a in dict.fromkeys(asins) if a not in have]
    if not need:
        return []
    left = keepa_io.tokens_left()
    if left < len(need) + 5:   # 夜間の大口取得と同じキー。待たずに「未確認（トークン）」で返す
        log(f'残高 {left} < 必要 {len(need) + 5}：取らない')
        return need
    got: list[str] = []
    for i in range(0, len(need), 100):
        chunk = need[i:i + 100]
        d = keepa_io._get('product', {'domain': keepa_io.DOMAIN_JP, 'asin': ','.join(chunk), 'stats': 365, 'history': 1})
        d['fetched'] = int(time.time())
        keepa_io._save(keepa_io.RAW / f'kzhist_{datetime.now():%Y%m%d_%H%M%S}_{i // 100:02d}.json.gz', d)
        got += [p['asin'] for p in d.get('products') or [] if p]
        log(f'  kzhist {len(chunk)}件 consumed {d.get("tokensConsumed")} left {d.get("tokensLeft")}')
    return [a for a in need if a not in got]


if __name__ == '__main__':
    cmd, *args = sys.argv[1:] or ['show']
    if cmd == 'fetch':
        miss = fetch(args)
        print('未確認（トークン）:', ' '.join(miss) if miss else 'なし')
    idx = load()
    for a in args:
        print(a, text(idx.get(a)) or '履歴なし')
