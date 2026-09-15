"""プール(3,309件)のブランドを50件ずつ Finder に渡し、monthlySold>=100 の ASIN を集める。
プールとの突合で「プール内の売れ筋」と「同ブランドの売れ筋(類似候補)」を得る。1クエリ≒10+件数/100トークン。"""
import json,urllib.request,urllib.parse,gzip,collections,time,sys
R="workspace/output/deliverables/"
OUT="workspace/output/agent_output/T-20260909-002/t11/"
k=[l.split('=',1)[1].strip() for l in open('workspace/output/agent_output/T-20260521-005/code/.env') if l.startswith('KEEPA_API_KEY=')][0]
def get(path,params):
    q=urllib.parse.urlencode(dict(params,key=k,domain=5))
    b=urllib.request.urlopen(urllib.request.Request(f"https://api.keepa.com/{path}?{q}",headers={"Accept-Encoding":"gzip"}),timeout=300).read()
    return json.loads(gzip.decompress(b) if b[:2]==b"\x1f\x8b" else b)
GTE=int(sys.argv[1]) if len(sys.argv)>1 else 100
pool={json.loads(l)['asin'] for l in open(R+'T-20260906-003/out/passed.jsonl')}
brands=collections.Counter()
for l in open(R+'T-20260831-006/out/keepa_facts.jsonl'):
    d=json.loads(l)
    if d['asin'] in pool and d.get('brand'): brands[d['brand']]+=1
bl=[b for b,_ in brands.most_common()]
res={};spent=0
for i in range(0,len(bl),50):
    batch=bl[i:i+50]
    sel={"monthlySold_gte":GTE,"brand":batch,"perPage":10000,"page":0}
    r=get('query',{"selection":json.dumps(sel,ensure_ascii=False)})
    spent+=r.get('tokensConsumed',0)
    tot=r.get('totalResults');a=r.get('asinList') or []
    print(i,len(batch),'total',tot,'got',len(a),'tok',r.get('tokensConsumed'),'left',r.get('tokensLeft'),r.get('error'),flush=True)
    res[i]={"brands":batch,"total":tot,"asins":a}
    if (r.get('tokensLeft') or 0)<200: print('low tokens stop');break
json.dump(res,open(OUT+f'finder_brand_ms{GTE}.json','w'),ensure_ascii=False)
allA=set(x for v in res.values() for x in v['asins'])
print('GTE',GTE,'brand ASINs',len(allA),'in pool',len(allA&pool),'spent',spent)
