"""商品→メーカーの判定ロジック（純関数のみ。API に触らない）— T-20260930-001。

過去の判定資産をそのまま使う（写し直さない）:
- 区分（国内/海外ブランド/中国系OEM/中国系OEM疑い/代理店/版元/ブランド不明）
    = agent_output/T-20260914-002/takashi/t1_classify.py の segment()
- 既知の大手ブランド = 同 t1_bigbrands.py の known_big()（本ファイルで追加分を足す）
- 規模の判定済み台帳 = deliverables/T-20260831-004/35_全メーカー台帳_規模判定込み.csv
    （判定=除外（規模：大企業確定）/ 除外（海外・国内窓口なし）/ 理由コード L1・L2）
- gBizINFO の規模キャッシュ = agent_output/T-20260914-002/t1_gbiz_cache/size_by_maker.json

方針（memory: knowledge_company_size_gate_design）: **落とすのは「明らかに送信先でない」ものだけ**。
規模不明・区分が曖昧なものは落とさず残し、理由を列に書く。
"""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
T1 = REPO / "workspace/output/agent_output/T-20260914-002"

# ルートカテゴリの除外（ID は 2026-09-30 に /category で実測。推測しない＝memory keepa_api_gotchas）
EXCLUDE_ROOTS = [
    465392,      # 本
    52033011,    # 洋書
    561956,      # ミュージック（CD）
    561958,      # DVD
    637392,      # PCソフト
    637394,      # ゲーム（ソフトが主。周辺機器も含むが版元・大手が大半）
    2250738051,  # Kindleストア
    2128134051,  # デジタルミュージック
    2351649051,  # Prime Video
    2381130051,  # アプリ＆ゲーム
    4788676051,  # Alexaスキル
    2320455051,  # ファイナンス
    4976279051,  # Amazonデバイス・アクセサリ（メーカー＝Amazon）
]
# 除外せず「印」を付けるルート（薬機法・出品許可・期限管理の確認が要る）
MARK_ROOTS = {160384011: "ドラッグ", 52374051: "ビューティー", 57239051: "食品"}

ROOT_NAMES = {
    86731051: "文房具・オフィス用品", 13299531: "おもちゃ", 160384011: "ドラッグストア",
    3445393051: "産業・研究開発用品", 2017304051: "車＆バイク", 2277724051: "大型家電",
    2127209051: "パソコン・周辺機器", 3210981: "家電＆カメラ", 2277721051: "ホビー",
    2127212051: "ペット用品", 2229202051: "ファッション", 344845011: "ベビー＆マタニティ",
    57239051: "食品・飲料・お酒", 14304371: "スポーツ＆アウトドア", 2016929051: "DIY・工具・ガーデン",
    2123629051: "楽器・音響機器", 52374051: "ビューティー", 3828871: "ホーム＆キッチン",
}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, T1 / "takashi" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


c1 = _load("t1_classify")     # segment(), nrm(), is_single()
bb = _load("t1_bigbrands")    # known_big()

