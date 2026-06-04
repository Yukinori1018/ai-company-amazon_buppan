"""ディスカバリーの「フィルタ閾値」を外出しするプリセット定義。

なぜ別ファイルか（タカシ）:
- 閾値はコードではなく「設定」。社長やサトル監修で頻繁に変わるのでコードから分離する。
- profit.py の判定閾値（利益率15%/純利益500円）とは別物。ここは「リサーチの絞り込み」条件。

閾値の出典（2026-06-04 サトル監修反映）:
  値はサトルのリサーチ成果 06_research-methods-to-encode.md に基づき、実プレイヤー基準
  （ERESA公式・ECセラーラボ・tremas-lab・社内朝野ナレッジ）で更新済み。
  サトルが「出典が割れる」と注記した値は保守的側を採り、下に before→after をコメント。

⚠️ Drop主軸への設計上の注記（サトル §A-2, §5）:
  リサーチの結論は「ランキング絶対順位より Drop30/90（販売回数の近似）で売れ行きを見る方が
  正確」。Drop は Keepa からしか取れず本プロトは Keepa 未契約のため、現状は max_sales_rank /
  min_monthly_sales を売れ行きの代理指標として残している。Keepa 契約後に Drop フィールドを
  AmazonProduct に足し、ここを drop30/drop90 主軸へ移行する（TODO・タカシ）。

各閾値の意味:
- max_sales_rank   : このランキングより上（数値が小さい）= よく売れている、を残す
                     （※サトル: 順位は補助指標。本命は Drop。Keepa後に置換予定）
- min_monthly_sales: 推定月販がこれ以上を残す（Drop30 の代理。死に筋を除外）
- max_offer_count  : 出品者数がこれ以下を残す（多すぎる相乗りは価格競争で利益消失）
                     サトル基準: 安全圏 3〜10人（少なすぎ1〜2人は真贋/知財リスクで別途警告）
- min_oos_rate_90d : 在庫切れ率がこれ以上を残す（在庫切れ＝出せば売れるチャンス）
                     サトル基準: 公式30〜40% / 社内20% で割れ → 保守的に下限20%採用。
                     0.0 にすると在庫切れ条件を無視する。
- min_margin_rate  : 利益率がこれ以上の結果だけ最終的に残す（profit計算後に適用）
                     サトル基準: 初心者5% / 標準15% / 安全圏20%
- min_net_profit   : 純利益（円）がこれ以上の結果だけ残す
                     サトル基準: 初心者500円 / 標準1,000円（朝野「利益500円まで緩めて分母拡大」）
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


# サトル基準（06_research-methods-to-encode.md §2「宝の地図」型プリセット）反映済み。
# (い)『価格差ハンティングマップ』を既定。社長は副業初心者 → 初心者緩め値を採用。
PRESETS: dict[str, DiscoveryPreset] = {
    # ── (い) 仕入れ元起点：サトル §2「価格差ハンティングマップ」初心者値 ──
    "hunting_beginner": DiscoveryPreset(
        key="hunting_beginner",
        label="(い)価格差ハンティング・初心者（推奨）",
        description=(
            "楽天/Yahoo!の実質価格とAmazon売値の差を突く電脳せどり。"
            "朝野式の初心者緩和（利益率5%/利益500円/月3個）で分母を広げる。"
            "サトル監修済（06_research §2 (い)初心者値）"
        ),
        # before(beginner_safe): rank10000/月販100/出品5/OOS0/率15%/額500
        max_sales_rank=50000,    # 順位は補助。Drop未取得のため緩め（→Keepa後Drop主軸へ）
        min_monthly_sales=3,     # サトル: 初心者は月3個(Drop30≥3)まで緩める
        max_offer_count=12,      # サトル: 初心者は出品者3〜12人
        min_oos_rate_90d=0.0,    # 在庫切れは(い)では必須条件にしない
        min_margin_rate=0.05,    # サトル: 初心者5%
        min_net_profit=500,      # サトル: 初心者500円
    ),
    # ── (い) 標準値（慣れてきたら）──
    "hunting_standard": DiscoveryPreset(
        key="hunting_standard",
        label="(い)価格差ハンティング・標準",
        description=(
            "利益率15%・利益1,000円・月販10個の標準ライン。安全圏寄り。"
            "サトル監修済（06_research §2 (い)標準値）"
        ),
        max_sales_rank=30000,
        min_monthly_sales=10,    # Drop30≥10
        max_offer_count=8,       # 標準は3〜8人
        min_oos_rate_90d=0.0,
        min_margin_rate=0.15,    # サトル: 標準15%
        min_net_profit=1000,     # サトル: 標準1,000円
    ),
    # ── (あ) Amazon起点：サトル §2「Amazon棚卸しマップ」初心者値 ──
    "stocktake_beginner": DiscoveryPreset(
        key="stocktake_beginner",
        label="(あ)Amazon棚卸し・初心者",
        description=(
            "Amazonで売れてて・競合薄くて・本体不在の棚を掘る。仕入元は後で探す。"
            "サトル監修済（06_research §2 (あ)初心者値）"
        ),
        max_sales_rank=50000,
        min_monthly_sales=3,     # Drop30≥3
        max_offer_count=12,      # サトル: 初心者3〜12人
        min_oos_rate_90d=0.0,    # 任意（不在優先）。在庫切れ妙味は oos_premium で強める
        min_margin_rate=0.05,
        min_net_profit=500,
    ),
    # ── 在庫切れ妙味（プレミア寄り）：サトル §A1 あ1/あ2/あ8 ──
    "oos_premium": DiscoveryPreset(
        key="oos_premium",
        label="(あ)在庫切れ妙味（プレミア寄り）",
        description=(
            "90日在庫切れ率が高い=出せば売れる商品を狙う。出品者も絞る。"
            "サトル監修済（公式30〜40%/社内20%が割れ→保守的に20%採用）"
        ),
        # before(oos_chance): rank20000/月販50/出品3/OOS20%/率12%/額400
        max_sales_rank=30000,
        min_monthly_sales=3,
        max_offer_count=8,       # サトル: 3〜8人
        min_oos_rate_90d=0.20,   # 公式40%/社内20%割れ → 保守的に下限20%
        min_margin_rate=0.12,
        min_net_profit=500,      # 400→500（朝野基準に統一）
    ),
    # ── 高利益率（中上級・「お宝プレミアマップ」寄り）：サトル §2(う) あ3 ──
    "high_margin": DiscoveryPreset(
        key="high_margin",
        label="高利益率重視（中上級・少数精鋭）",
        description=(
            "回転より1個あたり利益率を最優先。廃番/限定の急騰品想定（利益率30〜50%）。"
            "サトル監修済（06_research §2(う) お宝プレミアマップ）。在庫リスク高に注意。"
        ),
        max_sales_rank=30000,
        min_monthly_sales=0,
        max_offer_count=8,
        min_oos_rate_90d=0.0,
        min_margin_rate=0.30,    # 25%→30%（サトル: プレミア帯は30〜50%）
        min_net_profit=1000,     # 800→1000
    ),
    "wide_net": DiscoveryPreset(
        key="wide_net",
        label="広く拾う（学習用・ゆるめ）",
        description=(
            "閾値をほぼ無効化し、黒字なら全部出す。突合率や相場感の学習用。"
        ),
        max_sales_rank=999999,
        min_monthly_sales=0,
        max_offer_count=999,
        min_oos_rate_90d=0.0,
        min_margin_rate=0.0,
        min_net_profit=1,
    ),
}

# 既定は (い) 価格差ハンティング初心者（社長=副業初心者・電脳せどりが主軸）
DEFAULT_PRESET_KEY = "hunting_beginner"


def get_preset(key: str) -> DiscoveryPreset:
    """キーからプリセットを返す。未知なら既定（堅実）にフォールバック。"""
    return PRESETS.get(key, PRESETS[DEFAULT_PRESET_KEY])


def preset_choices() -> list[tuple[str, str]]:
    """UI のセレクト用 (key, label) リスト。"""
    return [(p.key, p.label) for p in PRESETS.values()]
