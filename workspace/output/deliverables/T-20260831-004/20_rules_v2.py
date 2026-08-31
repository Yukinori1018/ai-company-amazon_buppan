# -*- coding: utf-8 -*-
"""国内取引成立性ルール v2（scan_v15 移植用）。

v1 からの修正:
  - is_random_lowercase_run をセラー名の除外根拠から外した
    （thebookcommunity / thurmanbooks / soragadgetshop など英語圏の正常な店名を
      207/250 件で誤検出。実測済み）
  - is_gibberish_latin をゲートから外した
    （KÄRCHER / TP-Link を母音率で誤検出。実測済み）→ スコアの減点にのみ使う
  - **日本実体シグナル（S級）が1つでもあれば、海外シグナルより優先する**
    （Logitech / INTEX は中国製造の EAN を持つが日本法人がある。実測済み）
"""
import re, unicodedata

JP_ANY   = re.compile(r"[぀-ゟ゠-ヿ一-鿿]")
KANA     = re.compile(r"[぀-ゟ゠-ヿ]")
JP_CORP  = re.compile(r"(株式会社|㈱|\(株\)|（株）|有限会社|㈲|合同会社|合資会社|合名会社|"
                      r"財団法人|社団法人|協同組合|製作所|工業所|商会|商店|工房)")
INVOICE  = re.compile(r"(適格請求書|インボイス)")

# --- 中国企業であることの直接表記 ---
CN_CORP  = re.compile(r"(有限公司|股份|责任公司|責任公司)")
CN_PLACE = re.compile(r"(深圳|广州|廣州|东莞|東莞|义乌|義烏|惠州|佛山|宁波|寧波|厦门|廈門|"
                      r"温州|溫州|泉州|汕头|汕頭|中山市|珠海|揭阳|揭陽|郑州|鄭州|合肥|东莞市)")
CN_SIMP  = re.compile(r"[电产业务发网际经济营销质检购卖买这们对说见图报纸车马鸟鱼龙东华农实术设备机械厂县镇圳莞]")

# --- ピンイン語基（実測でFPゼロ。単独では弱、2語基以上で強）---
PINYIN_STRONG = re.compile(
    r"(youxiangongsi|youxian ?gongsi|gongsi|keji|maoyi|shangmao|wangluo|dianzi|"
    r"shenzhen|guangzhou|dongguan|yiwu|huizhou|ningbo|xiamen|foshan|zhongshan|"
    r"quanzhou|wenzhou|jinhua|hefei|zhengzhou|nongye|shiye|baihuo|jiaju)", re.I)

# --- 「メーカー直営」を名乗るだけの店（卸していない証拠）---
DIRECT_SHOP = re.compile(r"(直営|公式ストア|公式直営|オフィシャルストア|official ?store|"
                         r"メーカー直販|正規販売店)", re.I)
# --- 名前が解決できなかったセラー（Keepa が sellerId を返しただけ）---
SELLER_ID = re.compile(r"^A[0-9A-Z]{9,17}$")

# --- 再販/版元カテゴリ（今回は母集団から外す）---
REDIST_ROOT = {"DVD", "ミュージック", "本", "洋書", "ゲーム", "Kindleストア", "PCソフト",
               "デジタルミュージック", "Prime Video"}

def nrm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^0-9a-z぀-ゟ゠-ヿ一-鿿]", "", s)

def ean_cc(eans):
    for e in (eans or []):
        s = str(e).zfill(13)
        if s[:2] in ("45", "49"): return "JP"
        if s[:3] in tuple(f"69{i}" for i in range(10)): return "CN"
        if s[:3] in ("978", "979"): return "ISBN"
        if s[0] == "0" or s[:2] in ("01","02","03","04","05","06","07","08","09"): return "US"
        return "OTHER"
    return None

