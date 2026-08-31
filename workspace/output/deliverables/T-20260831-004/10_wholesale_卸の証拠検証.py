# -*- coding: utf-8 -*-
import csv, collections, sys, re, json
sys.path.insert(0,'.')
from rules import norm, tokens_sellers, JP
csv.field_size_limit(10**9)
SRC='/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14/02_候補リスト_社長用.csv'
rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig')))
lanes=json.load(open('lanes.json'))
main=set(lanes['main'])

MERCHANT_ID=re.compile(r'^A[0-9A-Z]{12,13}$')
TRADE=re.compile(r'株式会社|有限会社|合同会社|\(株\)|（株）|商店|商事|産業|工業|問屋|卸|販売|'
                 r'ホームセンター|専門店|本店|直営|老舗|質店|楽器店|書店|薬局|建材|電材|機工|'
                 r'インボイス|適格請求書')
def classify_sellers(r):
    b=re.sub(r'[^a-z0-9]','',norm(r['メーカー/ブランド']).lower())
    own=third=anon=trade=0
    for s in tokens_sellers(r):
        sl=re.sub(r'[^a-z0-9]','',s.lower())
        if b and len(b)>=3 and b in sl: own+=1
        elif MERCHANT_ID.match(s): anon+=1; third+=1
        else:
            third+=1
            if TRADE.search(s): trade+=1
    return own, third, anon, trade

st=collections.Counter(); ex=collections.defaultdict(list)
res={}
for r in rows:
    m=norm(r['メーカー/ブランド'])
    own,third,anon,trade=classify_sellers(r)
    d=res.setdefault(m, dict(own=0,third=0,trade=0,anon=0,n=0))
    d['own']=max(d['own'],own); d['third']=max(d['third'],third)
    d['trade']=max(d['trade'],trade); d['anon']=max(d['anon'],anon); d['n']+=1

M=[m for m in res if m in main]
print(f'=== メインレーン {len(M)}社 の「卸している証拠」の質 ===')
def pct(c): return f'{c:4d}社 ({c/len(M)*100:5.1f}%)'
print('  現行ゲート: 実セラー数>=2 のみ                  ', pct(len(M)))
print('  W1 ブランド自社出品を除いた第三者セラー>=2        ', pct(sum(1 for m in M if res[m]['third']>=2)))
print('  W2 第三者セラー>=2 かつ 屋号型セラー>=1(法人格/商店/インボイス等)', pct(sum(1 for m in M if res[m]['third']>=2 and res[m]['trade']>=1)))
print('  W3 W2 かつ 屋号型>=2（複数の実事業者が仕入れている）  ', pct(sum(1 for m in M if res[m]['third']>=2 and res[m]['trade']>=2)))
print('  参考: ブランド自社出品を含む                    ', pct(sum(1 for m in M if res[m]['own']>=1)))
print('  参考: 全セラーが匿名ID(屋号不明)                ', pct(sum(1 for m in M if res[m]['anon']>=1 and res[m]['trade']==0)))
print()
# 参考: 中国系レーンとの対比
allm=list(res)
print(f'=== 対比: 全{len(allm)}社 ===')
for lbl,cond in [('第三者セラー>=2', lambda d: d['third']>=2),
                 ('第三者>=2 かつ 屋号型>=1', lambda d: d['third']>=2 and d['trade']>=1),
                 ('第三者>=2 かつ 屋号型>=2', lambda d: d['third']>=2 and d['trade']>=2)]:
    c=sum(1 for m in allm if cond(res[m]))
    print(f'  {lbl:<26} {c:5d}社 ({c/len(allm)*100:5.1f}%)')
json.dump(res, open('wholesale_features.json','w'), ensure_ascii=False)
