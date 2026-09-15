"""T-20260915-003 業界団体9名簿 → メーカー候補の一覧と件数（0 token・Keepa 不使用）。
入力: agent_output/T-20260915-003/sources_html/members_raw.csv（build.py が名簿HTMLから作成）
出力: 02_メーカー一覧_業界団体名簿.csv（PUBLIC）／out/02_照合フラグ付き.csv（ギフトショー・T-1 照合。Git 追跡外）
"""
import csv,re,unicodedata,collections,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
RAW=ROOT/'agent_output'/'T-20260915-003'/'sources_html'/'members_raw.csv'
spec=importlib.util.spec_from_file_location('bb',ROOT/'agent_output'/'T-20260914-002'/'takashi'/'t1_bigbrands.py')
bb=importlib.util.module_from_spec(spec); spec.loader.exec_module(bb)

def key(s):
    s=unicodedata.normalize('NFKC',s or '')
    s=re.sub(r'\((株|有|同|一社)\)|㈱|㈲|株式会社|有限会社|合同会社','',s)
    s=re.sub(r'\s.*(事業部|ディビジョン|オフィス)$','',s)
    return re.sub(r'[\s・\.\-−_,、\'&/]','',s).lower()

# 非メーカー（名簿に載っているが仕入れ先のメーカーではない）。名前と周知の業態からの判定
NONMAKER={
 '小売':['アルペン','ゼビオ','イエローハット','オートバックスセブン','タイヤワールド館ベスト','ブリヂストンリテールジャパン','日本トイザらス','博品館','大創産業','イオンペット','カインズ','綿半パートナーズ','アマゾンジャパン','イオントップバリュ','フジ・コーポレーション','ササキスポーツ'],
 '物流・倉庫':['日通ＮＥＣロジスティクス','日通NECロジスティクス','バンダイロジパル','安田倉庫','日本通運','丸紅ロジスティクス','日本ラボテック'],
 '検査・認証':['SGSジャパン','食品環境検査協会','食品分析開発センター','日本食品分析センター','ボーケン品質評価機構','ニッセンケン品質評価センター','ユーロフィンQKEN','MERIEUX NUTRISCIENCES','テレコムエンジニアリングセンター','アイデックス ラボラトリーズ'],
 '保険・金融':['アニコム損害保険','第一アイペット損害保険','リトルファミリー少額短期保険'],
 '総合商社・卸':['三井物産','兼松','新生紙パルプ商事','ハピネット','阿部商会'],
 'メディア・IT・展示会・その他':['釣りビジョン','ブロードリーフ','ジャパン・メディア・システムズ','メッセフランクフルトジャパン','旭化成ホームズ','日本アムウェイ','OTオートモーティブサービス','PETOKOTO'],
}
NM={key(n):c for c,l in NONMAKER.items() for n in l}
# 外資の日本法人（名称・周知の親会社から明らかなものだけ。空欄＝未判定）
FOREIGN=['アディダス・ジャパン','アメアスポーツジャパン','ニューバランスジャパン','プーマジャパン','ユナイテッドスポーツブランズジャパン','ローリングスジャパン','テーラーメイドゴルフ','ピュア・フィッシング・ジャパン','ラパラ・ジャパン','ハズブロジャパン','マテル・インターナショナル','レゴジャパン','ラベンスバーガージャパン','マイクロスクーター・ジャパン','プラントイジャパン','スペクトラム ブランズ ジャパン','マース ジャパン リミテッド','日本ヒルズ・コルゲート','ネスレ日本','ロイヤルカナン ジャポン','ファルミナペットフーズ・ジャパン','ベーリンガーインゲルハイム アニマルヘルス ジャパン','日本ビルバック','ウェルペット・ジャパン','Vesync Japan','日本グッドイヤー','BBSジャパン','オーゼットジャパン','日本アムウェイ','スホﾟﾙﾃﾞｨﾝｸﾞｼﾞｬﾊﾟﾝ','ｽﾎﾟﾙﾃﾞｨﾝｸﾞｼﾞｬﾊﾟﾝ','アマゾンジャパン']
FK={key(n) for n in FOREIGN}
# 大手の補足（上場企業・周知の大手グループ。網羅ではない）
BIGPLUS=['デサント','ゴールドウイン','住友ゴム工業','グローブライド','横浜ゴム','カヤバ','大王製紙','貝印','天馬','アロン化成','サンリオ','大創産業','イエローハット','オートバックスセブン','ハピネット','日本トイザらス','ネスレ日本','日本ヒルズ・コルゲート','マース ジャパン リミテッド','エステー','アルペン','ゼビオ','ブリヂストンリテールジャパン','日本グッドイヤー','日本通運','三井物産','兼松','旭化成ホームズ','理研ビタミン','はごろもフーズ','アマゾンジャパン','イオントップバリュ','イオンペット','アース・ペット','ライオンペット','ユニ・チャーム','アイリスオーヤマ','エバニュー','学研ステイフル','パイロットコーポレーション','ショウワノート','くもん出版','幻冬舎','共立製薬','サントリーウエルネス','住商アグロインターナショナル','丸紅ロジスティクス','日通ＮＥＣロジスティクス','安田倉庫','ピジョン','トンボ']
BK={key(n) for n in BIGPLUS}
def is_group(n,t):
    return t in('団体会員',) or re.search(r'協会|組合|連合会|工業会|NPO法人|一般財団法人|一般社団法人|\(一社\)',n)
