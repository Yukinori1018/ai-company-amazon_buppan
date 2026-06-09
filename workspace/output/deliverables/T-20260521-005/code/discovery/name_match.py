"""仕入元名 × Amazon名 の「別商品の疑い」検知ガード（JAN誤登録対策）。

なぜ要るか（タカシ・honesty-first の核心 / 社長報告 2026-06-06）:
  JAN突合自体は正しい（Amazon の eanList に問い合わせJANが入っている）。だが
  Yahoo出店者が安い輸入雑貨に **誤った/使い回しのJAN** を登録しているため、同一JANが
  Amazonでは全く別商品を指すことがある。実例:
    - Yahoo「滑り台・ブランコ 大型遊具」 → Amazon「物置 屋外 大型 SOFTSEA」(同JAN)
    - Yahoo「つっぱり式ジャングルジム」 → Amazon「システムデスク OSJ」(同JAN)
  これを素通りさせると、別商品ペアが利益ランキングに載り社長が買い間違える。

このモジュールの役割:
  仕入元商品名と Amazon商品名を正規化し、意味のある共通トークン（名詞・ブランド・型番）が
  あるかを判定する。共通点が無ければ「別商品の疑い(JAN誤登録)」として呼び出し側に通知し、
  原石/利益ランキングから除外させる。

設計方針:
  - 純関数・正規表現/集合演算のみ。外部依存なし（YAGNI）。
  - 閾値は **緩め**。Amazonタイトルは冗長なので、厳しすぎると正しい組まで落とす。
    「型番一致」または「ブランド/主要名詞トークンが1つ以上共通」なら妥当とみなす。
  - 判定に使える材料が乏しい（両側とも短すぎる等）場合は **疑い扱いにしない**（誤検知抑制）。
    本ガードは「明らかにかけ離れている組」だけを落とすのが目的（見逃しより誤検知を恐れる）。
"""

import re
import unicodedata
from typing import Optional

# 商品名から落とすノイズ語（ストア名・プロモ語・送料表記・梱包語など）。
# これらは商品の同一性に寄与しないため、共通トークン判定の前に除去する。
_STOPWORDS = {
    # プロモ/販促
    "送料無料", "送料込", "送料込み", "ポイント", "ポイント消化", "セール", "sale",
    "クーポン", "限定", "数量限定", "人気", "おすすめ", "話題", "新品", "未使用",
    "正規品", "正規", "公式", "国内発送", "即日発送", "あす楽", "あすつく", "翌日配達",
    "プレゼント", "ギフト", "ラッピング", "まとめ買い", "お買い得", "格安", "激安",
    "最安", "最安値", "訳あり", "アウトレット", "在庫処分", "クリアランス",
    "新作", "新登場", "話題の", "売れ筋", "ランキング",
    # 梱包/数量の一般語（数量はquantity.pyが別途扱う。ここではトークンから外す）
    "セット", "パック", "個", "本", "枚", "袋", "箱", "入", "入り", "組",
    # 一般形容/接続
    "用", "対応", "兼用", "専用", "付き", "付", "タイプ", "サイズ", "カラー", "色",
    "and", "for", "with", "the", "of", "set", "pack", "pcs", "pc",
    # よくあるストア接尾辞
    "store", "shop", "ショップ", "ストア", "公式ストア", "本店", "楽天市場店", "yahoo店",
}

# ブランド/英字+数字の型番らしきトークン（例: B0DCZH84KW, OSJ-1200, SOFTSEA）を拾う。
_RE_MODEL = re.compile(r"[A-Za-z]{2,}[-]?\d{2,}[A-Za-z0-9-]*|[A-Za-z0-9]{2,}-[A-Za-z0-9]{2,}")

# 計量/容量の数値+単位（共通トークン判定では無視する。quantity.pyと同方針）。
_RE_MEASURE = re.compile(
    r"\d+\s*(?:ml|mL|ML|l|L|リットル|cc|g|kg|mg|cm|mm|m|inch|インチ"
    r"|mah|mAh|wh|w|v|a|hz|gb|tb|mb|度|℃|円|畳|帖)\b",
    re.IGNORECASE,
)

