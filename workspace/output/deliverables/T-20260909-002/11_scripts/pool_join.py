"""プール3,309件を monthlySold>=100(Finder brand突合) とそれ以外に分け、既存列で比較。0トークン。"""
import json,csv,statistics as st,collections
R='workspace/output/deliverables/';A='workspace/output/agent_output/T-20260909-002/t11/'
pool={}
for l in open(R+'T-20260906-003/out/passed.jsonl'):
    d=json.loads(l);pool[d['asin']]=d
hit=set(x for v in json.load(open(A+'finder_brand_ms100.json')).values() for x in v['asins'])
F={}
for l in open(R+'T-20260831-006/out/keepa_facts.jsonl'):
    d=json.loads(l)
    if d['asin'] in pool: F[d['asin']]=d
C={}
for r in csv.DictReader(open(R+'T-20260831-006/out/candidates.csv',encoding='utf-8-sig')):
    if r['ASIN'] in pool and r['ASIN'] not in C: C[r['ASIN']]=r
print('cand join',len(C))
def f(x):
    try: return float(str(x).replace(',',''))
    except: return None
def med(v):
    v=[x for x in v if x is not None]; return round(st.median(v),1) if v else None
def share(v): v=list(v); return f"{100*sum(v)/len(v):.1f}%" if v else '-'
G={'月100以上':[a for a in pool if a in hit],'月100未満/公表なし':[a for a in pool if a not in hit]}
print('| 指標 | '+' | '.join(f'{k}（{len(v)}件）' for k,v in G.items())+' |');print('|---|---|---|')
def row(name,fn): print(f'| {name} | '+' | '.join(str(fn(v)) for v in G.values())+' |')
row('価格 中央値(円)',lambda v:med(F[a]['price_yen'] for a in v))
row('純利益 中央値(円)',lambda v:med(f(C[a]['純利益']) for a in v if a in C))
row('利益率 中央値(%)',lambda v:med(f(C[a]['利益率%']) for a in v if a in C))
row('利益率10%以上',lambda v:share((f(C[a]['利益率%']) or -99)>=10 for a in v if a in C))
row('新品オファー数 中央値',lambda v:med(F[a]['offer_count'] for a in v))
row('新品オファー数8以上',lambda v:share((F[a]['offer_count'] or 0)>=8 for a in v))
row('実セラー数 中央値(取得分)',lambda v:med(F[a]['real_seller_count'] for a in v))
row('Amazon本体あり(availability≠-1)',lambda v:share(F[a]['availability_amazon']!=-1 for a in v))
row('バリエーション子',lambda v:share(pool[a].get('is_child') for a in v))
row('カート不在率 中央値',lambda v:med(pool[a].get('bb_absent') for a in v))
row('入数2以上(セット)',lambda v:share((F[a].get('pack_size') or 1)>=2 for a in v))
row('ランキング 中央値',lambda v:med(F[a]['sales_rank'] for a in v))
print()
cat=collections.Counter();catH=collections.Counter()
for a in pool:
    c=(F[a]['category_names'] or ['?'])[0];cat[c]+=1;catH[c]+=a in hit
print('| カテゴリ | 件数 | 月100以上 | 比率 |');print('|---|---:|---:|---:|')
for c,n in cat.most_common(15): print(f'| {c} | {n} | {catH[c]} | {100*catH[c]/n:.0f}% |')
print()
bands=[(0,1500),(1500,3000),(3000,5000),(5000,8000),(8000,15000),(15000,10**9)]
print('| 価格帯 | 件数 | 月100以上 | 比率 |');print('|---|---:|---:|---:|')
for lo,hi in bands:
    v=[a for a in pool if F[a]['price_yen'] and lo<=F[a]['price_yen']<hi]
    if v: print(f'| {lo:,}〜{(f"{hi:,}" if hi<10**9 else "")} | {len(v)} | {sum(a in hit for a in v)} | {100*sum(a in hit for a in v)/len(v):.0f}% |')
# 04/07 との重なり
for fn in ['T-20260909-002/out/04_回転ふるい_全件.csv','T-20260909-002/out/07_修正後候補.csv']:
    try:
        s={r.get('ASIN') for r in csv.DictReader(open(R+fn,encoding='utf-8-sig'))}
        print(fn,'rows',len(s),'月100以上',len(s&hit))
    except Exception as e: print(fn,e)
# 売れ筋の行データ（Git追跡外の out/ へ）
out=R+'T-20260909-002/out/11_月100以上_プール内.csv'
cols=['ASIN','Amazon商品名','サプライヤー名','NETSEA卸値(税込)','Amazon価格','純利益','利益率%','出品者数','Amazon本体の有無','最小発注額(税込)','出品の入数']
with open(out,'w',encoding='utf-8-sig',newline='') as fo:
    w=csv.writer(fo);w.writerow(cols+['ブランド','カテゴリ','バリエーション子','カート不在率'])
    for a in sorted(G['月100以上'],key=lambda a:-(f(C.get(a,{}).get('純利益')) or -1e9)):
        c=C.get(a,{});w.writerow([c.get(k,'' if k!='ASIN' else a) for k in cols]+[F[a]['brand'],(F[a]['category_names'] or [''])[0],pool[a].get('is_child'),pool[a].get('bb_absent')])
print('wrote',out)
v=[a for a in G['月100以上'] if a in C]
print('月100以上で 利益>0:',sum((f(C[a]['純利益']) or -1)>0 for a in v),' 利益率10%以上:',sum((f(C[a]['利益率%']) or -99)>=10 for a in v),' 利益率20%以上:',sum((f(C[a]['利益率%']) or -99)>=20 for a in v))
