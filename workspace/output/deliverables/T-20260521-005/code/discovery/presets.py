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

from dataclasses import dataclass, field


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


# =============================================================================
# (あ) Amazon起点：Keepa Best Sellers で売れ筋を引くカテゴリ（co.jp ルートカテゴリID）
# =============================================================================
# Keepa の co.jp ルートカテゴリID（domain=5）。bestsellers の category 引数に渡す。
# ※ これらは Amazon公開ブラウズノードではなく **Keepa /category で実取得した有効ID**
#    （2026-06-05 タカシが実 API で検証。Amazonブラウズノードとは一致しない値がある）。
# 初心者が扱いやすい安全カテゴリ（無在庫/FBA向き・規制が比較的緩い）を厳選。
@dataclass
class AmazonCategory:
    """Amazon起点探索の対象カテゴリ1件。"""

    key: str
    label: str
    category_id: int


AMAZON_CATEGORIES: dict[str, AmazonCategory] = {
    "home_kitchen": AmazonCategory("home_kitchen", "ホーム＆キッチン", 3828871),
    "office": AmazonCategory("office", "文房具・オフィス用品", 86731051),
    "pet": AmazonCategory("pet", "ペット用品", 2127212051),
    "toys": AmazonCategory("toys", "おもちゃ", 13299531),
    "sports": AmazonCategory("sports", "スポーツ＆アウトドア", 14304371),
}

# (あ) 既定カテゴリ（初心者向けに最も無難なホーム＆キッチン）。
DEFAULT_AMAZON_CATEGORY_KEY = "home_kitchen"


def amazon_category_choices() -> list[tuple[str, str]]:
    """UI のカテゴリ選択用 (key, label) リスト。"""
    return [(c.key, c.label) for c in AMAZON_CATEGORIES.values()]


def get_amazon_category(key: str) -> AmazonCategory:
    """キーから Amazon カテゴリを返す。未知なら既定（ホーム＆キッチン）。"""
    return AMAZON_CATEGORIES.get(key, AMAZON_CATEGORIES[DEFAULT_AMAZON_CATEGORY_KEY])


# =============================================================================
# (あ) 原石オートサーチ：Keepa Product Finder 用 selection（条件抽出）
# =============================================================================
# 「そこそこ売れてる × 競合が少ない × 中位ランク」のニッチ原石を数千商品から自動抽出する。
# Best Sellers（売れ筋トップ＝競争激・赤字）とは逆向きに、中位ランク帯を狙うのが肝。
#
# Keepa Product Finder の selection フィールド（query エンドポイント仕様）:
#   current_SALES_gte / _lte      : 販売ランキングの範囲（小さい=売れる）。中位帯で挟む。
#   current_COUNT_NEW_gte / _lte  : 新品出品者数の範囲（相乗り＝競合数）。少なめに絞る。
#   current_NEW_gte / _lte        : 新品価格の範囲（円）。仕入れ可能な価格帯に限定。
#   categories_include            : 対象カテゴリ（co.jp ノードID）の配列。
#   perPage / page                : ページング。sort: [[field, "asc"|"desc"]]。
# ※ Product Finder は ASIN しか返さない（詳細は別途 product で取得＝find_products内で実施）。


@dataclass
class FinderPreset:
    """原石オートサーチ1セット。Keepa Product Finder の selection に変換できる条件。"""

    key: str
    label: str
    description: str
    sales_rank_gte: int          # ランク下限（これ以上=トップ過ぎを除外）
    sales_rank_lte: int          # ランク上限（これ以下=売れなさ過ぎを除外）
    count_new_gte: int           # 出品者数の下限（少なすぎ=真贋/知財リスクの別問題）
    count_new_lte: int           # 出品者数の上限（多すぎ=価格競争）
    price_gte: int               # 価格下限（円）
    price_lte: int               # 価格上限（円）
    per_page: int = 50           # Finder取得件数（>=50）。詳細取得は別途15件にキャップ。
    # 抽出順。実走検証(2026-06-05)で SALES asc はランク密集帯（Amazonが安い人気品）に偏り
    # 原石が出にくいと判明。COUNT_NEW asc（競合が最も薄い順）で値付けの緩い原石を上に拾う。
    sort: list = field(default_factory=lambda: [["current_COUNT_NEW", "asc"]])
    # 利益計算後に効く閾値（既存 DiscoveryPreset と同じ役割。原石判定に使う）。
    min_margin_rate: float = 0.05
    min_net_profit: float = 500

    def to_selection(self, category_ids: list[int]) -> dict:
        """Keepa Product Finder の selection(JSON) を組み立てる。"""
        return {
            "current_SALES_gte": self.sales_rank_gte,
            "current_SALES_lte": self.sales_rank_lte,
            "current_COUNT_NEW_gte": self.count_new_gte,
            "current_COUNT_NEW_lte": self.count_new_lte,
            "current_NEW_gte": self.price_gte,
            "current_NEW_lte": self.price_lte,
            "categories_include": [int(c) for c in category_ids],
            "perPage": self.per_page,
            "page": 0,
            "sort": self.sort,
        }

    def as_discovery_preset(self) -> "DiscoveryPreset":
        """利益フィルタ用に既存 DiscoveryPreset へ写像する（パイプライン互換）。

        Finder 側で既にランク/出品者数/価格を絞り込んでいるので、ここでは
        利益閾値（率/額）だけを効かせ、メタ条件は緩く（誤除外を避ける）。
        """
        return DiscoveryPreset(
            key=self.key,
            label=self.label,
            description=self.description,
            max_sales_rank=self.sales_rank_lte,
            min_monthly_sales=0,
            max_offer_count=self.count_new_lte,
            min_oos_rate_90d=0.0,
            min_margin_rate=self.min_margin_rate,
            min_net_profit=self.min_net_profit,
        )