TRADE=re.compile(r'商事|商会|貿易|通商|トレーディング|問屋')

rows=list(csv.DictReader(open(RAW,encoding='utf-8-sig')))
# gBizINFO 従業員数（T-1 で既に照合済みのものだけ。新規 API 呼び出しなし）
D=ROOT/'deliverables'
emp={}
for t in csv.DictReader(open(D/'T-20260914-002'/'out'/'t1_all.csv',encoding='utf-8-sig')):
    v=t.get('従業員数(gBiz)','').strip()
    if not v: continue
    for f in ('メーカー','ブランド'):
        b=unicodedata.normalize('NFKC',t[f] or '')
        for p in [b,re.sub(r'\([^)]*\)','',b)]+re.findall(r'\(([^)]*)\)',b):
            k=key(p)
            if len(k)>=2: emp.setdefault(k,v)
gift={key(g['exhibitor']):g['class'] for g in csv.DictReader(open(D/'T-20260906-005'/'20_出展社2353件の機械分類.csv',encoding='utf-8-sig'))}
t1=set()
for t in csv.DictReader(open(D/'T-20260914-002'/'out'/'t1_all.csv',encoding='utf-8-sig')):
    for f in ('メーカー','ブランド'):
        b=unicodedata.normalize('NFKC',t[f] or '')
        for p in [b,re.sub(r'\([^)]*\)','',b)]+re.findall(r'\(([^)]*)\)',b):
            k=key(p)
            if len(k)>=2: t1.add(k)

out=[]
for r in rows:
    n=r['社名']; k=key(n)
    if is_group(n,r['会員種別']): cls='団体（メーカーでない）'
    elif k in NM: cls='非メーカー：'+NM[k]
    elif r['名簿'].startswith('日本スポーツ用品工業協会'): cls='メーカー候補（JASPOは卸・小売を含む・未分類）'
    else: cls='メーカー候補'
    big=bb.known_big(n) or ('既知' if k in BK else '')
    out.append({'カテゴリ':r['カテゴリ'],'社名':n,'名簿':r['名簿'],'会員種別':r['会員種別'],'名簿URL':r['URL'],
        '区分':cls,'外資の日本法人':'はい' if k in FK else '','大手（既知リスト）':'はい' if big else '',
        '従業員数（gBizINFO）':emp.get(k,''),'商社語を含む社名':'はい' if TRADE.search(n) else '',
        '取扱品目（名簿記載）':r['備考'],'EC直販の有無':'未調査','_key':k,'_gift':gift.get(k,''),'_t1':'一致' if k in t1 else ''})

pub=[{c:v for c,v in o.items() if not c.startswith('_')} for o in out]
with open(HERE/'02_メーカー一覧_業界団体名簿.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(pub[0])); w.writeheader(); w.writerows(pub)
with open(HERE/'out'/'02_照合フラグ付き.csv','w',encoding='utf-8-sig',newline='') as f:
    fl=[c for c in out[0] if c!='_key']; w=csv.DictWriter(f,fieldnames=fl); w.writeheader()
    for o in out: w.writerow({c:o[c] for c in fl})

# 集計（カテゴリ内は名寄せキーで重複除去）
S={}
cats=['ホーム＆キッチン','ペット用品','スポーツ＆アウトドア','車＆バイク','おもちゃ']
allmk={}
for c in cats:
    rs=[o for o in out if o['カテゴリ']==c]
    byk=collections.OrderedDict()
    for o in rs: byk.setdefault(o['_key'],o)
    mk={k:o for k,o in byk.items() if o['区分'].startswith('メーカー候補')}
    for k,o in mk.items(): allmk.setdefault(k,o)
    fo=sum(1 for o in mk.values() if o['外資の日本法人']); bg=sum(1 for o in mk.values() if o['大手（既知リスト）'] and not o['外資の日本法人'])
    sm=sum(1 for o in mk.values() if o['従業員数（gBizINFO）'] and int(o['従業員数（gBizINFO）'])<=300)
    S[c]=dict(名簿の行=len(rs),重複除去後=len(byk),団体=sum(1 for o in byk.values() if o['区分'].startswith('団体')),
        非メーカー=sum(1 for o in byk.values() if o['区分'].startswith('非メーカー')),メーカー候補=len(mk),うち外資=fo,うち大手=bg,
        残り国内の中小候補=len(mk)-fo-bg,うちgBizで300人以下確認=sm,商社語=sum(1 for o in mk.values() if o['商社語を含む社名']),
        ギフトショー一致=sum(1 for o in mk.values() if o['_gift']),T1一致=sum(1 for o in mk.values() if o['_t1']))
fo=sum(1 for o in allmk.values() if o['外資の日本法人']); bg=sum(1 for o in allmk.values() if o['大手（既知リスト）'] and not o['外資の日本法人'])
S['5カテゴリ合計（カテゴリ間の重複も除去）']=dict(メーカー候補=len(allmk),うち外資=fo,うち大手=bg,残り国内の中小候補=len(allmk)-fo-bg,
    ギフトショー一致=sum(1 for o in allmk.values() if o['_gift']),T1一致=sum(1 for o in allmk.values() if o['_t1']))
json.dump(S,open(HERE/'out'/'summary.json','w'),ensure_ascii=False,indent=1)
for c,v in S.items(): print(c,v)
print('rows',len(out))
