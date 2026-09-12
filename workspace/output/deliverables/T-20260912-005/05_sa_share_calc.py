#!/usr/bin/env python3
"""S-a 取り分の再推定（T-20260912-005 / サトル / 2026-09-13）。Keepa API は叩かない（0 token）。
入力: workspace/output/agent_output/T-20260912-001/raw17/<社>.json（2026-09-12 取得・Git 追跡外）
      workspace/output/agent_output/T-20260906-002/labeled_sample.json（文房具 n=360・2026-09-06）
出力: workspace/output/agent_output/T-20260912-005/sa_asin.csv / sa_company.csv / sa_stats.json
"""
import json, glob, os, csv, math, statistics
RAW = 'workspace/output/agent_output/T-20260912-001/raw17'
OUT = 'workspace/output/agent_output/T-20260912-005'
ORDER = ["大橋量器","木村硝子店","楠橋紋織","七福タオル","金野タオル","北尾化粧品部","高柳製茶","北陸製菓",
         "宇野刷毛ブラシ製作所","廣田硝子","守田漆器","池本刷子工業","木内籐材工業","朝倉染布","河野製紙",
         "小野甚味噌醤油醸造","田中帽子店"]
BASE = 30000.0          # マサルの置き値: 相乗り1 SKU 月商 3万円 = 1.0倍
LOT, TURN = 10, 1.8     # 10点ロット・回転 1.8ヶ月 → 足切り 取り分 ≥ 10/1.8 = 5.56 個/月
CUT = LOT / TURN
CAP = 49                # Amazon公表値なし ⇒ <50 と読む（公表値の最小階級 50。社内標本 n=110 の最小値も 50）

def price_of(x):
    st = x['stats']; cur = st['current']
    if cur[1] and cur[1] > 0: return cur[1], '現在新品価格(NEW, 着地価格)'
    for k in ('avg90', 'avg365'):
        v = st.get(k) or []
        if len(v) > 1 and v[1] and v[1] > 0: return v[1], f'{k} NEW（現在オファーなし）'
    return None, '価格なし'

rows = []
for name in ORDER:
    d = json.load(open(f'{RAW}/{name}.json', encoding='utf-8'))
    prods = d.get('products') or []
    if not prods:
        rows.append(dict(社=name, ASIN='（raw なし）', 親子='—', 備考='ブランド/製造元一致の出品に売れ筋ランクなし（T-20260912-001 S3）'))
        continue
    for x in prods:
        st = x['stats']; cur = st['current']
        rank = cur[3]; rank30 = (st.get('avg30') or [None]*4)[3]
        ref = x.get('salesRankReference'); cat = (x.get('categoryTree') or [{}])[0].get('name', '')
        ms = x.get('monthlySold')
        offers = max(cur[11], 0)      # COUNT_NEW = 新品オファー数（出品者数の上限。実セラー数ではない）
        amazon = x.get('availabilityAmazon', -1) != -1
        parent = x.get('parentAsin')
        price, psrc = price_of(x)
        if ms:
            est, layer = float(ms), '実測(Amazon公表・階級下限)'
            est_hi = est
        else:
            est_hi = float(CAP)
            est, layer = CAP / 2.0, '推定(公表なし→0〜49の中央)'
        share = est / (offers + 1); share_hi = est_hi / (offers + 1)
        rev = share * price if price else None
        rows.append(dict(
            社=name, ASIN=x['asin'], 商品名=(x.get('title') or '')[:36], brand=x.get('brand') or '',
            親子=f'子（親 {parent}）' if parent else '単体', 親ASIN=parent or '',
            ルートカテゴリ=cat, ランク本体_現在=rank, ランク本体_30日平均=rank30,
            Amazon公表月販_下限=ms or '', 月販の層=layer, 月販推定=round(est, 1), 月販上限=est_hi,
            新品オファー数_COUNT_NEW=offers, Amazon本体='あり' if amazon else 'なし',
            取り分_個月=round(share, 2), 取り分上限_個月=round(share_hi, 2),
            足切り_10点_1_8ヶ月=('○' if share >= CUT else '×'), 足切り_上限でも=('○' if share_hi >= CUT else '×'),
            価格=price or '', 価格の出所=psrc,
            取り分月商=round(rev) if rev else '', 倍率_対3万=round(rev / BASE, 2) if rev else '',
            倍率上限=round(share_hi * price / BASE, 2) if price else '',
            備考=('現在新品オファーなし' if cur[11] <= 0 else '')))