# t1_bigbrands に無い大手（T-20260914-006 の目視100件で漏れた社＋誰でも知る大手）。
# 迷うものは載せない。ここに載せる＝「明らかに送信先でない」。
EXTRA_BIG = """
taylormade テーラーメイド columbia コロンビア pokemon ポケモン sanrio サンリオ ikea イケア puma プーマ
rinnai リンナイ plus nakabayashi ナカバヤシ icom アイコム glidic microsoft マイクロソフト
nintendo 任天堂 capcom カプコン bandainamco バンダイナムコ kewpie キユーピー ajinomoto 味の素 meiji 明治
morinaga 森永 nissin 日清 kikkoman キッコーマン kirin キリン asahi アサヒ ito-en 伊藤園 itoen
kobayashi 小林製薬 rohto ロート製薬 taisho 大正製薬 kose コーセー kanebo カネボウ pola ポーラ
fancl ファンケル dhc orbis オルビス mandom マンダム kracie クラシエ earth アース製薬 fumakilla フマキラー
kinchou 金鳥 reckitt procter ピーアンドジー unilever ユニリーバ nestle ネスレ
nivea ニベア loreal ロレアル gillette ジレット oralb braun schick シック
tanita タニタ omron オムロン terumo テルモ
santen 参天製薬 bayer バイエル バイエル薬品 otsuka 大塚製薬 bauschlomb ボシュロム alcon アルコン iwatani 岩谷産業 イワタニ
kirkland カークランド ballantines バランタイン milbon ミルボン lebel ルベル タカラベルモント 北の達人コーポレーション
ine アイエヌイー hoyu ホーユー ホーユープロフェッショナル
mtg エムティージー ricoh リコー p&g pg ピーアンドジー 日清食品 sunstar サンスター 三菱ケミカル necプラットフォームズ nec 富士ソフト fujisoft
curel キュレル ドクターシーラボ drcilabo ジルスチュアート jillstuart レキットベンキーザー menicon メニコン maxell マクセル マクセルイズミ hololive ホロライブ
kingston キングストンテクノロジー yubico ユビコ titleist タイトリスト calvinklein カルバンクライン arcteryx アークテリクス burberry バーバリー
maisonmargiela メゾンマルジェラ aesop イソップ avene アベンヌ aramis アラミス umbro アンブロ avirex アヴィレックス optimumnutrition オプティマムニュートリション
doterra ドテラ spam スパム laphroaig ラフロイグ cuervo クエルボ compassbox コンパスボックス kirkland lanvin ランバン chloe クロエ nars ナーズ
レミーコアントロー remycointreau championpetfoods チャンピオンペットフーズ orijen 野村不動産ライフスポーツ
wizardsofthecoast ウィザーズオブザコースト yazaki 矢崎エナジーシステム 矢崎
富士通クライアントコンピューティング fujitsu 資生堂薬品 資生堂 アサヒグループ食品 アサヒフードアンドヘルスケア 日本ハム 住化エンバイロメンタルサイエンス
エヌテイテイドコモ nttdocomo ドコモ acer エイサー ヤクルトヘルスフーズ ヤクルト balmuda バルミューダ suqqu スック takeokikuchi タケオキクチ
waterpik ウォーターピック koss topps トップス jimmychoo ジミーチュウ olaplex オラプレックス soundpeats サウンドピーツ ルネサンス 東急スポーツオアシス
hobbywing ucloudlink ソリッドゴールド solidgold マイヤー meyer
chanel シャネル bvlgari ブルガリ hermes エルメス gucci グッチ prada プラダ armani アルマーニ versace ヴェルサーチェ jomalone ジョーマローン
lancome ランコム esteelauder エスティローダー clinique クリニーク clarins クラランス diptyque ディプティック tomford トムフォード guerlain ゲラン
shuuemura シュウウエムラ skii sk-ii cledepeaubeaute クレドポーボーテ ysl yvessaintlaurent イヴサンローラン dior ディオール christiandior
ウーノ オージュア aujua milbon ファイントゥデイ finetoday costco コストコ
kagome カゴメ starbucks スターバックス アミノバイタル コーセーコスメポート riketechnos リケンテクノス kahlua カルーア
stdupont エステーデュポン デュポン kaytee ケイティー
google グーグル corsair コルセア dolcegabbana ドルチェアンドガッバーナ wella ウエラ ウエラジャパン albion アルビオン francfranc フランフラン
""".split()


def _n(s: str) -> str:
    return c1.nrm(s)


EXTRA_BIG_N = {_n(x) for x in EXTRA_BIG if _n(x)}


CORP = re.compile(r"(株式会社|有限会社|合同会社|㈱|㈲|\(株\)|（株）)")


def known_big(brand: str, maker: str) -> str:
    hit = bb.known_big(brand, maker)
    if hit:
        return hit
    for name in (brand, maker):
        name = CORP.sub("", name or "")  # 「株式会社◯◯」→「◯◯」
        for n in bb._parts(name):  # 「サンリオ(SANRIO)」→ サンリオ / sanrio / 全体
            for k in EXTRA_BIG_N:
                if n == k or (len(k) >= 6 and n.startswith(k)):
                    return k
    return ""


# ---- 過去の判定済み台帳（T-20260831-004）----
def _ledger() -> dict[str, dict]:
    p = REPO / "workspace/output/deliverables/T-20260831-004/35_全メーカー台帳_規模判定込み.csv"
    out: dict[str, dict] = {}
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[_n(r["メーカー"])] = r
    return out