# ==========================================================================
# manufacturer が「社名」か「商品説明文」かの判定
# ==========================================================================
# 実測した defect: manufacturer に商品説明が入っている行がある。
#   例) "GPC Image Flex ( ブラザー LC3117 対応"  "ejet SAT SAT-6CL サツマイモ インク"
#       "マタインク for Canon インク BCI300 BCI301"
# この日本語は「対応機種の説明」であって社名ではない。互換インクの中国系ブランドが
# 「manufacturer日本語」で全部すり抜けていた。社名らしさを先に確かめる。
DESC_WORDS = re.compile(r"(対応|互換|\bfor\b|用\b|セット|枚入|個入|純正|型番|"
                        r"[A-Z]{2,}[- ]?\d{2,})", re.I)

def is_company_like(m: str) -> bool:
    """manufacturer が社名として使えるか。長い・商品説明語を含む・括弧つきは不可。"""
    m = (m or "").strip()
    if not m or len(m) > 25:            return False
    if DESC_WORDS.search(m):            return False
    if "(" in m or "（" in m:           return False
    if len(m.split()) > 3:              return False
    return True

# ==========================================================================
# S級：メーカー側に日本の実体がある証拠
# ==========================================================================
def s_jp_signals(maker, manufacturers, eancc_counter):
    s = set()
    good = [m for m in manufacturers if is_company_like(m)]
    if eancc_counter.get("JP"):                       s.add("JAN45/49")
    if JP_ANY.search(maker or ""):                    s.add("メーカー名日本語")
    if any(JP_ANY.search(m) for m in good):           s.add("manufacturer日本語")
    if JP_CORP.search(maker or "") or any(JP_CORP.search(m) for m in good):
        s.add("日本法人格")
    return s

# ==========================================================================
# 海外（日本に窓口がない）証拠 ※S級が1つでもあれば無効化される
# ==========================================================================
def cn_signals(maker, manufacturers, sellers):
    s = set()
    names = [maker] + list(manufacturers)
    for n in names:
        if CN_CORP.search(n or "") or CN_PLACE.search(n or "") or CN_SIMP.search(n or ""):
            s.add("メーカー名が中国企業表記"); break
    if len(PINYIN_STRONG.findall(nrm(maker))) >= 2:  s.add("メーカー名がピンイン連結")
    cn_sellers = [x for x in sellers
                  if CN_CORP.search(x) or CN_PLACE.search(x) or CN_SIMP.search(x)
                  or len(PINYIN_STRONG.findall(nrm(x))) >= 1]
    if cn_sellers: s.add("セラー名に中国企業表記/ピンイン")
    return s, cn_sellers

# ==========================================================================
# 卸証拠：独立セラー（ブランド系列店・直営店・名前未解決を除いた第三者）
# ==========================================================================
def independent_sellers(brand_norm, sellers):
    out = []
    for x in sellers:
        n = nrm(x)
        if SELLER_ID.match(x.strip()):        continue      # 名前が解決できていない
        if DIRECT_SHOP.search(x):             continue      # 直営を名乗る店
        if brand_norm and len(brand_norm) >= 3 and (brand_norm in n or (len(n) >= 3 and n in brand_norm)):
            continue                                        # ブランド系列店
        out.append(x)
    return out

def jp_sellers(sellers):
    """日本の事業者と判定できるセラー。

    かな or 日本法人格 or インボイス登録 or 漢字（中国語マーカーが無い場合）。
    漢字を足した理由: `ABEAM RIDESHOP (木曜日定休)` `國光商店` のような
    「かなが1文字も無い日本語店名」を取りこぼしていた（実測）。
    ただし漢字は日中共通なので、中国企業表記・地名・簡体字があれば除く。
    """
    out = []
    for x in sellers:
        if CN_CORP.search(x) or CN_PLACE.search(x) or CN_SIMP.search(x):
            continue
        if KANA.search(x) or JP_CORP.search(x) or INVOICE.search(x) or re.search(r"[一-鿿]", x):
            out.append(x)
    return out


def unresolved_sellers(sellers):
    """Keepa が名前を解決できず sellerId のまま返したセラー。

    実測 2.8%（8,713件中242件）。45社は全商品で全セラーが未解決。
    **これを「直営店」と同じ扱いにすると、曙産業・筒井時正商店のような
    国内SMEを『卸の証拠なし』で捨てる。** 判定保留として残すこと。
    """
    return [x for x in sellers if SELLER_ID.match(x.strip())]
