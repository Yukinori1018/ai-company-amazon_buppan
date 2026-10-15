"""T-20260930-001 入口基準への適合チェック（タカシ 2026-10-10）

シート「メーカー連絡先」の各行（＝代表ASIN 1本）が、リスト設計書
deliverables/T-20260930-001/01_リスト設計_Amazon起点メーカー連絡先台帳.md §3-1/3-2 と
CLAUDE.md §3.3-5・§3.5 の入口基準を満たすかを判定し、「基準チェック」列の文字列を返す。

基準（カズヨ指示 10/10）
  1 月販 ≥ 50（Amazon 表示）          … 実画面 → 候補CSV → Keepa キャッシュ の順に採る。
       実画面で「表示なし」の行は、キーゾン式推定（kz_hist.py・CLAUDE.md §3.3-16）の直近30日が 50 以上なら通す。
       50 未満なら NG のまま推定値と限界（family 共有・月13個超は過小）を〔〕に書く（2026-10-16 追加）
  2 Amazon 本体なし（365日在庫切れ率 ≥ 90%）… 実画面で「あり」なら NG
  3 FBA出品者 ≥ 1 かつ 新品出品 ≥ 2（入口(a)を含む）
  4 大カテゴリーの売れ筋ランク ≤ 5万     … Keepa キャッシュ stats.current[3]
  5 利益率5%に必要な掛け ≥ 40%          … 40_採算列の「利益率5%の上限卸値」÷「平時売価」
       2026-10-16 変更（カズヨ判断A・タカシ実装）：前の値は「売価 ≥ 2,200円」。単価の下限は当社が置いた定数で、
       CLAUDE.md §3.3-27（実践者は単価の下限を置かず利益で切る）・§3.5 メーカー直の初期方針（見積り利益率5%以上で
       テスト仕入れ）と食い違い、入口(b)（売価1,500〜2,199円）の接触候補を全員落としていた。
       40% は仮置き（§3.1）。メーカー直の一般的な5〜6掛けで5%が届く線。40〜50%は採算メモに「掛け交渉次第」
  6 カート保持者がメーカー本人でない      … 判定「除外：メーカー本人」→NG、「本人の疑い」→未確認

出力：'OK' ／ 'NG：理由・理由' ／ '未確認：項目'（NG が1つでもあれば NG を優先し、未確認は括弧で併記）
※ 値はシート（非公開）にだけ出る。PUBLIC リポには集計件数しか書かない。
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import kz_hist  # noqa: E402

# 実体は deliverables/（PUBLIC・コードのみ）。Keepa キャッシュは agent_output/（gitignore）にある
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../../..'))
RAW = os.path.join(REPO, 'workspace/output/agent_output/T-20260930-001/raw')

MIN_SOLD, MIN_OOS, MAX_RANK = 50, 90, 50_000
# 基準5：利益率5%を取るのに必要な掛け（＝利益率5%の上限卸値 ÷ 平時売価）の下限。仮置き（§3.1）。
# 2026-10-16 までは MIN_PRICE = 2_200（売価の下限）だった。
MIN_KAKE, NEGOTIATE_KAKE = 0.40, 0.50
COL_UP5, COL_PRICE = '利益率5%の上限卸値(円・税込)', '平時売価(円・税込)'


def load_keepa_cache() -> dict[str, dict]:
    """raw/prod*.json.gz の Keepa product を ASIN で引けるようにする（取得はしない）。"""
    idx: dict[str, dict] = {}
    if not os.path.isdir(RAW):
        return idx
    for fn in sorted(os.listdir(RAW)):
        if not (fn.startswith('prod') and fn.endswith('.json.gz')):
            continue
        try:
            d = json.loads(gzip.decompress(open(os.path.join(RAW, fn), 'rb').read()))
        except Exception:
            continue
        for p in (d.get('products') or []):
            if p and p.get('asin'):
                idx[p['asin']] = p
    return idx


_KZ: dict[str, dict] | None = None


def kz_estimate(asin: str) -> dict | None:
    """キーゾン式推定（kz_hist.py）。手元の raw/kzhist_*.json.gz だけを読む（取得はしない）。"""
    global _KZ
    if _KZ is None:
        try:
            _KZ = kz_hist.load()
        except Exception:
            _KZ = {}
    return _KZ.get(asin)


def _int(s) -> int | None:
    m = re.search(r'-?\d[\d,]*', str(s or ''))
    return int(m.group().replace(',', '')) if m else None


def _shown_int(s) -> int | None:
    """実画面の列の数値。「未調査（batchZ3の範囲外）」「未確認」は値なし（None）。
    2026-10-13 タカシ：batchZ1〜Z3 の「未調査（batchZ3の範囲外）」から _int が 3 を拾い、
    月販3・新品3 と誤読して接触候補3社を基準NGにしていた（バッチ名に数字が入ったのは Z1 から）。"""
    s = str(s or '').strip()
    if not s or s.startswith(('未調査', '未確認')):
        return None
    return _int(s)


def _keepa(p: dict) -> dict:
    """Keepa の負値（-1=データなし・-2=未取得）は None に揃える。"""
    st = (p or {}).get('stats') or {}
    pos = lambda v: v if isinstance(v, int) and v >= 0 else None
    cur = st.get('current') or []
    oos = st.get('outOfStockPercentage365') or []
    return {'sold': pos((p or {}).get('monthlySold')),
            'oos': pos(oos[0]) if oos else None,
            'rank': pos(cur[3]) if len(cur) > 3 else None,
            'fba': pos(st.get('offerCountFBA')),
            'new': pos(st.get('totalOfferCount'))}


def need_kake(profit: dict) -> float | None:
    """利益率5%を取るのに必要な掛け（0.45＝4.5掛けまでなら5%が残る）。計算できなければ None。
    上限卸値が0以下（タダで仕入れても5%に届かない）は 0.0 を返す＝必ず NG になる。"""
    up5, price = _int((profit or {}).get(COL_UP5)), _int((profit or {}).get(COL_PRICE))
    if up5 is None or not price or price <= 0:
        return None
    return max(up5, 0) / price


def kake_ng(k: float | None) -> str | None:
    """基準5の NG 理由（OK なら None）。k が None のときは呼ばない（未確認扱い）。"""
    if k is not None and k < MIN_KAKE:
        return f'5%に必要な掛け{k * 100:.0f}%<{MIN_KAKE * 100:.0f}%'
    return None


def kake_note(k: float | None) -> str:
    """40〜50% は通すが、掛けの交渉が要ることを採算メモに残す。"""
    if k is not None and MIN_KAKE <= k < NEGOTIATE_KAKE:
        return f'掛け交渉次第（利益率5%に必要な掛け{k * 100:.0f}%）'
    return ''


def check(r: dict, cand: dict, profit: dict, kp: dict | None) -> str:
    k = _keepa(kp or {})
    ng, unk = [], []

    # 1 月販
    shown = r.get('過去1ヶ月の販売数(実画面9/30)') or ''
    if '表示なし' in shown and '実画面未確認' not in shown:
        # 2026-10-16（タカシ）：実画面で表示なしの行に、キーゾン式推定（kz_hist.py・§3.3-16）を後ろから足す。
        # 推定の直近30日が 50 以上なら通す。50 未満なら NG のまま、推定値と限界を〔〕に添える（事実として書く）
        e = kz_estimate(r.get('代表ASIN(タカシ)') or (kp or {}).get('asin') or '')
        note = f'〔{kz_hist.text(e)}〕' if e else ''
        if e and not e.get('none') and e['m'][0] >= MIN_SOLD:
            pass
        else:
            ng.append('月販表示なし' + note)
    else:
        v = _shown_int(shown) if shown and '表示なし' not in shown else None
        if v is None:
            v = _int(cand.get('過去1ヶ月の販売数(代表)')) or k['sold']
        if v is None:
            unk.append('月販')
        elif v < MIN_SOLD:
            ng.append(f'月販{v}<{MIN_SOLD}')

    # 2 Amazon 本体
    amz = r.get('Amazon本体の有無') or ''
    oos = _int(cand.get('本体365日在庫切れ率(代表)'))
    if oos is None:
        oos = k['oos']
    if amz.startswith(('あり', '有')) or 'Amazon.co.jp' in (r.get('カート保持者(実画面9/30)') or ''):
        ng.append('Amazon本体あり')
    elif oos is None:
        if not amz.startswith(('なし', '無')):
            unk.append('本体履歴')
    elif oos < MIN_OOS:
        ng.append(f'本体在庫切れ率{oos}%<{MIN_OOS}%')

    # 3 FBA ≥1 かつ 新品 ≥2（実画面の新品数があれば優先）
    fba = _int(cand.get('代表のFBA数'))
    fba = fba if fba is not None else k['fba']
    if fba is None and r.get('_cart_fba'):  # 実画面でカート保持者の出荷が FBA（sync_ledger.apply_screen_checks）
        fba = 1
    new_s = r.get('新品出品数(実画面)') or ''
    new = _shown_int(new_s)
    if new is None:
        new = _int(cand.get('代表の新品オファー数'))
    if new is None:
        new = k['new']
    if fba is None:
        unk.append('FBA数')
    elif fba < 1:
        ng.append('FBA出品者0')
    if new is None:
        unk.append('新品出品数')
    elif new < 2:
        ng.append(f'新品出品{new}<2')

    # 4 ランク
    if k['rank'] is None:
        unk.append('ランク')
    elif k['rank'] > MAX_RANK:
        ng.append(f'ランク{k["rank"] / 10000:.1f}万位>5万')

    # 5 利益率5%に必要な掛け ≥ 40%（2026-10-16 までは「売価 ≥ 2,200円」）
    k5 = need_kake(profit)
    if k5 is None:
        unk.append('採算')
    elif kake_ng(k5):
        ng.append(kake_ng(k5))

    # 6 カート保持者
    j = r.get('判定') or ''
    if 'メーカー本人' in j and j.startswith('除外'):
        ng.append('カートがメーカー本人')
    elif '本人の疑い' in j or '本人カート疑い' in j or '実画面で取得できず' in j:
        unk.append('カート保持者')

    if ng:
        return 'NG：' + '・'.join(ng) + (f'（未確認：{"・".join(unk)}）' if unk else '')
    if unk:
        return '未確認：' + '・'.join(unk)
    return 'OK'


def reason_tags(s: str) -> list[str]:
    """集計用：'NG：月販30<50・ランク7.2万位>5万' → ['月販', 'ランク']"""
    if not s.startswith('NG：'):
        return []
    body = re.sub(r'〔[^〕]*〕', '', re.sub(r'（未確認：.*', '', s[3:]))
    out = []
    for t in body.split('・'):
        if '必要な掛け' in t:  # 「5%に必要な掛け32%<40%」は先頭が数字なので下の正規表現では語が残らない
            out.append('必要な掛け')
            continue
        out.append(re.sub(r'[\d,.%<>万位円]+.*$', '', t) or t)
    return out