LEDGER = _ledger()
_SIZE_P = T1 / "t1_gbiz_cache" / "size_by_maker.json"
SIZE = {_n(k): v for k, v in json.loads(_SIZE_P.read_text(encoding="utf-8")).items()} if _SIZE_P.exists() else {}

# manufacturer 欄に入る「社名でないもの」の典型
NOT_COMPANY = re.compile(r"^(不明|非公開|国内メーカー|unknown|none|n/?a|その他|other|-+)$", re.I)


def maker_key(p: dict) -> tuple[str, str]:
    """メーカー単位に寄せるキーと表示名。manufacturer 優先・無ければ brand。"""
    brand = (p.get("brand") or "").strip()
    maker = (p.get("manufacturer") or "").strip()
    name = maker if maker and not NOT_COMPANY.match(maker) and not c1.DESC.search(maker) else brand
    # 「マタインク CRG-051H」「マタインク 29J TN29J…」のように manufacturer にブランド＋型番が入る行は、
    # 型番ごとに別の社に割れる（2026-10-04 の抜き取りで同じ社が3行に割れていた）。ブランドで始まり型番が続く形はブランドに寄せる
    if brand and name != brand and name.startswith(brand) and re.search(r"[0-9A-Z]{2,}[-0-9A-Z]*", name[len(brand):]):
        name = brand
    return (_n(name) or "(空)"), name


def prior_verdict(brand: str, maker: str) -> tuple[str, str]:
    """過去台帳と gBiz キャッシュからの判定。戻り値 (除外理由 or '', 根拠)。"""
    for name in (maker, brand):
        k = _n(name)
        if not k:
            continue
        r = LEDGER.get(k)
        if r:
            if r["判定"].startswith("除外（規模"):
                return "大手（過去判定）", "T-20260831-004 台帳: " + r["判定理由"][:30]
            if r["判定"].startswith("除外（海外"):
                return "海外（過去判定）", "T-20260831-004 台帳: " + r["判定理由"][:30]
            if r.get("理由コード") in ("L1", "L2"):
                return "大手（gBiz）", "T-20260831-004 台帳: " + r["理由"][:40]
        s = SIZE.get(k)
        if s and s.get("理由コード") in ("L1", "L2"):
            return "大手（gBiz）", "gBiz: " + s.get("理由", "")[:40]
    return "", ""


# ---- 救済（2026-10-01 追加）----
# 「中国系OEM疑い」「海外ブランド疑い（JANが国内でない）」は代表 ASIN 1本の機械判定で、国内の英字ブランドを巻き込む
# （BURTLE・CIO 型）。メーカー単位（同じ社に寄せた全 ASIN）で日本の実体シグナルを探し、1つでもあれば区分の除外を打ち消す。
# **救済は区分の除外だけを打ち消す。大手判定は救済の後でも必ず当てる**（memory: amazon_first_maker_extraction の罠1）。
RESCUABLE = ("中国系OEM疑い", "海外ブランド疑い（JANが国内でない）")
_GBIZ_P = REPO / "workspace/output/agent_output/T-20260930-001/gbiz/exact_by_name.json"
GBIZ_EXACT = json.loads(_GBIZ_P.read_text(encoding="utf-8")) if _GBIZ_P.exists() else {}


# gBiz で偶然一致しやすい「社名でない」ブランド表記（Generic → 有限会社ＧＥＮＥＲＩＣ）
NOT_NAME = {"generic", "ノーブランド", "noname", "nobrand", "unknown", "不明"}


def _jp_ledger(name: str) -> str:
    """過去台帳での日本実体。**「manufacturer が日本語」だけは使わない**（中国系セラーも日本語で書く：LEACCO公式店）。
    使うのは JAN45/49・日本の法人格・法人番号・人が卸の証拠まで見た「連絡候補」だけ。"""
    r = LEDGER.get(_n(name))
    if not r or r["判定"].startswith(("除外（海外", "除外（日本実体", "除外（会社名")):
        return ""
    sig = r.get("日本実体シグナル") or ""
    if r["判定"] == "連絡候補" or r.get("法人番号") or "JAN45/49" in sig or "日本法人格" in sig:
        return f"T-20260831-004台帳（{r['判定']}・{sig}）"
    return ""