# トークン分割: 記号・空白・全角/半角の区切りで割る。
_RE_SPLIT = re.compile(r"[\s　、,，。.・/／\\|｜:：;；()（）\[\]【】「」『』\"'<>＜＞#＃*＊+＋~〜ー!！?？=＝×x✕]+")

# 短すぎて意味の薄い1〜2文字の英字/かなトークンは捨てる（誤マッチ抑制）。
_MIN_JA_TOKEN_LEN = 2   # 日本語（漢字/カナ）は2文字以上を意味トークンとして扱う
_MIN_EN_TOKEN_LEN = 3   # 英字は3文字以上


def normalize(name: Optional[str]) -> str:
    """商品名を正規化（NFKC・小文字化・計量単位の除去）。"""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", str(name)).lower()
    text = _RE_MEASURE.sub(" ", text)
    return text


def _is_meaningful(tok: str) -> bool:
    if not tok or tok in _STOPWORDS:
        return False
    if tok.isdigit():
        return False  # 裸の数字は同一性の根拠にしない（数量はquantity側で扱う）
    # 英字のみのトークンは長さ要件を課す
    if re.fullmatch(r"[a-z]+", tok):
        return len(tok) >= _MIN_EN_TOKEN_LEN
    # 1文字の漢字/カナは弱いので捨てる
    if len(tok) < _MIN_JA_TOKEN_LEN and not re.search(r"\d", tok):
        return False
    return True


def tokenize(name: Optional[str]) -> set:
    """正規化した商品名から、同一性判定に使う意味トークン集合を作る。"""
    norm = normalize(name)
    raw = [t for t in _RE_SPLIT.split(norm) if t]
    return {t for t in raw if _is_meaningful(t)}


def extract_models(name: Optional[str]) -> set:
    """型番らしき英数字トークン（ブランド型番）を抽出する。"""
    norm = normalize(name)
    return {m.group(0) for m in _RE_MODEL.finditer(norm)}


def _ngram_overlap(a: str, b: str, n: int = 3) -> bool:
    """日本語の連結名詞対策: 文字 n-gram の共有が十分あれば「関連あり」とみなす（補助シグナル）。

    日本語商品名は空白で区切られず1語に連なることが多く、トークン分割だけだと共通語を
    取りこぼす。その救済。ただし誤検知（偶然のかな2文字一致＝「ブラック」と「ブランコ」の
    『ブラ』、サイズ語『大型』等）を防ぐため、**3-gram**＋**被覆率**＋**最低絶対数**の
    3条件を課す（社長報告の 遊具⇔物置 が 2-gram『ブラ/大型』で誤OKになった対策 2026-06-06）。
    """
    sa = {a[i:i + n] for i in range(len(a) - n + 1)}
    sb = {b[i:i + n] for i in range(len(b) - n + 1)}
    if not sa or not sb:
        return False
    inter = sa & sb
    denom = min(len(sa), len(sb))
    # 3-gram が2個以上共有 かつ 小さい方の30%以上を被覆する場合のみ「関連あり」。
    return len(inter) >= 2 and denom > 0 and (len(inter) / denom) >= 0.30


