"""T-20260930-001 入口基準への適合チェック（タカシ 2026-10-10）

シート「メーカー連絡先」の各行（＝代表ASIN 1本）が、リスト設計書
deliverables/T-20260930-001/01_リスト設計_Amazon起点メーカー連絡先台帳.md §3-1/3-2 と
CLAUDE.md §3.3-5・§3.5 の入口基準を満たすかを判定し、「基準チェック」列の文字列を返す。

基準（カズヨ指示 10/10）
  1 月販 ≥ 50（Amazon 表示）          … 実画面 → 候補CSV → Keepa キャッシュ の順に採る
  2 Amazon 本体なし（365日在庫切れ率 ≥ 90%）… 実画面で「あり」なら NG
  3 FBA出品者 ≥ 1 かつ 新品出品 ≥ 2（入口(a)を含む）
  4 大カテゴリーの売れ筋ランク ≤ 5万     … Keepa キャッシュ stats.current[3]
  5 売価 ≥ 2,200円                     … 40_採算列の平時売価 → 候補CSVの代表の売価
  6 カート保持者がメーカー本人でない      … 判定「除外：メーカー本人」→NG、「本人の疑い」→未確認

出力：'OK' ／ 'NG：理由・理由' ／ '未確認：項目'（NG が1つでもあれば NG を優先し、未確認は括弧で併記）
※ 値はシート（非公開）にだけ出る。PUBLIC リポには集計件数しか書かない。
"""
from __future__ import annotations

import gzip
import json
import os
import re

# 実体は deliverables/（PUBLIC・コードのみ）。Keepa キャッシュは agent_output/（gitignore）にある
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../../..'))
RAW = os.path.join(REPO, 'workspace/output/agent_output/T-20260930-001/raw')

MIN_SOLD, MIN_OOS, MAX_RANK, MIN_PRICE = 50, 90, 50_000, 2_200


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


def _int(s) -> int | None:
    m = re.search(r'-?\d[\d,]*', str(s or ''))
    return int(m.group().replace(',', '')) if m else None


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


def check(r: dict, cand: dict, profit: dict, kp: dict | None) -> str:
    k = _keepa(kp or {})
    ng, unk = [], []

    # 1 月販
    shown = r.get('過去1ヶ月の販売数(実画面9/30)') or ''
    if '表示なし' in shown and '実画面未確認' not in shown:
        ng.append('月販表示なし')
    else:
        v = _int(shown) if shown and '表示なし' not in shown else None
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
    new_s = r.get('新品出品数(実画面)') or ''
    new = _int(new_s) if new_s and '未確認' != new_s else None
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

    # 5 売価
    price = _int(profit.get('平時売価(円・税込)')) or _int(r.get('代表の売価')) or _int(cand.get('代表の売価'))
    if price is None:
        unk.append('売価')
    elif price < MIN_PRICE:
        ng.append(f'売価{price:,}円<2,200')

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
    body = re.sub(r'（未確認：.*', '', s[3:])
    out = []
    for t in body.split('・'):
        out.append(re.sub(r'[\d,.%<>万位円]+.*$', '', t) or t)
    return out