def _jp_gbiz(name: str) -> str:
    if _n(name) in {_n(x) for x in NOT_NAME}:
        return ""
    s = SIZE.get(_n(name))
    if s and s.get("法人番号"):
        return f"gBiz完全一致1社（{s.get('gBiz商号') or ''}）"
    g = GBIZ_EXACT.get(name)
    # 一般社団法人・財団法人はメーカーでない（harness → 一般社団法人Ｈａｒｎｅｓｓ の偶然一致・2026-10-04 抜き取り）
    if g and len(g) == 1 and not any(x in g[0]["name"] for x in ("社団法人", "財団法人", "ＬＬＣ", "LLC")):
        return f"gBiz完全一致1社（{g[0]['name']}）"
    return ""


def rescue_signals(group: list[dict]) -> list[str]:
    """メーカー単位の日本実体シグナル。group = 同じ社に寄せた product の list。"""
    sig: list[str] = []
    if any(c1.ean_cc(p.get("eanList")) == "JP" for p in group):
        sig.append("JAN45/49の商品あり")
    makers = {(p.get("manufacturer") or "").strip() for p in group} - {""}
    if any(c1.JP_CORP.search(m) and not c1.DESC.search(m) for m in makers):
        sig.append("manufacturerに日本の法人格")
    # 「日本オスモ」「◯◯ジャパン」＝海外ブランドの日本法人・輸入総代理店の典型（2026-10-04 抜き取りで取りこぼしを確認）。
    # 日本語表記つきに限る（英字の "xxx-JP" は中国系セラーも名乗るので使わない）
    if any(re.search(r"(日本|ジャパン)", m) and not c1.DESC.search(m) for m in makers):
        sig.append("manufacturerが日本法人名（日本◯◯／◯◯ジャパン）")
    names = makers | {(p.get("brand") or "").strip() for p in group} - {""}
    for n in sorted(names):
        for f in (_jp_ledger, _jp_gbiz):
            w = f(n)
            if w and w not in sig:
                sig.append(w)
    return sig


def classify(p: dict, group: list[dict] | None = None) -> tuple[str, str, str]:
    """1社の判定（代表 product ＋同じ社の全 product）。戻り値 (除外理由 or '', 根拠, 救済理由)。除外理由が空なら残す。"""
    group = group or [p]
    brand, maker = p.get("brand") or "", p.get("manufacturer") or ""
    seg, why = c1.segment(p)
    if c1.DESC.search(maker):  # 「マタインク for キヤノン用…」の説明中の他社名で大手判定しない
        maker = ""
    sig = rescue_signals(group)
    rescue = "・".join(sig)
    if seg in ("海外ブランド", "中国系OEM", "版元", "ブランド不明"):
        return seg, why, ""
    if seg == "中国系OEM疑い" and not sig:
        return seg, why, ""
    kb = known_big(brand, maker)
    if kb:
        return "大手（既知リスト）", kb, ""
    pv, pwhy = prior_verdict(brand, maker)
    if pv:
        return pv, pwhy, ""
    cc = c1.ean_cc(p.get("eanList"))
    if cc in ("OTHER", "US") and not c1.JP_CORP.search(maker) and not sig:
        return "海外ブランド疑い（JANが国内でない）", f"EAN={cc}", ""
    rescued_from = ""
    if seg == "中国系OEM疑い":
        rescued_from = "中国系OEM疑い"
    elif cc in ("OTHER", "US") and not c1.JP_CORP.search(maker):
        rescued_from = "海外ブランド疑い（JANが国内でない）"
    if rescued_from:
        return "", f"救済（元：{rescued_from}）", rescue
    if seg == "代理店":
        return "", "代理店（輸入元。国内窓口として残す）", ""
    return "", "", ""


if __name__ == "__main__":
    assert known_big("サンリオ(SANRIO)", "") and known_big("", "任天堂")
    assert known_big("BOS", "") == ""
    print("maker_rules ok", len(LEDGER), len(SIZE))