FINDER_PRESETS: dict[str, FinderPreset] = {
    # ── 原石オートサーチ・初心者（サトル基準：中位ランク×競合薄×手頃価格）──
    "finder_genseki_beginner": FinderPreset(
        key="finder_genseki_beginner",
        label="(あ)原石オートサーチ・初心者（推奨）",
        description=(
            "キーワード不要。中位ランク（概ね1,000〜80,000位）× 出品者2〜10人 × "
            "1,000〜10,000円 の『そこそこ売れて競合が薄い』ニッチ原石を数千商品から自動抽出。"
            "Best Sellers（売れ筋トップ＝赤字）の逆を狙う。サトル基準・初心者緩和。"
        ),
        sales_rank_gte=3000,      # 〜3,000位は人気品でAmazonが安い傾向→原石薄。少し下から拾う
        sales_rank_lte=80000,     # 80,000位より下は売れ行き不安で除外
        count_new_gte=2,          # 出品1人=真贋/知財リスクの別問題なので2以上
        count_new_lte=10,         # 10人超は価格競争で利益消失
        price_gte=1000,
        price_lte=10000,
        per_page=50,
        # 初心者既定は SALES asc。実走検証(2026-06-05)で「JAN付き＝Yahooで仕入元を実際に
        # 当てられる」ブランド品が多く、利益が実数で出る（保留だらけになりにくい）ため。
        # 競合の薄いニッチ無名品狙い（=Yahoo未掲載が増える）は『標準』の COUNT_NEW asc で。
        sort=[["current_SALES", "asc"]],
        min_margin_rate=0.05,     # 初心者5%
        min_net_profit=500,       # 初心者500円
    ),
    # ── 原石オートサーチ・標準（競合さらに絞り/利益厚め）──
    "finder_genseki_standard": FinderPreset(
        key="finder_genseki_standard",
        label="(あ)原石オートサーチ・標準",
        description=(
            "中位ランク × 出品者2〜6人 × 1,500〜12,000円。競合をさらに絞り利益率15%/1,000円を要求。"
            "慣れてきたら。サトル基準・標準値。"
        ),
        sales_rank_gte=1000,
        sales_rank_lte=60000,
        count_new_gte=2,
        count_new_lte=6,
        price_gte=1500,
        price_lte=12000,
        per_page=50,
        min_margin_rate=0.15,
        min_net_profit=1000,
    ),
}

DEFAULT_FINDER_PRESET_KEY = "finder_genseki_beginner"


def get_finder_preset(key: str) -> FinderPreset:
    """キーから Finder プリセットを返す。未知なら既定（初心者）。"""
    return FINDER_PRESETS.get(key, FINDER_PRESETS[DEFAULT_FINDER_PRESET_KEY])


def finder_preset_choices() -> list[tuple[str, str]]:
    """UI のセレクト用 (key, label) リスト。"""
    return [(p.key, p.label) for p in FINDER_PRESETS.values()]


def get_preset(key: str) -> DiscoveryPreset:
    """キーからプリセットを返す。未知なら既定（堅実）にフォールバック。"""
    return PRESETS.get(key, PRESETS[DEFAULT_PRESET_KEY])


def preset_choices() -> list[tuple[str, str]]:
    """UI のセレクト用 (key, label) リスト。"""
    return [(p.key, p.label) for p in PRESETS.values()]
