# -*- coding: utf-8 -*-
import json, collections
lab=json.load(open('sample200_feat.json'))
def dist(rows,title):
    c=collections.Counter(r['label'] for r in rows); n=len(rows)
    a=c['A1']+c['A2']
    print(f"{title:<46} 残{n:4d}社  A本命{a:3d} ({a/n*100:4.1f}%)  "
          f"[A1 {c['A1']} A2 {c['A2']} B {c['B']} C {c['C']} D {c['D']} E {c['E']} F {c['F']}]")
    return rows
cur=dist(lab,'0. 現行の候補リスト(そのまま)')
cur=dist([r for r in cur if r['media_ratio']<0.5],'1. +メディアカテゴリ除外(社長論点2)')
cur=dist([r for r in cur if r['cn']<3],'2. +CNスコア>=3を除外(適合率100%帯)')
cur=dist([r for r in cur if r['cn']<1],'3. +CNスコア>=1を除外')
cur=dist([r for r in cur if r['jp'].get('J1_ブランドが日本語',0) or r['jp'].get('J2_manufacturerが日本語',0)],'4. +日本語シグナル必須')
print()
print('=== 4段階通過後の内訳（誤って残ったもの）===')
for r in cur:
    if r['label'] not in ('A1','A2'):
        print(f"  [{r['label']}] {r['maker']} / mfr:{r['mfr'][:28]} / {r['cat']}")
print()
print('=== 落としてしまった A本命（取りこぼし）===')
keep={id(r) for r in cur}
for r in lab:
    if r['label'] in ('A1','A2') and id(r) not in keep:
        why=[]
        if r['media_ratio']>=0.5: why.append('メディア')
        if r['cn']>=1: why.append(f"CN{r['cn']}:{[k for k,v in r['cn_sig'].items() if v]}")
        if not(r['jp'].get('J1_ブランドが日本語',0) or r['jp'].get('J2_manufacturerが日本語',0)): why.append('日本語シグナル無')
        print(f"  [{r['label']}] {r['maker']} <- {' / '.join(why)}")
