# -*- coding: utf-8 -*-
import csv, json, collections, sys
sys.path.insert(0,'.')
from rules import cn_score, jp_signals, is_media, norm
csv.field_size_limit(10**9)
SRC='/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260817-005/v14/02_候補リスト_社長用.csv'
rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig')))
by=collections.defaultdict(list)
for r in rows: by[norm(r['メーカー/ブランド'])].append(r)

def maker_feat(m):
    rs=by[m]
    scores=[cn_score(r) for r in rs]
    best=max(s for s,_ in scores)
    agg=collections.Counter()
    for s,sig in scores:
        for k,v in sig.items():
            if v: agg[k]+=1
    j=collections.Counter()
    for r in rs:
        for k,v in jp_signals(r).items():
            if v: j[k]+=1
    media=sum(1 for r in rs if is_media(r))
    return dict(cn=best, cn_sig=dict(agg), jp=dict(j), n=len(rs), media_ratio=media/len(rs))

lab=json.load(open('sample200_labeled.json'))
for m in lab: m.update(maker_feat(m['maker']))
json.dump(lab,open('sample200_feat.json','w'),ensure_ascii=False,indent=1)

def ev(name, pred, target):
    tp=sum(1 for m in lab if pred(m) and m['label'] in target)
    fp=sum(1 for m in lab if pred(m) and m['label'] not in target)
    fn=sum(1 for m in lab if not pred(m) and m['label'] in target)
    P=tp/(tp+fp)*100 if tp+fp else 0; R=tp/(tp+fn)*100 if tp+fn else 0
    print(f'{name:<40} 適合率{P:5.1f}%  再現率{R:5.1f}%  (的中{tp} 誤検出{fp} 取りこぼし{fn})')
    return [m for m in lab if pred(m) and m['label'] not in target]

print('=== 中国系OEM(D)判定 ===')
for th in (1,2,3,4,5):
    fps=ev(f'CNスコア>={th}', lambda m,t=th: m['cn']>=t, {'D'})
print()
for k in ['S1_ブランド直営出品','S2_ピンイン風セラー','S3_略号JPセラー','S4_中国式manufacturer','S5_非日本漢字','S6_越境OEM文体']:
    ev('  単独: '+k, lambda m,k=k: m['cn_sig'].get(k,0)>0, {'D'})
print()
print('=== 日本語シグナル: A1+A2の再現 ===')
for k in ['J1_ブランドが日本語','J2_manufacturerが日本語','J3_法人格表記','J4_日本語セラーが過半']:
    ev('  '+k, lambda m,k=k: m['jp'].get(k,0)>0, {'A1','A2'})
ev('  J1 or J2 (どちらか日本語)', lambda m: m['jp'].get('J1_ブランドが日本語',0)>0 or m['jp'].get('J2_manufacturerが日本語',0)>0, {'A1','A2'})
print()
print('=== メディアカテゴリ除外 → C の再現 ===')
ev('  主カテゴリがDVD/CD/本/洋書/ゲーム/PCソフト', lambda m: m['media_ratio']>=0.5, {'C'})
