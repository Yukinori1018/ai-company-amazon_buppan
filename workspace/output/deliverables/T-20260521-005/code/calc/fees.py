"""Amazon.co.jp 料率・FBA手数料の定数表（2026年時点の公開料率の代表値）。

⚠️ 重要 —— このファイルの数値は「要・経理ハジメ検証」です。
   Amazon の料率・FBA手数料は予告なく改定されます。ここに置いた値は
   2026年時点の Amazon.co.jp 公開情報の「代表値」であり、最新性は保証しません。
   実運用前に必ず Amazon Seller Central の最新ページと突き合わせてください。

設計方針（タカシ）:
- 計算ロジック（profit.py）から「数値」を完全に切り離す。
- 数値の出典・前提・検証要否をこの1ファイルに集約し、改定時はここだけ直す。
- 1円もごまかさないため、料率は概算丸めをせず公開値をそのまま置く。

出典（2026年時点で確認した代表値ベース。要再確認）:
- Amazon 販売手数料: Seller Central「Amazon出品サービスの手数料」カテゴリ別料率表
- FBA配送代行手数料: Seller Central「FBA料金」標準サイズ/大型サイズ区分別
"""

# =============================================================================
# Amazon 販売手数料（カテゴリ別料率）
# =============================================================================
# - 料率は「税込売値」に対して掛ける（Amazon は税込価格基準で手数料を算定）。
# - min_fee_yen: カテゴリによっては最低手数料が設定される（例: 一部30円）。
#   不明・未設定のカテゴリは 0 とし、料率のみで算定する。
#
# ⚠️ 経理ハジメ検証ポイント:
#   - 各カテゴリの料率（特に「ホーム&キッチン」「ドラッグストア」等は
#     価格帯で段階料率になる場合がある。ここでは単一料率の代表値を採用）。
#   - 最低手数料の有無・金額。
#
# 形式: category_key -> {"label": 表示名, "rate": 料率(小数), "min_fee_yen": 最低手数料}

REFERRAL_FEE_TABLE = {
    "default": {"label": "その他（デフォルト）", "rate": 0.15, "min_fee_yen": 0},
    "books": {"label": "本", "rate": 0.15, "min_fee_yen": 0},
    "home_kitchen": {"label": "ホーム（家庭用品）&キッチン", "rate": 0.15, "min_fee_yen": 0},
    "beauty": {"label": "ビューティー", "rate": 0.10, "min_fee_yen": 30},
    "drugstore": {"label": "ドラッグストア", "rate": 0.10, "min_fee_yen": 30},
    "health": {"label": "ヘルス&パーソナルケア", "rate": 0.10, "min_fee_yen": 30},
    "toys": {"label": "おもちゃ&ホビー", "rate": 0.15, "min_fee_yen": 0},
    "electronics": {"label": "家電&カメラ", "rate": 0.08, "min_fee_yen": 30},
    "pc": {"label": "パソコン・周辺機器", "rate": 0.08, "min_fee_yen": 30},
    "sports": {"label": "スポーツ&アウトドア", "rate": 0.15, "min_fee_yen": 0},
    "diy": {"label": "DIY・工具", "rate": 0.15, "min_fee_yen": 0},
    "apparel": {"label": "服&ファッション小物", "rate": 0.15, "min_fee_yen": 30},
    "food": {"label": "食品&飲料", "rate": 0.10, "min_fee_yen": 0},
    "pet": {"label": "ペット用品", "rate": 0.15, "min_fee_yen": 0},
    "office": {"label": "文房具・オフィス用品", "rate": 0.15, "min_fee_yen": 0},
}


# =============================================================================
# FBA 配送代行手数料（サイズ区分別・固定額）
# =============================================================================
# - 1点あたりの「出荷作業手数料＋配送代行手数料」の合算代表値（円・税込相当）。
# - 実際の FBA 料金は「寸法 × 重量」で細かい区分に分かれるが、MVP では
#   社長が選びやすい代表的な区分に丸めた固定額を持つ（YAGNI）。
# - 在庫保管手数料・長期保管手数料・返品処理手数料はここには含めない
#   （その他経費フィールドで個別計上する想定）。
#
# ⚠️ 経理ハジメ検証ポイント:
#   - 各サイズ区分の金額。FBA 料金改定の影響を最も受けやすい部分。
#   - 「小型・標準」のさらに細かい重量区分を作るべきか（今は代表値で丸めている）。
#
# 形式: size_key -> {"label": 表示名, "fba_fee_yen": FBA手数料(円), "note": 寸法/重量の目安}

FBA_FEE_TABLE = {
    "small": {
        "label": "小型サイズ",
        "fba_fee_yen": 290,
        "note": "25×18×2.0cm以内・250g以内が目安",
    },
    "standard_1": {
        "label": "標準サイズ1（〜1kg）",
        "fba_fee_yen": 434,
        "note": "45×35×20cm以内・1kg以内が目安",
    },
    "standard_2": {
        "label": "標準サイズ2（〜2kg）",
        "fba_fee_yen": 514,
        "note": "標準寸法内・2kg以内が目安",
    },
    "large_1": {
        "label": "大型サイズ1（〜5kg）",
        "fba_fee_yen": 603,
        "note": "60サイズ前後・5kg以内が目安",
    },
    "large_2": {
        "label": "大型サイズ2（〜10kg）",
        "fba_fee_yen": 707,
        "note": "80〜100サイズ・10kg以内が目安",
    },
    "self_ship": {
        "label": "自己発送（FBA不使用）",
        "fba_fee_yen": 0,
        "note": "FBA手数料は0。配送料は『その他経費』で別途計上",
    },
}


# =============================================================================
# 消費税率（税抜⇄税込変換に使用）
# =============================================================================
# ⚠️ 経理ハジメ検証ポイント:
#   - 標準税率10%を採用。食品など軽減税率8%対象は profit.py 呼び出し側で
#     tax_rate を上書きする想定（今はデフォルト10%）。
CONSUMPTION_TAX_RATE = 0.10


def get_referral_rate(category_key: str) -> dict:
    """カテゴリキーから販売手数料設定を返す。未知のキーは default にフォールバック。"""
    return REFERRAL_FEE_TABLE.get(category_key, REFERRAL_FEE_TABLE["default"])


def get_fba_fee(size_key: str) -> dict:
    """サイズキーから FBA 手数料設定を返す。未知のキーは standard_1 にフォールバック。"""
    return FBA_FEE_TABLE.get(size_key, FBA_FEE_TABLE["standard_1"])


def category_choices() -> list:
    """UI のセレクトボックス用（key, label）リスト。"""
    return [(k, v["label"]) for k, v in REFERRAL_FEE_TABLE.items()]


def size_choices() -> list:
    """UI のセレクトボックス用（key, label）リスト。"""
    return [(k, v["label"]) for k, v in FBA_FEE_TABLE.items()]
