"""
コンプラ警告マスタ
- ブランド名で検索して、販売チャネル制限/商標権リスクが既知のものを赤フラグ
- マスタは順次拡張（社長フィードバック・サトル調査結果を反映）
"""
from typing import Optional

RESTRICTED_BRANDS: dict[str, str] = {
    "Sony": "Sony 販売チャネル制限あり（出品許可申請が必要）",
    "Panasonic": "Panasonic ブランド制限あり（一部商品で許可申請必要）",
    "Bandai": "Bandai 商標確認推奨（プレミアムバンダイ等公式チャネル制限あり）",
    "バンダイ": "Bandai 商標確認推奨",
    "Apple": "Apple ブランド制限（並行輸入品も含めて厳しい）",
    "Nike": "Nike 真贋確認必須（出品許可申請）",
    "Anker": "Anker 認定セラー以外は警告対象",
    "Dyson": "Dyson 正規販売店制限あり",
    "Shark": "Shark Ninja 認定セラー制限あり",
    "Nintendo": "任天堂 商標・販路制限あり（中古/未開封の区分注意）",
    "ニンテンドー": "任天堂 商標・販路制限あり",
}


def check_brand(title: str) -> Optional[str]:
    """商品タイトルからブランドを検出し、警告メッセージを返す。該当なしなら None"""
    title_lower = title.lower()
    for brand, msg in RESTRICTED_BRANDS.items():
        if brand.lower() in title_lower:
            return f"🚨 {msg}"
    return None
