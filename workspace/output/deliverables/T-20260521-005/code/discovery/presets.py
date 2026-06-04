"""ディスカバリーの「フィルタ閾値」を外出しするプリセット定義。

なぜ別ファイルか（タカシ）:
- 閾値はコードではなく「設定」。社長やサトル監修で頻繁に変わるのでコードから分離する。
- profit.py の判定閾値（利益率15%/純利益500円）とは別物。ここは「リサーチの絞り込み」条件。

⚠️ 要・サトル監修:
  下の数値は一般的な電脳せどり指南で語られる代表値（朝野拓也系ナレッジ・一般論）から
  タカシが置いた暫定値です。サトルのリサーチ結果（06_research-methods-to-encode.md）が
  出たら、その実数で上書きしてください。現時点では実データ検証されていません。

各閾値の意味:
- max_sales_rank   : このランキングより上（数値が小さい）= よく売れている、を残す
- min_monthly_sales: 推定月販がこれ以上を残す（売れない死に筋を除外）
- max_offer_count  : 出品者数がこれ以下を残す（多すぎる相乗りは価格競争で利益消失）
- min_oos_rate_90d : 在庫切れ率がこれ以上を残す（在庫切れ＝チャンス、という考え方）
                     0.0 にすると在庫切れ条件を無視する。
- min_margin_rate  : 利益率がこれ以上の結果だけ最終的に残す（profit計算後に適用）
- min_net_profit   : 純利益（円）がこれ以上の結果だけ残す
"""

from dataclasses import dataclass


@dataclass
class DiscoveryPreset:
    """ディスカバリーのフィルタ閾値1セット。"""

    key: str
    label: str
    description: str
    max_sales_rank: int = 30000
    min_monthly_sales: int = 0
    max_offer_count: int = 999
    min_oos_rate_90d: float = 0.0
    min_margin_rate: float = 0.0     # 0.0〜1.0
    min_net_profit: float = 0.0      # 円


# ⚠️ 要・サトル監修の暫定プリセット群
PRESETS: dict[str, DiscoveryPreset] = {
    "beginner_safe": DiscoveryPreset(
        key="beginner_safe",
        label="初心者・堅実（推奨）",
        description=(
            "売れていて・相乗りが少なく・利益率も確保。失敗しにくい王道設定。"
            "⚠️サトル監修前の暫定値"
        ),
        max_sales_rank=10000,
        min_monthly_sales=100,
        max_offer_count=5,
        min_oos_rate_90d=0.0,
        min_margin_rate=0.15,
        min_net_profit=500,
    ),
    "oos_chance": DiscoveryPreset(
        key="oos_chance",
        label="在庫切れ狙い（チャンス型）",
        description=(
            "在庫切れが多い=出品すれば売れやすい商品を狙う。出品者数も絞る。"
            "⚠️サトル監修前の暫定値"
        ),
        max_sales_rank=20000,
        min_monthly_sales=50,
        max_offer_count=3,
        min_oos_rate_90d=0.20,
        min_margin_rate=0.12,
        min_net_profit=400,
    ),
    "high_margin": DiscoveryPreset(
        key="high_margin",
        label="高利益率重視（少数精鋭）",
        description=(
            "回転は問わず1個あたりの利益率を最優先。単価高め商品向け。"
            "⚠️サトル監修前の暫定値"
        ),
        max_sales_rank=30000,
        min_monthly_sales=0,
        max_offer_count=8,
        min_oos_rate_90d=0.0,
        min_margin_rate=0.25,
        min_net_profit=800,
    ),
    "wide_net": DiscoveryPreset(
        key="wide_net",
        label="広く拾う（学習用・ゆるめ）",
        description=(
            "閾値をほぼ無効化し、利益が出る候補を黒字なら全部出す。relationship学習用。"
            "⚠️サトル監修前の暫定値"
        ),
        max_sales_rank=999999,
        min_monthly_sales=0,
        max_offer_count=999,
        min_oos_rate_90d=0.0,
        min_margin_rate=0.0,
        min_net_profit=1,
    ),
}

DEFAULT_PRESET_KEY = "beginner_safe"


def get_preset(key: str) -> DiscoveryPreset:
    """キーからプリセットを返す。未知なら既定（堅実）にフォールバック。"""
    return PRESETS.get(key, PRESETS[DEFAULT_PRESET_KEY])


def preset_choices() -> list[tuple[str, str]]:
    """UI のセレクト用 (key, label) リスト。"""
    return [(p.key, p.label) for p in PRESETS.values()]