with open(f'{OUT}/sa_asin.csv', 'w', encoding='utf-8-sig', newline='') as f:
    keys = max(rows, key=len).keys()
    w = csv.DictWriter(f, fieldnames=list(keys)); w.writeheader(); w.writerows(rows)

def q(v, p):
    v = sorted(v); n = len(v)
    if not n: return None
    k = (n - 1) * p; lo = math.floor(k); hi = math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)
def dist(v):
    v = [float(a) for a in v if a != '' and a is not None]
    return dict(n=len(v), p10=round(q(v,.1),2) if v else None, p50=round(q(v,.5),2) if v else None, p90=round(q(v,.9),2) if v else None, mean=round(sum(v)/len(v),2) if v else None)

data = [r for r in rows if r.get('取り分_個月') is not None and r['ASIN'] != '（raw なし）']
# ファミリー重複除去: 親ASINごとに（子は兄弟合計の上限なので）ランク最良の1件だけ残す
fam = {}
for r in data:
    k = r['親ASIN'] or r['ASIN']
    if k not in fam or r['ランク本体_現在'] < fam[k]['ランク本体_現在']: fam[k] = r
famrows = list(fam.values())
stats = {}
for label, rs in [('ASIN別_121', data), ('ファミリー別_重複除去', famrows),
                  ('ASIN別_Amazon本体なし', [r for r in data if r['Amazon本体']=='なし']),
                  ('ファミリー別_Amazon本体なし', [r for r in famrows if r['Amazon本体']=='なし'])]:
    stats[label] = dict(
        n=len(rs), 子=sum(r['親子']!='単体' for r in rs), 実測層=sum('実測' in r['月販の層'] for r in rs),
        Amazon本体あり=sum(r['Amazon本体']=='あり' for r in rs), 現在オファーなし=sum(r['備考']=='現在新品オファーなし' for r in rs),
        足切り通過=sum(r['足切り_10点_1_8ヶ月']=='○' for r in rs), 足切り通過_上限でも=sum(r['足切り_上限でも']=='○' for r in rs),
        取り分=dist([r['取り分_個月'] for r in rs]), 取り分上限=dist([r['取り分上限_個月'] for r in rs]),
        倍率_全体=dist([r['倍率_対3万'] for r in rs]), 倍率_上限=dist([r['倍率上限'] for r in rs]),
        倍率_実測層のみ=dist([r['倍率_対3万'] for r in rs if '実測' in r['月販の層']]),
        倍率_推定層のみ=dist([r['倍率_対3万'] for r in rs if '推定' in r['月販の層']]),
        オファー数=dist([r['新品オファー数_COUNT_NEW'] for r in rs]),
        価格=dist([r['価格'] for r in rs]),
    )
json.dump(stats, open(f'{OUT}/sa_stats.json','w',encoding='utf-8'), ensure_ascii=False, indent=1)

comp = []
for name in ORDER:
    rs = [r for r in data if r['社']==name]
    fr = [r for r in famrows if r['社']==name]
    if not rs:
        comp.append(dict(社=name, ASIN数=0, ファミリー数=0)); continue
    comp.append(dict(社=name, ASIN数=len(rs), うち子=sum(r['親子']!='単体' for r in rs), ファミリー数=len(fr),
        実測層=sum('実測' in r['月販の層'] for r in rs), Amazon本体あり=sum(r['Amazon本体']=='あり' for r in rs),
        ランク本体_中央=statistics.median([r['ランク本体_現在'] for r in rs]),
        オファー数_中央=statistics.median([r['新品オファー数_COUNT_NEW'] for r in rs]),
        取り分_中央=round(statistics.median([r['取り分_個月'] for r in rs]),2), 取り分_最大=max(r['取り分_個月'] for r in rs),
        足切り通過ASIN=sum(r['足切り_10点_1_8ヶ月']=='○' for r in rs), 足切り通過ファミリー=sum(r['足切り_10点_1_8ヶ月']=='○' for r in fr),
        倍率_中央=round(statistics.median([r['倍率_対3万'] for r in rs if r['倍率_対3万']!='']),2) if any(r['倍率_対3万']!='' for r in rs) else '',
        倍率_最大=max([r['倍率_対3万'] for r in rs if r['倍率_対3万']!='' ] or ['']),
        取り分月商_合計_ファミリー=round(sum(r['取り分月商'] for r in fr if r['取り分月商']!='')),
    ))
with open(f'{OUT}/sa_company.csv','w',encoding='utf-8-sig',newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(max(comp,key=len).keys())); w.writeheader(); w.writerows(comp)
print(json.dumps(stats, ensure_ascii=False, indent=1))
for c in comp: print(c)