def assess(supplier_name: Optional[str], amazon_name: Optional[str]) -> dict:
    """仕入元名とAmazon名が「同一商品として妥当か」を判定する。

    返り値 dict:
      ok      : bool  妥当（同一商品とみなしてよい）なら True
      reason  : str   判定根拠（ログ/監査用）
      shared  : list  共有した意味トークン/型番（説明用）

    判定（緩め＝誤検知を抑える）:
      1) 型番が1つ以上共有 → 妥当（最強シグナル）。
      2) 意味トークンが1つ以上共有 → 妥当。
      3) 文字bi-gram被覆が閾値以上 → 妥当（日本語連結名詞の救済）。
      4) いずれの材料も判定に足りない（両側トークンが乏しい）→ 妥当扱い（疑いにしない）。
      5) 上のどれにも当たらない（両側に十分な情報があるのに共通点ゼロ）→ 別商品の疑い。
    """
    s_tokens = tokenize(supplier_name)
    a_tokens = tokenize(amazon_name)
    s_models = extract_models(supplier_name)
    a_models = extract_models(amazon_name)

    shared_models = sorted(s_models & a_models)
    if shared_models:
        return {"ok": True, "reason": f"型番一致:{shared_models}", "shared": shared_models}

    shared_tokens = sorted(s_tokens & a_tokens)
    if shared_tokens:
        return {"ok": True, "reason": f"共通語:{shared_tokens}", "shared": shared_tokens}

    # 判定材料が乏しい場合は疑い扱いにしない（誤検知抑制。honesty-first）。
    # どちらかが意味トークン0なら、共通点ゼロを「別商品」と断じる根拠が弱い。
    if not s_tokens or not a_tokens:
        return {"ok": True, "reason": "判定材料不足(トークン乏しい)→疑い対象外", "shared": []}

    # 日本語連結名詞の救済: 意味トークンを連結した文字列同士の bi-gram 被覆で関連を見る。
    # ※ 生の正規化文字列だとストア名/プロモ語（送料無料 等）の共通プレフィクスで
    #   誤って「関連あり」になるため、ストップワード除去後のトークンだけで判定する。
    if _ngram_overlap("".join(sorted(s_tokens)), "".join(sorted(a_tokens))):
        return {"ok": True, "reason": "文字bi-gram被覆あり", "shared": []}

    # 両側に十分な情報があるのに共通点ゼロ → 別商品の疑い（JAN誤登録）。
    return {
        "ok": False,
        "reason": "共通トークン・型番・bi-gram被覆すべて無し（別商品の疑い）",
        "shared": [],
    }


def is_suspect(supplier_name: Optional[str], amazon_name: Optional[str]) -> bool:
    """別商品の疑い（JAN誤登録）なら True。"""
    return not assess(supplier_name, amazon_name)["ok"]


# =============================================================================
# 数値属性（容量・サイズ）の抽出と矛盾チェック  ＋  突合信頼度スコア
# =============================================================================
# 社長フィードバック(2026-06-07):「突合がまだ間違っているものが多い。正確性をぐんと上げて」。
# JAN一致を鵜呑みにせず、容量(ml/L/g/kg)・サイズ(cm/インチ)・型番・ブランド語の
# 多シグナルで「本当に同一商品か」を検証し、迷ったら厳しめ（原石を減らしてでも誤突合を出さない）。
#
# 設計:
#   - 容量/サイズは「数値 × 基準単位」に正規化して集合で持つ（例 500ml→500.0ml, 1L→1000.0ml）。
#   - 両側に同種の属性があり、共通値が1つも無ければ「矛盾」とみなす（例 500ml vs 1000ml）。
#   - 個数（入数）は quantity.py / pipeline 側で別途厳密に扱うため、ここでは容量・サイズに限定。

# 容量・重量・長さの単位を共通の基準単位へ換算する係数。
# 体積→ml基準、重量→g基準、長さ→mm基準 にそろえる。
_VOLUME_TO_ML = {
    "ml": 1.0, "cc": 1.0, "l": 1000.0, "リットル": 1000.0,
}
_WEIGHT_TO_G = {
    "mg": 0.001, "g": 1.0, "kg": 1000.0,
}
_LENGTH_TO_MM = {
    "mm": 1.0, "cm": 10.0, "m": 1000.0, "inch": 25.4, "インチ": 25.4,
}

# 「数値（小数可）＋単位」を1トークンで拾う正規表現（容量/重量/長さ）。
_RE_VOLUME = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|cc|l|リットル)\b", re.IGNORECASE)
_RE_WEIGHT = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|kg|g)\b", re.IGNORECASE)
_RE_LENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm|inch|インチ|m)\b", re.IGNORECASE)


def _norm_unit_text(name: Optional[str]) -> str:
    """単位抽出用の軽い正規化（NFKC・小文字化）。計量を消さない点が normalize と違う。"""
    if not name:
        return ""
    return unicodedata.normalize("NFKC", str(name)).lower()


def _extract_scaled(text: str, regex, table: dict) -> set:
    """正規表現＋換算表で「基準単位での数値集合」を作る。"""
    out = set()
    for m in regex.finditer(text):
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        unit = m.group(2).lower()
        factor = table.get(unit)
        if factor is None:
            continue
        scaled = round(val * factor, 3)
        if scaled > 0:
            out.add(scaled)
    return out


