# -*- coding: utf-8 -*-
"""困り度スコアの材料を Keepa の生レスポンスから抽出する（追加トークン消費ゼロ）。

入力: T-20260817-005/v14/raw_offers/*.json.gz（product + offers + 全履歴）
出力: t41_asin_features.json
"""
import gzip, json, glob, datetime, statistics, sys, os, bisect

V14 = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14"
OUT = os.path.dirname(os.path.abspath(__file__))

EPOCH = datetime.datetime(1970, 1, 1)
def kt2dt(m):  # Keepa time minutes -> datetime(UTC)
    return EPOCH + datetime.timedelta(minutes=m + 21564000)

NOW = None  # データの最終更新時刻を基準にする（実行日ではなく）

def series(arr):
    """[t,v,t,v,...] -> (ts[], v[])  keepa分のまま扱う。v=-1 は欠品/未出品"""
    if not arr:
        return ([], [])
    ts = arr[0::2]; vs = arr[1::2]
    n = min(len(ts), len(vs))
    return (ts[:n], vs[:n])

def value_at(s, t):
    ts, vs = s
    if not ts: return None
    i = bisect.bisect_right(ts, t) - 1
    return vs[i] if i >= 0 else None

def slice_pts(s, t0, t1):
    ts, vs = s
    if not ts: return []
    i = bisect.bisect_right(ts, t0)
    j = bisect.bisect_right(ts, t1)
    head = value_at(s, t0)
    return [(t0, head)] + list(zip(ts[i:j], vs[i:j]))

def time_weighted(s, t0, t1, skip_neg=True):
    pts = slice_pts(s, t0, t1)
    out = []
    for i, (t, v) in enumerate(pts):
        nxt = pts[i+1][0] if i + 1 < len(pts) else t1
        dur = nxt - t
        if dur <= 0 or v is None: continue
        if skip_neg and v < 0: continue
        out.append((v, float(dur)))
    return out

def wq(pairs, q):
    """重み付き分位点"""
    if not pairs:
        return None
    pairs = sorted(pairs)
    tot = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= tot * q:
            return v
    return pairs[-1][0]

def wmean(pairs):
    if not pairs: return None
    tot = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tot if tot else None

def instock_ratio(s, t0, t1):
    """区間内で「値が正（=在庫あり）」だった時間の割合"""
    pts = slice_pts(s, t0, t1)
    tot = 0.0; on = 0.0
    for i, (t, v) in enumerate(pts):
        nxt = pts[i+1][0] if i + 1 < len(pts) else t1
        dur = float(nxt - t)
        if dur <= 0: continue
        tot += dur
        if v is not None and v > 0: on += dur
    return (on / tot) if tot else None

def main():
    files = sorted(glob.glob(V14 + "/raw_offers/*.json.gz"))
    rows = {}
    latest = None
    for f in files:
        d = json.loads(gzip.open(f, 'rt', encoding='utf-8').read())
        for p in d.get('products', []):
            csv = p.get('csv') or []
            def g(i): return csv[i] if len(csv) > i else None
            s_new  = series(g(1))    # NEW（新品最安・送料抜き）
            s_amz  = series(g(0))    # AMAZON（本体の価格＝出品していた時だけ正）
            s_cnt  = series(g(11))   # COUNT_NEW＝新品「オファー数」（出品者数ではない）
            s_rank = series(g(3))    # SALES rank
            s_bb   = series(g(18))   # BUY_BOX_SHIPPING
            if not s_new:
                continue
            t_end = max([s[0][-1] for s in (s_new, s_cnt, s_rank) if s[0]] or [None])
            if t_end is None:
                continue
            latest = t_end if latest is None else max(latest, t_end)
            rows[p['asin']] = dict(p=p, s_new=s_new, s_amz=s_amz, s_cnt=s_cnt,
                                   s_rank=s_rank, s_bb=s_bb, t_end=t_end)
    # 基準日 = データ全体の最終更新
    ref = latest
    print("参照時刻(データ最終):", kt2dt(ref), "商品数:", len(rows), file=sys.stderr)

    feats = {}
    for asin, r in rows.items():
        p = r['p']
        t1 = ref
        t180 = t1 - 180 * 1440
        t90  = t1 - 90 * 1440
        t30  = t1 - 30 * 1440
        first = r['s_new'][0][0]
        hist_days = (t1 - first) // 1440

        pw180 = time_weighted(r['s_new'], t180, t1)
        pw30  = time_weighted(r['s_new'], t30, t1)
        p50 = wq(pw180, .5); p10 = wq(pw180, .1); p90 = wq(pw180, .9)
        cur = value_at(r['s_new'], t1)
        cur = cur if (cur is not None and cur > 0) else None

        # D1 値幅（乱高下）
        band = ((p90 - p10) / p50) if (p50 and p50 > 0 and p10 is not None and p90 is not None) else None
        # 価格改定回数（180日・±1%超の変化のみ数える）
        chg = 0; prev = None
        for ts, v in zip(*r['s_new']):
            if ts < t180 or v is None or v < 0: continue
            if prev is not None and prev > 0 and abs(v - prev) / prev > 0.01:
                chg += 1
            prev = v
        # D3 直近の下落率（30日中央値 vs 180日中央値）
        p50_30 = wq(pw30, .5)
        drop = (1 - p50_30 / p50) if (p50 and p50_30 and p50 > 0) else None
        # D2 新品オファー数の増加
        cw30 = time_weighted(r['s_cnt'], t30, t1)
        cw_old = time_weighted(r['s_cnt'], t180, t90)
        c_now = wq(cw30, .5); c_old = wq(cw_old, .5)
        d_cnt = (c_now - c_old) if (c_now is not None and c_old is not None) else None
        # D4 Amazon本体の在庫率
        amz180 = instock_ratio(r['s_amz'], t180, t1) if r['s_amz'][0] else 0.0
        amz_now = value_at(r['s_amz'], t1) if r['s_amz'][0] else None
        # ランク（直近30日中央値）
        rw = time_weighted(r['s_rank'], t30, t1)
        rank30 = wq(rw, .5)
        # オファー内訳
        offers = p.get('offers') or []
        live = [o for o in offers if o.get('lastSeen', 0) and o['lastSeen'] > t1 - 14 * 1440]
        n_fba = sum(1 for o in live if o.get('isFBA'))
        n_cn  = sum(1 for o in live if o.get('shipsFromChina'))
        n_amz = sum(1 for o in live if o.get('isAmazon'))
        sellers = sorted({o.get('sellerId') for o in live if o.get('sellerId')})

        feats[asin] = dict(
            asin=asin, brand=p.get('brand'), manufacturer=p.get('manufacturer'),
            title=(p.get('title') or '')[:120],
            catTree=[c.get('name') for c in (p.get('categoryTree') or [])],
            hist_days=hist_days,
            price_now=cur, p50_180=p50, p10_180=p10, p90_180=p90,
            band=band, n_change_180=chg, drop_30v180=drop,
            count_new_now=c_now, count_new_old=c_old, d_count_new=d_cnt,
            amz_instock_180=amz180, amz_now=(amz_now if (amz_now or 0) > 0 else None),
            rank30=rank30,
            n_live_offers=len(live), n_fba=n_fba, n_china=n_cn, n_amz_offer=n_amz,
            sellers=sellers,
            monthlySold=p.get('monthlySold'),
        )
    json.dump(dict(ref=str(kt2dt(ref)), feats=feats), open(OUT + "/t41_asin_features.json", "w"),
              ensure_ascii=False)
    print("wrote", len(feats), file=sys.stderr)

main()
