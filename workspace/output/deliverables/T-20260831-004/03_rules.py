# -*- coding: utf-8 -*-
"""仕入れ可能メーカー抽出 — 判定ルール群（T-20260831-003 / タケシ）
すべて 02_候補リスト_社長用.csv の既存列だけで計算できる（Keepaトークン不要）。"""
import re, unicodedata

JP = re.compile(r'[ぁ-んァ-ヶ一-龥]')
KANJI = re.compile(r'[一-龥]')
CN_PLACE = re.compile(
 r'shenzhen|shen ?zhen|dongguan|guangzhou|hangzhou|ningbo|yiwu|shanghai|shantou|foshan|'
 r'huizhou|zhongshan|xiamen|chengdu|jiangsu|zhejiang|guangdong|fujian|heyuan|danyang|'
 r'quanzhou|wenzhou|suzhou|qingdao|tianjin|chongqing|hefei|nanjing|wuhan|beijing|'
 r'technology co|tech co|trading co|electronic co|industrial co|e-commerce|limited company',
 re.I)
# 中国語ピンイン音節（日本語ローマ字に無い綴りを優先）
PINYIN = ('zh','xi','qi','ji','yu','ao','ang','eng','ong','uan','iao','ui','uo','ie','ue',
          'zi','ci','si','ri','shi','chi','xu','qu','ju','lv','nv','hui','gui','kui','zhu','shu')
CN_ONLY = re.compile(r'(zh|q[iuae]|xi|xu|[^aeiou]v|ng[a-z]|ao[a-z]|iu[a-z])', re.I)

MEDIA_CATS = {'DVD','ミュージック','本','洋書','ゲーム','PCソフト'}

HYPE = re.compile(r'業界(初|最|先端|トップ)|最強|超強力|世界初|驚異|究極|進化モデル|新登場|'
                  r'アップグレード版|20(2[4-9])(年|)(新|改良|最新)|同クラス最|大幅アップ|1台多役|'
                  r'先行発売|限定|驚き|話題')
BRACKET = re.compile(r'【[^】]{2,}】')

def norm(s): return unicodedata.normalize('NFKC', (s or '')).strip()

def tokens_sellers(row):
    return [t.strip() for t in norm(row.get('セラー名一覧','')).split('/') if t.strip()]

# ---------- 中国系OEM判定（6シグナル） ----------
def cn_signals(row):
    b = norm(row.get('メーカー/ブランド',''))
    mfr = norm(row.get('manufacturer',''))
    title = norm(row.get('商品名',''))
    sellers = tokens_sellers(row)
    sig = {}
    bl = re.sub(r'[^a-z0-9]','',b.lower())

    # S1 ブランド自身が出品者（公式/直営/専門店/-JP/OFFICIAL/Direct/Store）
    s1=[]
    for s in sellers:
        sl = re.sub(r'[^a-z0-9]','',s.lower())
        if bl and len(bl)>=3 and bl in sl:
            if re.search(r'公式|直営|直営店|専門店|販売店|OFFICIAL|Direct|Store|ストア|[-_ ]?jp\b|JP', s, re.I):
                s1.append(s)
    sig['S1_ブランド直営出品'] = s1

    # S2 セラー名がローマ字のみ8字以上で中国語ピンイン特徴を含む（日本語なし）
    s2=[]
    for s in sellers:
        if JP.search(s): continue
        core = re.sub(r'[^A-Za-z]','',s)
        if len(core) >= 8 and CN_ONLY.search(core) and not re.match(r'^A[0-9A-Z]{12,13}$', s):
            s2.append(s)
    sig['S2_ピンイン風セラー'] = s2

    # S3 セラー名が「大文字略号-JP」型（HCY-JP, LBW-JP, GUYU-JP…）
    s3=[t for t in sellers if re.match(r'^[A-Z]{2,6}[\-‐_ ]?JP\b', t) or re.search(r'[\-‐_]JP(店|)$', t)]
    sig['S3_略号JPセラー'] = s3

    # S4 manufacturer が中国地名/中国式社名
    sig['S4_中国式manufacturer'] = [mfr] if CN_PLACE.search(mfr) else []

    # S5 日本語に無い漢字（簡体字）が本文/社名に混入
    bad=set()
    for ch in title+b+mfr+' '.join(sellers):
        if '一'<=ch<='鿿':
            try: ch.encode('cp932')
            except Exception: bad.add(ch)
    sig['S5_非日本漢字'] = sorted(bad)

    # S6 タイトルが越境OEM文体（【】2個以上 かつ 誇大表現）かつブランドが非日本語ASCII
    s6 = bool(len(BRACKET.findall(title))>=2 and HYPE.search(title) and not JP.search(b))
    sig['S6_越境OEM文体'] = ['yes'] if s6 else []
    return sig

def cn_score(row):
    s = cn_signals(row)
    w = {'S1_ブランド直営出品':2,'S2_ピンイン風セラー':2,'S3_略号JPセラー':2,
         'S4_中国式manufacturer':3,'S5_非日本漢字':3,'S6_越境OEM文体':1}
    return sum(w[k] for k,v in s.items() if v), s

# ---------- 日本実体シグナル ----------
CORP = re.compile(r'株式会社|有限会社|合同会社|\(株\)|（株）|\(有\)|Co\.,? ?Ltd|K\.K\.|KK\b')
def jp_signals(row):
    b = norm(row.get('メーカー/ブランド','')); mfr = norm(row.get('manufacturer',''))
    sig={}
    sig['J1_ブランドが日本語'] = bool(JP.search(b))
    sig['J2_manufacturerが日本語'] = bool(JP.search(mfr))
    sig['J3_法人格表記'] = bool(CORP.search(b) or CORP.search(mfr))
    sellers = tokens_sellers(row)
    sig['J4_日本語セラーが過半'] = (sum(1 for s in sellers if JP.search(s)) > len(sellers)/2) if sellers else False
    return sig

# ---------- 名寄せノイズ ----------
COMPAT  = re.compile(r'対応|互換|純正と|\bfor\b|カートリッジ|トナーカートリッジ')   # 互換消耗品の説明文
NOBRAND = re.compile(r'^(ノーブランド品|ノーブランド|Generic|NoBrand|不明|-)$', re.I)

def is_nobrand(row):
    return bool(NOBRAND.match(norm(row.get('メーカー/ブランド',''))))

def jp_signal_valid(row):
    """manufacturer が『◯◯対応』等の互換消耗品の説明文の場合、日本語＝日本企業と読まない。"""
    b = norm(row.get('メーカー/ブランド','')); mfr = norm(row.get('manufacturer',''))
    if JP.search(b) and not COMPAT.search(b): return True
    if JP.search(mfr) and not COMPAT.search(mfr): return True
    return False

def is_media(row):
    return norm(row.get('カテゴリ','')).split(' > ')[0] in MEDIA_CATS
