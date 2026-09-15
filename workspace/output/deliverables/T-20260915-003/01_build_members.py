"""T-20260915-003 業界団体9名簿のHTML（agent_output/T-20260915-003/sources_html/ に保存・2026-09-15取得）→ members_raw.csv。
取得は curl で各1回・間隔1秒。会員登録・ログインなし。電話番号・住所は出力しない。
"""
import os; os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','agent_output','T-20260915-003','sources_html'))
import re,html,csv,glob
def lines(f):
    h=open(f,encoding='utf-8',errors='ignore').read()
    h=re.sub(r'<script.*?</script>|<style.*?</style>','',h,flags=re.S)
    t=html.unescape(re.sub(r'<[^>]+>','\n',h))
    return [l.strip() for l in t.split('\n') if l.strip()]
rows=[]
def add(cat,src,url,typ,name,note=''):
    name=re.sub(r'\s+',' ',name).strip(); 
    if name: rows.append(dict(カテゴリ=cat,名簿=src,URL=url,会員種別=typ,社名=name,備考=note))
# houseware
L=lines('houseware.html'); i=L.index('企業⼀覧'); j=L.index('取扱製品種別で探す')
for n in L[i+1:j]: add('ホーム＆キッチン','日本金属ハウスウェア工業組合（燕）','https://houseware.jp/company/','組合員',n)
# jpm
L=lines('jpm.html'); i=L.index('会社名'); j=L.index('Contents')
for n in L[i+1:j]:
    if re.fullmatch(r'[アカサタナハマヤラワ]行|このページの先頭へ',n): continue
    add('ホーム＆キッチン','日本プラスチック日用品工業組合','https://jpm.or.jp/kumiai/','組合員',n)
# petfood
raw=open('petfood.html',encoding='utf-8',errors='ignore').read()
cut=raw.index('賛助会員ここから')
for part,typ in ((raw[:cut],'正会員'),(raw[cut:],'賛助会員')):
    open('_pf.html','w').write(part)
    P=lines('_pf.html')
    for k in range(len(P)-1):
        if P[k]=='会社名': add('ペット用品','ペットフード協会','https://petfood.or.jp/outline-list/',typ,P[k+1])
# jppma
L=lines('jppma.html'); i=L.index('正会員'); j=L.index('ページ　TOP')
for n in L[i+1:j]:
    if n=='賛助会員': continue
    t='賛助会員' if n.startswith('(賛助会員') else '正会員'
    add('ペット用品','日本ペット用品工業会','https://www.jppma.or.jp/member/list.php',t,re.sub(r'^\(賛助会員[)）]\s*','',n))
# jaspo
L=lines('jaspo_list.html'); i=L.index('TEL/FAX')
for k in range(i+1,len(L)-1):
    if re.fullmatch(r'\d{1,3}',L[k]): add('スポーツ＆アウトドア','日本スポーツ用品工業協会（JASPO）','https://jaspo.org/member-list/','会員（メーカー・卸・小売混在）',L[k+1])
# jaftma
for line in open('jaftma_rows.tsv'):
    h,n,g=line.rstrip('\n').split('\t')
    t='賛助会員' if '賛助' in h else ('団体' if '団体' in h else '正会員')
    add('スポーツ＆アウトドア','日本釣用品工業会','https://www.jaftma.or.jp/about/member_list/',t,n,g)
# napac
L=lines('napac.html'); j=L.index('ＡＰ８２プレゼントキャンペーン'); i=[k for k,l in enumerate(L) if l=='会員一覧' and k<j][-1]
for n in L[i+1:j]:
    if re.fullmatch(r'[あかさたなはまやらわ]行|ページTOPへ|>|ホーム|会員一覧',n): continue
    add('車＆バイク','NAPAC（日本自動車用品・部品アフターマーケット振興会）','https://www.napac.jp/cms/ja/members','会員',n)
# jaama
L=lines('jaama.html'); i=L.index('備　考'); j=L.index('このページのトップへ')
prev=None
for n in L[i+1:j]:
    if re.fullmatch(r'[アカサタナハマヤラワ]行',n): continue
    if n in('賛助会員',):
        rows[-1]['会員種別']='賛助会員'; continue
    if re.fullmatch(r'理事長|副理事長|理事|監事|特別顧問',n): continue
    add('車＆バイク','全国自動車用品工業会（JAAMA）','https://www.jaama.gr.jp/member-companies/member-list.html','正会員',n)
# toys
L=lines('toys.html'); i=L.index('■さ行'); j=L.index('Copyright(C) The Japan Toy Assosiation.  All Rights Reserved')
buf=[]
for n in L[i+1:j]:
    if n.startswith('■'): continue
    buf.append(n)
# fix split tokens like '(' + '株)くもん出版' and '天栄' '(株)'
fixed=[]
k=0
while k<len(buf):
    n=buf[k]
    if n=='(' : fixed.append(n+buf[k+1]); k+=2; continue
    if n=='(株)' and fixed: fixed[-1]=fixed[-1]+'(株)'; k+=1; continue
    fixed.append(n); k+=1
grp=['愛知県玩具卸商業協同組合','大阪玩具事業協同組合','大阪府玩具・人形問屋協同組合連合会','おもちゃ団地協同組合','中部玩具人形工業会','東京玩具人形協同組合','日本空気入ビニール製品工業組合','日本バルーン協会','日本プラスチック玩具工業協同組合','日本プラモデル工業協同組合']
sup=['日通ＮＥＣロジスティクス(株)','日本ラボテック(株)','(株)バンダイロジパル','安田倉庫(株)']
for n in fixed:
    t='団体会員' if n in grp else ('賛助会員' if n in sup else '正会員（企業）')
    add('おもちゃ','日本玩具協会','https://www.toys.or.jp/kaiin_ichiran.html',t,n)
import collections
c=collections.Counter((r['カテゴリ'],r['名簿'],r['会員種別']) for r in rows)
for k,v in sorted(c.items()): print(k,v)
w=csv.DictWriter(open('members_raw.csv','w',encoding='utf-8-sig'),fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(len(rows))