def extract_attributes(name: Optional[str]) -> dict:
    """商品名から数値属性（容量[ml]・重量[g]・長さ[mm]）を基準単位の集合で抽出する。"""
    text = _norm_unit_text(name)
    return {
        "volume_ml": _extract_scaled(text, _RE_VOLUME, _VOLUME_TO_ML),
        "weight_g": _extract_scaled(text, _RE_WEIGHT, _WEIGHT_TO_G),
        "length_mm": _extract_scaled(text, _RE_LENGTH, _LENGTH_TO_MM),
    }


def numeric_conflict(supplier_name: Optional[str], amazon_name: Optional[str]) -> Optional[str]:
    """容量・重量・長さの数値属性が「明確に矛盾」していれば矛盾の説明文を返す。

    両側に同種の属性があり、共通する値が1つも無いときだけ矛盾とみなす
    （例: 500ml vs 1000ml）。片側にしか属性が無い／同種が無い場合は矛盾なし（None）。
    誤検知を抑えるため「両側に在り、かつ重なりゼロ」という厳しい条件に限定する。
    """
    sa = extract_attributes(supplier_name)
    aa = extract_attributes(amazon_name)
    labels = {"volume_ml": "容量", "weight_g": "重量", "length_mm": "サイズ"}
    units = {"volume_ml": "ml", "weight_g": "g", "length_mm": "mm"}
    for key, label in labels.items():
        s = sa[key]
        a = aa[key]
        if s and a and not (s & a):
            sv = "/".join(f"{v:g}{units[key]}" for v in sorted(s))
            av = "/".join(f"{v:g}{units[key]}" for v in sorted(a))
            return f"{label}が不一致（仕入元 {sv} ⇔ Amazon {av}）"
    return None


# 突合信頼度ラベル（UI 表示と原石昇格ゲートで共有）。
CONFIDENCE_HIGH = "高"
CONFIDENCE_MID = "中"
CONFIDENCE_LOW = "低"


def match_confidence(supplier_name: Optional[str], amazon_name: Optional[str]) -> dict:
    """仕入元名 × Amazon名 の「同一商品らしさ」を多シグナルで採点する。

    返り値 dict:
      level   : "高" / "中" / "低"
      reason  : 判定根拠（監査/ログ用）
      conflict: 数値属性の矛盾説明（あれば。無ければ ""）
      shared  : 共有した型番/トークン

    採点（社長＝正確性最優先 → 迷ったら厳しめ。ただし正当な単一キーワード品は落とさない）:
      - 数値属性（容量/重量/サイズ）が明確に矛盾 → 即「低」（原石にしない）。
      - 共通点が乏しい（assess が別商品の疑い）→ 「低」。
      - 型番一致 → 「高」（最強シグナル）。
      - 主要名詞が1語以上重複（数値矛盾なし）→ 「高」。
        ※ 共通名詞が1語でも、別商品なら assess が先に「低」で弾く。残った行は
          実体のある共通名詞を持つため「高」とみなす。
      - 共有名詞ゼロだが n-gram 被覆 or 判定材料不足で assess 妥当 → 「中」（確証が弱い）。
    """
    conflict = numeric_conflict(supplier_name, amazon_name)
    if conflict:
        return {"level": CONFIDENCE_LOW, "reason": f"数値属性が矛盾: {conflict}",
                "conflict": conflict, "shared": []}

    a = assess(supplier_name, amazon_name)
    if not a["ok"]:
        return {"level": CONFIDENCE_LOW, "reason": a["reason"],
                "conflict": "", "shared": []}

    s_models = extract_models(supplier_name)
    a_models = extract_models(amazon_name)
    shared_models = sorted(s_models & a_models)
    if shared_models:
        return {"level": CONFIDENCE_HIGH, "reason": f"型番一致:{shared_models}",
                "conflict": "", "shared": shared_models}

    shared_tokens = sorted(tokenize(supplier_name) & tokenize(amazon_name))
    if shared_tokens:
        return {"level": CONFIDENCE_HIGH,
                "reason": f"主要名詞一致:{shared_tokens}（数値属性に矛盾なし）",
                "conflict": "", "shared": shared_tokens}

    # 共有名詞ゼロだが assess は妥当（n-gram 被覆 or 判定材料不足）→ 確証が弱い → 中。
    return {"level": CONFIDENCE_MID, "reason": f"確証が弱い（{a['reason']}）",
            "conflict": "", "shared": []}
