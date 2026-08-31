# -*- coding: utf-8 -*-
"""v15 抽出フィルタを既存 v14 候補リストへ遡及適用する（Keepaトークン消費ゼロ）。
出力: メーカー単位の3レーン CSV + 除外ログ"""
import csv, collections, sys, os, re, statistics, json
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from rules import cn_score, is_media, norm, CORP, JP, tokens_sellers, jp_signal_valid, is_nobrand
csv.field_size_limit(10**9)
SRC=sys.argv[1]; OUT=sys.argv[2]
os.makedirs(OUT, exist_ok=True)
rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig')))
by=collections.defaultdict(list)
for r in rows: by[norm(r['メーカー/ブランド'])].append(r)

RESALE={'本','洋書','ミュージック'}; CORPONLY={'DVD','ゲーム','PCソフト'}
MERCHANT_ID=re.compile(r'^A[0-9A-Z]{12,13}$')
TRADE=re.compile(r'株式会社|有限会社|合同会社|\(株\)|（株）|商店|商事|産業|工業|問屋|卸|販売|'
                 r'ホームセンター|専門店|本店|直営|老舗|楽器店|書店|薬局|建材|電材|機工|インボイス|適格請求書')
def third_party(r):
    b=re.sub(r'[^a-z0-9]','',norm(r['メーカー/ブランド']).lower()); t=w=0
    for s in tokens_sellers(r):
        sl=re.sub(r'[^a-z0-9]','',s.lower())
        if b and len(b)>=3 and b in sl: continue
        t+=1
        if TRADE.search(s): w+=1
    return t,w
def med(v): 
    x=[float(r[v] or 0) for r in rs if r[v] not in ('',None)]
    return round(statistics.median(x)) if x else ''

recs=[]
for m,rs in by.items():
    cn=max(cn_score(r)[0] for r in rs)
    sig=sorted({k for r in rs for k,v in cn_score(r)[1].items() if v})
    cats=collections.Counter(norm(r['カテゴリ']).split(' > ')[0] for r in rs)
    top=cats.most_common(1)[0][0]
    media=sum(1 for r in rs if is_media(r))/len(rs)
    jp=any(jp_signal_valid(r) for r in rs)
    nob=any(is_nobrand(r) for r in rs)
    corp=any(CORP.search(norm(r['メーカー/ブランド'])) or CORP.search(norm(r['manufacturer'])) for r in rs)
    tp=max(third_party(r)[0] for r in rs); tw=max(third_party(r)[1] for r in rs)
    # 判定
    if nob:
        lane='除外:ノーブランド'; reason='メーカー名が特定できない(ノーブランド品/Generic)'
    elif media>=0.5:
        lane='除外:メディア'; reason=('再販制度対象(法人化でも解けない)' if top in RESALE
                 else '版元直取引は法人+実績が前提(法人化で条件付きに開く)' if top in CORPONLY else 'メディア')
    elif cn>=3: lane='除外:中国系OEM(確定)'; reason='CNスコア%d / %s'%(cn,'+'.join(sig))
    elif cn>=1: lane='除外:中国系OEM(疑い)'; reason='CNスコア%d / %s'%(cn,'+'.join(sig))
    elif tp<2:  lane='除外:卸の証拠なし'; reason='ブランド自社出品を除く第三者セラーが2未満'
    elif jp:    lane='A_メインレーン'; reason='日本語商号あり→gBizINFOで従業員数照合へ'
    else:       lane='B_英字レーン'; reason='日本語シグナルなし→人手/HTTP確認が必要'
    mfrs=[norm(r['manufacturer']) for r in rs if norm(r['manufacturer'])]
    recs.append(dict(メーカー=m, レーン=lane, 判定理由=reason,
      商号候補=collections.Counter(mfrs).most_common(1)[0][0] if mfrs else '',
      法人格表記=('あり' if corp else ''), 該当商品数=len(rs), 主カテゴリ=top,
      第三者セラー数=tp, 屋号型セラー数=tw, CNスコア=cn, CNシグナル='+'.join(sig),
      想定仕入れ上限の中央値=round(statistics.median([float(r['想定仕入れ金額(上限)'] or 0) for r in rs])),
      Amazon価格の中央値=round(statistics.median([float(r['Amazon価格'] or 0) for r in rs])),
      代表商品=rs[0]['商品名'][:80], 代表ASIN=rs[0]['ASIN'],
      メーカー検索=rs[0]['メーカー検索(Google)']))
recs.sort(key=lambda x:(x['レーン'], -x['該当商品数']))
H=list(recs[0].keys())
def dump(fn, sel):
    with open(os.path.join(OUT,fn),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,H); w.writeheader()
        for r in recs:
            if sel(r): w.writerow(r)
dump('04_メーカーリスト_Aメインレーン.csv', lambda r:r['レーン']=='A_メインレーン')
dump('05_メーカーリスト_B英字レーン.csv',  lambda r:r['レーン']=='B_英字レーン')
dump('06_除外ログ_全件.csv',             lambda r:r['レーン'].startswith('除外'))
c=collections.Counter(r['レーン'] for r in recs)
print('=== v15 遡及適用の結果（メーカー単位）===')
for k,v in c.most_common(): print(f'  {k:<26} {v:5d}社')
print(f'  合計 {len(recs)}社')
