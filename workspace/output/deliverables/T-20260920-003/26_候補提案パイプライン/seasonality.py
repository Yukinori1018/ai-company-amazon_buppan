#!/usr/bin/env python3
"""季節判定 — 「死んでいる棚」と「今が季節外の棚」を区別する1枚（純関数）。

なぜ要るか（2026-10-01 カズヨが SD レーンAで実画面に当てた1件）
----------------------------------------------------------------
ナガクラ リトルガーデン・プロ ミニトマト（栽培キット）は、**価格差が実在していました** ──
卸480円（税抜・1個から買える）に対し Amazon `B001LOOR4E` が ￥2,680、新品オファー1社のみ、
Amazon 本体の在庫なし、手残り約895円/個・利益率33%。

🔴 **なのにキーゾンで3か月0個**で、「おすすめ出品の要件を満たす出品はありません」＝カートも立っていない。
生存ゲートはこれを `NO-GO`（市場が無い）に落とします。

**でもレビューは153件ありました。**レビュー153件は「**過去は売れていた**」という意味です。
栽培キットは春物で、7〜9月は端境期。つまりこれは「死んだ棚」ではなく「**今が季節外の棚**」でした。

**生存ゲートはこの2つを区別できません。**90日平均ランクも直近3ヶ月の実数も、
「年間を通して売れていない」と「今が端境期」のどちらでも同じ顔をします。

区別する材料は手元にあります
----------------------------
**Keepa の売れ筋ランクの履歴（`csv[3]`）は商品レスポンスにそのまま入っています。**
実測（2026-10-01・23商品）で**23件すべてに入っており、1商品あたり6,456点**ありました。
**追加トークンは0です。**2年ぶんを月（1〜12）に畳めば、

- **年間を通してランクが低い** → 死んでいる（`NO-GO` でよい）
- **特定の月だけ跳ねる** → 季節商品（ピーク月がいつかで扱いを変える）

が分かります。

⚠️ **キーワードでは季節を判定しません。**「鍋」「加湿」のような語は**並べ替えにだけ**使い
（`season_hint()`）、**ゲートを動かすのは履歴（データ）だけ**にします。
商品名から季節を当てるのは「18食入り」と同じ型の推測で、同じ語が逆の意味になります
（「鍋つかみ」は通年・「保温ボトル」は通年に近い）。CLAUDE.md §3.3-17。
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Keepa の時刻は「2011-01-01 00:00 UTC からの分数 − 21564000」。
KEEPA_EPOCH_OFFSET_MIN = 21564000

# この倍率以上ランクが振れていれば季節性ありとみなす（最良月 × 倍率 ≦ 最悪月）。
# 3.0 は「最もよく売れる月に比べて、端境期は順位が3倍以上悪い」という線。
SEASONAL_SWING = 3.0

# ピーク月とみなす範囲（最良月のランク × これ以内）。
# 🔴 1.6 では**季節の「肩の月」が落ちます**。冬物で12月7,000位・11月12,000位のとき、
# 1.6（＝11,200位）だと11月がピークから外れ、「11〜1月にピークか？」の判定を外しました。
# 季節は月単位の山なので、肩まで含める 2.0 が実用的です（テストで固定）。
PEAK_TOLERANCE = 2.0

# 月の中央値を出すのに最低これだけの観測点が要る。
MIN_POINTS_PER_MONTH = 3

# 季節判定を出すのに最低これだけの月が埋まっていないといけない。
MIN_MONTHS_COVERED = 6

# 「いま仕入れて売る」ために優先したい月（2026-10-01 カズヨ指示）。
# 今日が10/1 で、仕入れ→納品→販売までに2〜4週間かかるので、狙うのは11〜1月。
TARGET_MONTHS = (11, 12, 1)

ALL_YEAR = "通年"
SEASONAL = "季節"
DEAD = "通年低調"
UNKNOWN_SEASON = "判定不能"


@dataclass
class Season:
    """季節の判定結果。`verdict` だけ見れば済むようにしてあります。"""

    verdict: str                        # 通年 / 季節 / 通年低調 / 判定不能
    peak_months: tuple[int, ...] = ()   # ピークの月（1〜12）
    best_rank: int | None = None        # 最良月の中央ランク
    worst_rank: int | None = None       # 最悪月の中央ランク
    swing: float | None = None          # worst / best
    months_covered: int = 0
    monthly: dict = field(default_factory=dict)   # {月: 中央ランク}
    reason: str = ""

    def peaks_in_target(self, target: tuple[int, ...] = TARGET_MONTHS) -> bool:
        """ピークが「いま狙いたい月」に入っているか。"""
        return bool(set(self.peak_months) & set(target))

    def label(self) -> str:
        """`判定理由` の先頭に出す1行。**空文字を返しません**（§3.2 空欄を作らない）。"""
        if self.verdict == UNKNOWN_SEASON:
            return f"【季節 判定不能（{self.reason}）】"
        if self.verdict == SEASONAL:
            months = "・".join(f"{m}月" for m in self.peak_months)
            hit = "🔴いま狙う月" if self.peaks_in_target() else "いま狙う月ではない"
            return (f"【季節 {months}にピーク（振れ幅 {self.swing:.1f}倍・"
                    f"最良{self.best_rank:,}位／最悪{self.worst_rank:,}位）＝{hit}】")
        if self.verdict == DEAD:
            return (f"【季節 通年低調（最良月でも{self.best_rank:,}位・"
                    f"{self.months_covered}ヶ月ぶんの履歴）】")
        return (f"【季節 通年（振れ幅 {self.swing:.1f}倍・"
                f"{self.best_rank:,}〜{self.worst_rank:,}位）】")


def _to_dt(km: int) -> datetime:
    """Keepa の分 → UTC の datetime。

    Keepa の定義は `unixTime = (keepaTime + 21564000) * 60`。
    **ここを自分で計算し直さないこと**（1行で済むので、途中で畳むと符号を間違えます）。
    """
    return datetime.fromtimestamp((int(km) + KEEPA_EPOCH_OFFSET_MIN) * 60, tz=timezone.utc)


def parse_rank_history(csv3, days: int = 730, now: datetime | None = None
                       ) -> list[tuple[datetime, int]]:
    """Keepa の `csv[3]`（売れ筋ランクの履歴）→ `[(日時, ランク), ...]`。

    形は `[分, 値, 分, 値, ...]` のフラットな配列で、**値 -1 は「データなし」**です。
    `days` より古い点は捨てます（既定2年＝同じ月を2回観測できる）。
    """
    if not csv3:
        return []
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    out: list[tuple[datetime, int]] = []
    it = iter(csv3)
    for km in it:
        try:
            v = next(it)
        except StopIteration:
            break
        if v is None or v < 0:              # -1 は欠測。0 位は存在しないので 0 も捨てる
            continue
        try:
            t = _to_dt(km)
        except (ValueError, OSError, OverflowError):
            continue
        if t >= cutoff:
            out.append((t, int(v)))
    return out


def monthly_medians(points: list[tuple[datetime, int]]) -> dict[int, int]:
    """月（1〜12）ごとのランク中央値。観測が少ない月は**入れません**（推測で埋めない）。"""
    buckets: dict[int, list[int]] = {}
    for t, v in points:
        buckets.setdefault(t.month, []).append(v)
    return {m: int(statistics.median(vs)) for m, vs in buckets.items()
            if len(vs) >= MIN_POINTS_PER_MONTH}


def classify(csv3, dead_rank: int = 500_000, days: int = 730,
             now: datetime | None = None) -> Season:
    """売れ筋ランクの履歴から季節性を判定する。**追加トークン0。**

    - 月が `MIN_MONTHS_COVERED` 本埋まっていなければ `判定不能`（**通年とも季節とも書かない**）
    - 振れ幅が `SEASONAL_SWING` 倍以上 → `季節`（最良月 × `PEAK_TOLERANCE` 以内の月をピークとする）
    - どの月も `dead_rank` より下 → `通年低調`（本当に死んでいる）
    - それ以外 → `通年`
    """
    pts = parse_rank_history(csv3, days=days, now=now)
    monthly = monthly_medians(pts)
    if len(monthly) < MIN_MONTHS_COVERED:
        return Season(UNKNOWN_SEASON, months_covered=len(monthly), monthly=monthly,
                      reason=f"ランク履歴が{len(monthly)}ヶ月ぶんしかありません"
                             f"（{MIN_MONTHS_COVERED}ヶ月必要）")

    best = min(monthly.values())
    worst = max(monthly.values())
    swing = worst / best if best else None
    peaks = tuple(sorted(m for m, v in monthly.items() if v <= best * PEAK_TOLERANCE))

    if best > dead_rank:
        # 最もよく売れる月でも圏外。これは季節ではなく、本当に売れていない棚。
        # ⚠️ **ピーク月は空にします。**全月が同じように低調なとき `peaks` は全12月になり、
        # `peaks_in_target()` が True を返して「11〜1月の棚」に化けます（テストで固定）。
        # 通年低調にピークという概念はありません。
        return Season(DEAD, (), best, worst, swing, len(monthly), monthly,
                      reason=f"最良月でも{best:,}位（{dead_rank:,}位より下）")

    if swing and swing >= SEASONAL_SWING:
        return Season(SEASONAL, peaks, best, worst, swing, len(monthly), monthly,
                      reason=f"{'・'.join(f'{m}月' for m in peaks)}にピーク")

    return Season(ALL_YEAR, peaks, best, worst, swing, len(monthly), monthly,
                  reason="年間の振れ幅が小さい")


def from_product(product: dict, dead_rank: int = 500_000,
                 now: datetime | None = None) -> Season:
    """Keepa の product をそのまま渡せる口。`csv[3]` が無ければ `判定不能`。"""
    csv = product.get("csv") or []
    csv3 = csv[3] if len(csv) > 3 else None
    if not csv3:
        return Season(UNKNOWN_SEASON,
                      reason="ランク履歴（csv[3]）がレスポンスに入っていません"
                             "（`history=1` を付けて取り直してください）")
    return classify(csv3, dead_rank=dead_rank, now=now)


# ── 並べ替え用の季節ヒント（**ゲートには使いません**）────────────────────────

# 🔴 **これはゲートではなく「順番」のためだけの材料です。**
# 商品名から季節を当てるのは推測で、同じ語が逆の意味になります
# （「鍋つかみ」は通年・「夏用マスク」は夏物だが「マスク」単独は通年）。
# **落とす・残すの判断は `classify()`（履歴）だけが行います。**
WINTER_WORDS = (
    "暖房", "ヒーター", "こたつ", "炬燵", "電気毛布", "湯たんぽ", "カイロ", "防寒",
    "加湿", "保温", "あったか", "もこもこ", "フリース", "ルームシューズ", "ひざ掛け",
    "鍋", "土鍋", "卓上コンロ", "蒸し器", "おでん", "しゃぶしゃぶ", "すき焼き",
    "乾燥対策", "静電気", "リップ", "ハンドクリーム", "入浴剤", "結露",
    "クリスマス", "年末", "年始", "正月", "おせち", "福袋", "お歳暮", "受験", "合格",
    "スノー", "雪", "スキー", "スノボ", "手袋", "マフラー", "ニット", "ダウン",
)
SUMMER_WORDS = (
    "冷感", "涼", "扇風機", "サーキュレーター", "うちわ", "日傘", "日焼け", "UV",
    "虫よけ", "虫除け", "蚊", "殺虫", "water", "プール", "浮き輪", "水着", "浴衣",
    "かき氷", "製氷", "クーラーボックス", "保冷", "熱中症", "汗", "制汗", "除湿",
)
# ⚠️ **短い語を入れないこと。**「土」を入れたら「**土鍋**」が春物に当たり、
# 冬物と春物の両方にヒットして「不明」に落ちていました（テストで固定）。
# 「種」も「各種」「品種」に当たるので使いません。
SPRING_WORDS = (
    "栽培", "園芸", "種まき", "種子", "苗", "プランター", "花壇", "肥料", "培養土",
    "ガーデニング", "入学", "入園", "新学期", "新生活", "花見", "こいのぼり",
    "ひな祭", "雛祭", "母の日",
)
AUTUMN_WORDS = ("運動会", "ハロウィン", "敬老", "紅葉", "読書", "月見")


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKC", str(s or ""))


def season_hint(title: str | None, category: str | None = None) -> str:
    """商品名・カテゴリから推測した季節。**並べ替え専用**。

    複数の季節に当たったら「不明」を返します（片方を黙って採らない）。
    """
    t = _norm(title) + " " + _norm(category)
    hits = {name for name, words in (("冬", WINTER_WORDS), ("夏", SUMMER_WORDS),
                                     ("春", SPRING_WORDS), ("秋", AUTUMN_WORDS))
            if any(w in t for w in words)}
    if len(hits) == 1:
        return hits.pop()
    return "不明"


def order_key(season: Season | None, title: str | None = None,
              category: str | None = None,
              target: tuple[int, ...] = TARGET_MONTHS) -> int:
    """判定の順番（小さいほど先）。**11〜1月に売れるものを先に見る**（カズヨ指示 2026-10-01）。

    | 値 | 中身 |
    |---|---|
    | 0 | 履歴のピークが 11〜1月（**データで裏が取れた冬物**） |
    | 1 | 履歴は通年で、商品名が冬物（在庫を抱えても売れ続ける） |
    | 2 | 履歴は通年で、商品名も通年 |
    | 3 | 季節不明・判定不能 |
    | 4 | 商品名が秋物 |
    | 5 | 履歴のピークが春夏、または商品名が春物・夏物（**在庫6ヶ月になるので初回には使わない**） |
    """
    hint = season_hint(title, category)
    if season and season.verdict == SEASONAL:
        if season.peaks_in_target(target):
            return 0
        return 5                        # ピークが春夏＝今から仕入れると半年寝かせる
    if season and season.verdict == ALL_YEAR:
        return 1 if hint == "冬" else 2
    if hint == "冬":
        return 1
    if hint in ("春", "夏"):
        return 5
    if hint == "秋":
        return 4
    return 3
