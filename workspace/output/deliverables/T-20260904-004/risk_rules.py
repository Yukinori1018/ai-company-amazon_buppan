#!/usr/bin/env python3
"""「買ってはいけないリスト」を機械判定に落とす — T-20260904-004 / D。

出典は同ディレクトリの `research/draft.md`（2026-09-04 リサーチャー確定版）。
第1部の除外リスト（#1〜#15）と第2部の「初回に向く4群」を、そのまま関数にしてあります。
draft の番号を `rule_id` に持たせてあるので、判定結果から原典に戻れます。

━━ 設計の方針 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **判定は純関数**にする。CSV も API も知らない。だからテストできる（tests_risk_rules.py）。
2. **落とした理由を必ず1つ返す**。「なんとなく落ちた」を作らない。
3. **判定できないものは「要目視」と言う。**「たぶん新品」で通さない（社長の明示指示）。

━━ 正直に書いておく限界 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
draft #2「ブランドが付いた商品全般を除外」は、**機械適用すると候補が 0 件になります**。
Keepa の `brand` フィールドは 19,864件中 19,844件（99.9%）で埋まっており、
ノーブランド雑貨にも卸元の社名がブランドとして登録されているためです。
そこで本モジュールは brand を2段に分けます。

    Tier A（機械除外）… 著名ブランド・大手メーカー。誤爆しても惜しくない側に倒す
    Tier B（残す・要実機確認）… それ以外。**全SKUに「ゲート未確認」の印を必ず付ける**

Tier B を残す判断はタカシの実装判断であって、draft の緩和ではありません。
最終判定はセラーセントラルの実機（draft 2-D #9）で行う、という原典の但し書きに従っています。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# =============================================================================
# 語彙。**すべて draft.md 由来**。思いつきで足さないこと（足すならコメントに出典を書く）
# =============================================================================

# draft #4 / 反転条件③: NETSEA には中古品が実在する（2026-08-31 実測212件）
USED_KEYWORDS = [
    "中古", "USED", "used", "Used", "ユーズド", "中古品",
    "ヴィンテージ", "ビンテージ", "vintage", "Vintage",
    "リユース", "リサイクル品", "古着", "アウトレット", "outlet", "OUTLET",
    "開封済", "開封品", "返品", "訳あり", "ワケあり", "わけあり", "B品", "難あり",
    "未使用に近い", "再生品", "リファービッシュ",
]

# draft #1: 電気用品（PSE）。電源につなぐ／電池が入っている／充電する物すべて
ELECTRIC_KEYWORDS = [
    "電源", "電池", "乾電池", "充電", "充電式", "充電器", "バッテリー", "モバイルバッテリー",
    "ACアダプタ", "AC アダプタ", "アダプター", "コンセント", "延長コード", "電源コード",
    "リチウム", "USB", "Bluetooth", "ブルートゥース", "Wi-Fi", "WiFi", "無線",
    "LED", "led", "ＬＥＤ", "照明", "ライト", "ランプ", "電球", "蛍光灯",
    "電動", "電気", "ヒーター", "ドライヤー", "扇風機", "サーキュレーター", "加湿器",
    "除湿", "空気清浄", "掃除機", "炊飯", "電子レンジ", "オーブン", "トースター",
    "コンロ", "IH", "ミキサー", "ブレンダー", "シェーバー", "バリカン", "アイロン",
    "スピーカー", "イヤホン", "ヘッドホン", "カメラ", "プリンタ", "モニター",
    "モーター", "コンプレッサー", "ポンプ", "イルミネーション", "電飾",
    # 2026-09-06 追記: 初回の出力に「プロジェクター機能付ウェザークロック」「ウェザー
    # インフォクロック」が残っていた。乾電池で動く小物を名前で拾えていなかったため。
    # draft #1 は「電池が入っている物すべて」なので、電池駆動の小物もここで落とす。
    "時計", "クロック", "ウォッチ", "目覚まし", "アラーム", "ブザー",
    "プロジェクター", "ラジオ", "リモコン", "センサー", "電卓", "電子",
    "温湿度", "湿度計", "体重計", "体組成", "歩数計", "タイマー",
]
# 誤爆よけ。「LEDライト用の電池を含まない交換シェード」のような物まで落とすと母数が死ぬが、
# 初回は**落とす側に倒す**（draft 結論3: 除外は「慎重に」ではなく「買わない」で運用する）。
# 例外にするのはこの語が含まれる場合だけ（＝電気を使わないことが名前で確定するもの）。
ELECTRIC_SAFE_OVERRIDES = ["電池不要", "電源不要", "電気を使わない", "非電動", "手動"]

# draft #3: 化粧品・コスメ・医薬部外品
COSMETIC_KEYWORDS = [
    "化粧品", "化粧水", "美容液", "乳液", "クリーム", "ファンデーション", "リップ",
    "口紅", "アイシャドウ", "マスカラ", "アイライナー", "チーク", "ネイル", "マニキュア",
    "除光液", "コスメ", "医薬部外品", "薬用", "日焼け止め", "サンスクリーン",
    "シャンプー", "コンディショナー", "トリートメント", "ヘアカラー", "白髪染め",
    "美白", "育毛", "養毛", "香水", "オーデコロン", "フレグランス",
]

# draft #5: 並行輸入品・海外ブランド品
PARALLEL_IMPORT_KEYWORDS = ["並行輸入", "並行品", "海外正規", "逆輸入", "USA直輸入", "海外版"]

# draft #7: 互換品・「〜対応」「〜風」「ジェネリック」
COMPATIBLE_KEYWORDS = [
    "互換", "互換品", "ジェネリック", "generic", "Generic", "汎用品",
    "対応", "適合", "用交換", "交換用", "リサイクルトナー", "詰め替え用インク",
    "風デザイン", "同型", "タイプ品", "ノックオフ",
]

# draft #8: 食品・飲料
FOOD_KEYWORDS = [
    "食品", "食料", "飲料", "ドリンク", "お菓子", "菓子", "チョコ", "クッキー", "せんべい",
    "米", "麺", "パスタ", "スープ", "調味料", "醤油", "味噌", "砂糖", "塩", "油",
    "コーヒー", "紅茶", "緑茶", "ジュース", "水", "ミネラルウォーター", "サプリ",
    "健康食品", "栄養", "プロテイン", "レトルト", "缶詰", "冷凍食品", "ふりかけ",
    "賞味期限", "消費期限", "食べ", "飲む",
]

# draft #9: 書籍・CD・DVD等メディア系
MEDIA_KEYWORDS = ["書籍", "コミック", "DVD", "Blu-ray", "ブルーレイ", "CD-ROM", "写真集", "楽譜"]

# draft #12: 割れ物（ガラス・陶器）
# 2026-09-06 追記: 初回の出力に「ウォールミラー 鏡」が残っていた（鏡＝ガラス）。
FRAGILE_KEYWORDS = ["ガラス", "陶器", "磁器", "陶磁器", "セラミック製", "クリスタル", "瀬戸物",
                    "土鍋", "鏡", "ミラー", "花瓶", "急須", "湯呑"]

# draft #13: 医療機器・コンタクト・サプリ
MEDICAL_KEYWORDS = [
    "医療機器", "管理医療機器", "コンタクトレンズ", "カラコン", "体温計", "血圧計",
    "補聴器", "マスク 医療", "医薬品", "第1類", "第2類", "第3類", "指定第2類",
]

# draft #14: 酒類・金券・武器・化学物質など制限品
RESTRICTED_KEYWORDS = [
    "酒", "ワイン", "ビール", "焼酎", "日本酒", "ウイスキー", "リキュール", "梅酒",
    "たばこ", "タバコ", "加熱式", "電子たばこ", "VAPE",
    "商品券", "ギフト券", "金券", "切手", "収入印紙",
    "モデルガン", "エアガン", "ナイフ", "刀", "銃",
    "スプレー", "エアゾール", "殺虫剤", "消火", "花火", "ライター", "ガスボンベ",
    "アルコール除菌", "接着剤", "シンナー", "塗料",
]

# draft #6: 中国輸入ノーブランド品。**仕入れ先ごと外す**という原典の判断に合わせる
CHINA_IMPORT_SUPPLIER_KEYWORDS = ["グッズステーション", "上海", "義烏", "イーウー", "深圳", "深セン"]

# draft #2 Tier A: 機械除外する著名ブランド／大手メーカー。
# ここは「有名だから」ではなく「ゲート・真贋クレームの実例が draft に挙がっている系統」を入れる。
# 誤爆は許容する（初回に選ぶ理由がないため）。
MAJOR_BRAND_KEYWORDS = [
    "Apple", "アップル", "Nike", "NIKE", "ナイキ", "adidas", "アディダス", "PUMA",
    "Sony", "ソニー", "Panasonic", "パナソニック", "SHARP", "シャープ", "TOSHIBA", "東芝",
    "HITACHI", "日立", "Canon", "キヤノン", "Nikon", "ニコン", "EPSON", "エプソン",
    "Brother", "ブラザー", "NEC", "富士通", "FUJITSU", "富士フイルム", "FUJIFILM",
    "Samsung", "サムスン", "LG", "Xiaomi", "シャオミ", "Anker", "アンカー",
    "Dyson", "ダイソン", "Philips", "フィリップス", "Braun", "ブラウン",
    "Gillette", "ジレット", "P&G", "花王", "KAO", "資生堂", "SHISEIDO", "KOSE", "コーセー",
    "Unilever", "ユニリーバ", "ライオン", "LION", "小林製薬", "大塚製薬",
    "味の素", "Ajinomoto", "アサヒ", "ASAHI", "キリン", "KIRIN", "サントリー", "SUNTORY",
    "日清", "明治", "森永", "コカ・コーラ", "Coca", "ネスレ", "Nestle",
    "LEGO", "レゴ", "BANDAI", "バンダイ", "TAKARA", "タカラトミー", "任天堂", "Nintendo",
    "COACH", "コーチ", "GUCCI", "PRADA", "LOUIS", "CHANEL", "HERMES", "Levi",
    "3M", "スリーエム", "コクヨ", "KOKUYO", "ゼブラ", "ZEBRA", "パイロット", "PILOT",
    "三菱鉛筆", "トンボ鉛筆", "Tombow", "サクラクレパス", "PLUS", "マキタ", "makita",
]

# draft 2-B: 初回に向く4群。Keepa のルートカテゴリで当てる。
# ⚠️ 「カテゴリが安全でも個別ASINが制限されている可能性は消えない」（draft 2-B 末尾）。
#     これは絞り込みにしか使えず、最終判定はセラーセントラルの実機。
FIT_GROUPS = {
    "①文房具・オフィス用品": ["文房具・オフィス用品"],
    "②ホーム＆キッチン(非電気)": ["ホーム＆キッチン", "ホーム&キッチン"],
    "③DIY・工具(非電動)": ["DIY・工具・ガーデン"],
    "④季節雑貨(電池なし)": ["ホビー", "産業・研究開発用品"],
}
# draft 2-C で明示的に保留／除外されたルートカテゴリ
BLOCKED_ROOT_CATEGORIES = {
    "ドラッグストア": "draft #3/#13（化粧品・医薬部外品・サプリの主戦場）",
    "ビューティー": "draft #3（化粧品・コスメ）",
    "食品・飲料・お酒": "draft #8/#14（食品・飲料は裁定で除外、酒類は制限品）",
    "家電＆カメラ": "draft #1（電気用品・PSE）",
    "パソコン・周辺機器": "draft #1（電気用品・PSE）",
    "大型家電": "draft #1/#11（電気用品・大型）",
    "Amazonデバイス・アクセサリ": "draft #1/#2（電気用品・ブランド）",
    "楽器・音響機器": "draft #1（電気機器を含む）",
    "本": "draft #9（メディア系・裁定で除外）",
    "DVD": "draft #9（メディア系・裁定で除外）",
    "ミュージック": "draft #9（メディア系・裁定で除外）",
    "ゲーム": "draft #9/#2（メディア系・ブランド）",
    "ファッション": "draft #2（ブランド比率が高い）",
    "スポーツ＆アウトドア": "draft 2-C（ブランド品比率が高く絞り込みコストが見合わない）",
    "おもちゃ": "draft 2-C（キャラクター物＝知財／電池内蔵＝危険物）",
    "ベビー＆マタニティ": "draft 2-C（ソースが矛盾。矛盾を解かずに初回に入れない）",
    "ペット用品": "draft 2-C 相当（4群に含まれない）",
    "車＆バイク": "draft #7（互換品・適合品が主）",
}

# draft #11: 大型・重量物
MAX_LONGEST_SUM_MM = 1700   # 3辺合計 170cm
MAX_WEIGHT_G = 30_000       # 30kg


# =============================================================================
# 判定
# =============================================================================

@dataclass
class Verdict:
    """1SKU ぶんの判定結果。**落とす理由は必ず1つ以上入る**。"""

    blocked: bool = False
    rule_id: str = ""                       # 最初に触れた draft の項番（例: "#4 中古"）
    reasons: list = field(default_factory=list)   # 触れた全ルール（人が読む用）
    used_hit: str = ""                      # 中古系の一致語。空文字＝一致なし
    used_status: str = ""                   # 「該当なし」「該当(<語>)」「要目視」
    brand_tier: str = ""                    # "A(著名)" / "B(要実機確認)" / "不明"
    fit_group: str = ""                     # 4群のどれか。空＝どれにも当たらない
    notes: list = field(default_factory=list)

    @property
    def risk_label(self) -> str:
        """CSV の「★リスク判定」列に入れる1文。触れていないなら、そう書く。"""
        if self.reasons:
            return " / ".join(self.reasons)
        return "買ってはいけないリストのどの項目にも触れない（ただしゲートは実機確認が必要）"


def _norm(text) -> str:
    """全角/半角・大文字小文字のゆれを吸収する。キーワード照合の前処理。"""
    if not text:
        return ""
    return unicodedata.normalize("NFKC", str(text))


def _hit(text: str, keywords) -> str:
    """最初に一致したキーワードを返す。無ければ空文字。"""
    for kw in keywords:
        if _norm(kw) and _norm(kw) in text:
            return kw
    return ""


def check_used(*texts, description_available: bool = True) -> tuple:
    """中古系表記の有無。**「たぶん新品」で通さない**（社長の明示指示）。

    戻り値 (status, hit):
        ("該当", 語)   … 中古系の語が見つかった → 必ず除外
        ("該当なし", "") … 判定に足るテキストがあり、語が無かった
        ("要目視", "")  … 商品説明が取得できておらず、機械判定では新品と言い切れない

    NETSEA は卸サイトだが、そこで売られている個々の商品が新品である保証はない
    （draft #4 反転条件③・2026-08-31 実測212件）。
    """
    joined = _norm(" ".join(str(t or "") for t in texts))
    hit = _hit(joined, USED_KEYWORDS)
    if hit:
        return "該当", hit
    if not description_available:
        return "要目視", ""
    return "該当なし", ""


def judge(
    *,
    netsea_name: str = "",
    amazon_title: str = "",
    brand: str = "",
    category_names=None,
    description: str = "",
    supplier_name: str = "",
    description_available: bool = True,
    package_mm=None,
    package_g=None,
    seller_count=None,
) -> Verdict:
    """1SKU を「買ってはいけないリスト」に当てる。

    引数はすべてキーワード専用にしてあります（順番の取り違えで誤判定させないため）。
    """
    v = Verdict()
    cats = list(category_names or [])
    root = cats[0] if cats else ""
    text = _norm(" ".join([netsea_name or "", amazon_title or "", " ".join(cats)]))
    text_with_desc = _norm(" ".join([text, description or ""]))

    def block(rule_id: str, why: str):
        v.blocked = True
        if not v.rule_id:
            v.rule_id = rule_id
        v.reasons.append(f"{rule_id}: {why}")

    # ── #4 中古（最優先。古物商許可がない前提が崩れると無許可営業になる）──────────
    status, hit = check_used(netsea_name, amazon_title, description,
                             description_available=description_available)
    v.used_status = f"該当({hit})" if status == "該当" else status
    v.used_hit = hit
    if status == "該当":
        block("#4 中古", f"中古系表記「{hit}」を検出。古物商許可がないため扱えない")
    elif status == "要目視":
        v.notes.append("NETSEA の商品説明が空欄で、中古かどうかを機械判定できない → 発注前に商品ページを目視")

    # ── #1 電気用品（PSE）─────────────────────────────────────────────
    if not _hit(text, ELECTRIC_SAFE_OVERRIDES):
        hit = _hit(text, ELECTRIC_KEYWORDS)
        if hit:
            block("#1 電気用品", f"「{hit}」を検出。PSE表示なしの販売は電安法27条違反")

    # ── #2 ブランド（Tier A のみ機械除外。Tier B は残して実機確認へ）──────────────
    brand_text = _norm(f"{brand} {amazon_title}")
    major = _hit(brand_text, MAJOR_BRAND_KEYWORDS)
    if major:
        v.brand_tier = f"A(著名: {major})"
        block("#2 ブランド", f"著名ブランド「{major}」。ゲート要件を満たしても却下される実例あり")
    elif (brand or "").strip():
        v.brand_tier = "B(要実機確認)"
        v.notes.append(f"ブランド「{brand}」が Amazon に登録済み。セラーセントラルでゲート確認が必須")
    else:
        v.brand_tier = "不明"
        v.notes.append("Keepa に brand が無い。ゲート確認は実機で行う")

    # ── #3 化粧品・医薬部外品 ────────────────────────────────────────
    hit = _hit(text, COSMETIC_KEYWORDS)
    if hit:
        block("#3 化粧品", f"「{hit}」を検出。ゲート厳格＋真贋クレームの主戦場")

    # ── #5 並行輸入 ───────────────────────────────────────────────
    hit = _hit(text_with_desc, PARALLEL_IMPORT_KEYWORDS)
    if hit:
        block("#5 並行輸入", f"「{hit}」を検出")

    # ── #6 中国輸入ノーブランド（仕入れ先ごと外す）────────────────────────────
    hit = _hit(_norm(supplier_name), CHINA_IMPORT_SUPPLIER_KEYWORDS)
    if hit:
        block("#6 中国輸入", f"仕入れ先名に「{hit}」。PSE/技適の最終責任と知財地雷を初回で負わない")

    # ── #7 互換品・「〜対応」表記 ──────────────────────────────────────
    hit = _hit(text, COMPATIBLE_KEYWORDS)
    if hit:
        block("#7 互換品", f"「{hit}」を検出。権利者からの偽造品通報が定型的に発生")

    # ── #8 食品・飲料 ────────────────────────────────────────────
    hit = _hit(text, FOOD_KEYWORDS)
    if hit:
        block("#8 食品", f"「{hit}」を検出。難易度評価が矛盾したまま解けていない（裁定で除外）")

    # ── #9 メディア系 ────────────────────────────────────────────
    hit = _hit(text, MEDIA_KEYWORDS)
    if hit:
        block("#9 メディア", f"「{hit}」を検出。小口はカートが取れず1周が完走しない")

    # ── #12 割れ物 ──────────────────────────────────────────────
    hit = _hit(text, FRAGILE_KEYWORDS)
    if hit:
        block("#12 割れ物", f"「{hit}」を検出。破損クレーム・返品")

    # ── #13 医療機器・サプリ ──────────────────────────────────────
    hit = _hit(text, MEDICAL_KEYWORDS)
    if hit:
        block("#13 医療機器", f"「{hit}」を検出。許認可・ラボ要件")

    # ── #14 酒類・金券・武器・化学物質 ─────────────────────────────────
    hit = _hit(text, RESTRICTED_KEYWORDS)
    if hit:
        block("#14 制限品", f"「{hit}」を検出")

    # ── #11 大型・重量物（寸法が取れているときだけ判定する。不明を駄目にしない）──────
    if package_mm and len(package_mm) == 3 and all(package_mm):
        if sum(package_mm) > MAX_LONGEST_SUM_MM:
            block("#11 大型", f"3辺合計 {sum(package_mm)}mm > {MAX_LONGEST_SUM_MM}mm")
    if package_g and package_g > MAX_WEIGHT_G:
        block("#11 重量物", f"{package_g}g > {MAX_WEIGHT_G}g")

    # ── カテゴリごと除外（draft 2-C の保留・裁定済み）────────────────────────
    if root in BLOCKED_ROOT_CATEGORIES:
        block("カテゴリ除外", f"「{root}」— {BLOCKED_ROOT_CATEGORIES[root]}")

    # ── 4群への適合（除外ではなく、通す側の条件）──────────────────────────
    for group, roots in FIT_GROUPS.items():
        if root in roots:
            v.fit_group = group
            break

    # ── 完走軸: 出品者100人規模の最安値合わせ市場（draft 2-A 追加軸）──────────────
    if seller_count is not None and seller_count >= 100:
        block("完走不可", f"出品者(オファー)数 {seller_count}。小口はカートを取れない")

    return v
