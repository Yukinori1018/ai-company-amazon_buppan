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
kinchou 金鳥 sc johnson reckitt pg procter ピーアンドジー unilever ユニリーバ nestle ネスレ
nivea ニベア loreal ロレアル gillette ジレット oralb braun schick シック
tanita タニタ omron オムロン terumo テルモ
""".split()


def _n(s: str) -> str:
    return c1.nrm(s)


EXTRA_BIG_N = {_n(x) for x in EXTRA_BIG if _n(x)}


def known_big(brand: str, maker: str) -> str:
    hit = bb.known_big(brand, maker)
    if hit:
        return hit
    for name in (brand, maker):
        n = _n(name)
        for k in EXTRA_BIG_N:
            if n == k or (len(k) >= 4 and n.startswith(k)):
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
NOT_COMPANY = re.compile(r"^(不明|unknown|none|n/?a|その他|other|-+)$", re.I)


def maker_key(p: dict) -> tuple[str, str]:
    """メーカー単位に寄せるキーと表示名。manufacturer 優先・無ければ brand。"""
    brand = (p.get("brand") or "").strip()
    maker = (p.get("manufacturer") or "").strip()
    name = maker if maker and not NOT_COMPANY.match(maker) and not c1.DESC.search(maker) else brand
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


def classify(p: dict) -> tuple[str, str]:
    """1商品のメーカー判定。戻り値 (除外理由 or '', 根拠)。空なら残す。"""
    brand, maker = p.get("brand") or "", p.get("manufacturer") or ""
    seg, why = c1.segment(p)
    if seg in ("海外ブランド", "中国系OEM", "中国系OEM疑い", "版元", "ブランド不明"):
        return seg, why
    kb = known_big(brand, maker)
    if kb:
        return "大手（既知リスト）", kb
    pv, pwhy = prior_verdict(brand, maker)
    if pv:
        return pv, pwhy
    if seg == "代理店":
        return "", "代理店（輸入元。国内窓口として残す）"
    return "", ""


if __name__ == "__main__":
    assert known_big("サンリオ(SANRIO)", "") and known_big("", "任天堂")
    assert known_big("BOS", "") == ""
    print("maker_rules ok", len(LEDGER), len(SIZE))
