#!/usr/bin/env python3
"""まとめ売り突合 — 「卸の1点」と「Amazon の1個」をつなぐ1枚（純関数）。

なぜ要るか（2026-10-01 カズヨが SD の実画面で確定させたこと）
-------------------------------------------------------------
日用消耗品は**単品では構造的に黒字になりません**。固定費（FBA 配送代行 + 保管/納品/資材 +
誤差幅）が1個あたり 821円かかるので、卸178円のたわしでも必要売価が **1,214円**になります。
1個1,214円のたわしは売れません。

だから「×10点セット」等の**まとめ売りを1商品として出し、固定費を10個で割る**のが前提です。
`required_sell()` の第2引数 `n` がその「何個で割るか」です。

🔴 そして **JAN は単品とセットで同一**です（旭化成 ズビズバ あみたわし 4901670106107 は
SD の「1点」「×10点」「×200点」すべて同じ JAN）。**JAN 突合はいつも単品 ASIN に当たります。**
これが 9/30・10/1 の単位ずれの構造的な原因でした。

🟢 実測でわかった救い（2026-10-01・1リクエスト10トークン）
---------------------------------------------------------
**Keepa の `code` 逆引きは、その JAN のセット品 ASIN を最初から全部返していました。**
4901670106107 の1リクエストで10 ASIN（×1 / ×2 / ×3 / ×4 / ×5 / ×6 / ×7 / ×10 / ×200）。
`discover._pick_best()` が**そのうち1件だけを採って残り9件を捨てていた**のが本当の損失です。
**課金は「返ってきた商品数」なので、捨てた9件もすでに払っています。**
セット品を集めるのに追加トークンは1つも要りません。拾い直すだけです。

さらに `packageQuantity` が**セット数そのもの**として入っていました（上の10件で 1/2/3/4/5/6/7/10/200）。
商品名の正規表現とは**独立した2本目の情報源**になります（CLAUDE.md §3.3-17 の「機械で検査する」）。

| ASIN | 商品名 | packageQuantity | numberOfItems |
|---|---|---|---|
| B01MU0SNTZ | 【セット品】…×4個 | 4 | -1 |
| B01MCR1XMK | … × 3個セット | 3 | **1** |
| B00H2E0JLW | … 2個セット | **1** | 2 |

`numberOfItems` は 1 が既定値として入ることがあり、`packageQuantity` も 1 に落ちることがあります。
**だから多数決はしません。**商品名と `packageQuantity` の2本が一致したときだけ「確定」で、
食い違ったら **大きい方を採って「不一致」**にします（原価を安く見積もる方向へ推測しない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import seasonality
import set_count

# packageQuantity / numberOfItems として受け付ける上限。
# 商品名側（`set_count.MAX_PLAUSIBLE = 60`）より広く取ります。「600粒」を60個と誤読する心配が
# 無い構造化フィールドなので、×200個セットのような実在の大口を切り落とす方が害が大きい。
MAX_STRUCTURED = 1000

# 判定の確度。呼び出し側は `is_decided()` だけを見れば済みます。
CONFIRMED = "確定"      # 商品名と packageQuantity が一致した
SINGLE = "単独"         # 情報源が1本だけ
CONFLICT = "不一致"     # 2本が食い違った → **人が両方の画面を見る**
UNREADABLE = "不明"     # どちらも読めない


@dataclass
class SetCount:
    """Amazon の1個が卸の何点にあたるか、と**その根拠**。"""

    n: int | None                       # 原価の倍率。None なら決められなかった
    confidence: str                     # 確定 / 単独 / 不一致 / 不明
    sources: dict = field(default_factory=dict)   # {"商品名": 4, "packageQuantity": 4, ...}
    reason: str = ""

    def is_decided(self) -> bool:
        """機械の判定を GO に進めてよいか。

        - `確定` … 独立2本が一致した。進めてよい
        - `単独` で **n == 1** … 単品。倍率の取り違えが起きない側なので進めてよい
        - それ以外 … **UNKNOWN**（人が卸サイトと Amazon の両方を見る）
        """
        if self.confidence == CONFIRMED:
            return True
        return self.confidence == SINGLE and self.n == 1


def _structured(v) -> int | None:
    """packageQuantity / numberOfItems を読む。0 と -1 は「データなし」の印。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= MAX_STRUCTURED else None


def resolve(title: str | None, package_quantity=None, number_of_items=None) -> SetCount:
    """商品名 × packageQuantity（× numberOfItems）から倍率を決める。

    `numberOfItems` は**判定には使いません**（1 が既定値として入る実例があるため）。
    記録だけ残して、人が見るときの材料にします。
    """
    title_n = set_count.parse_amazon_set_count(title)
    pq = _structured(package_quantity)
    noi = _structured(number_of_items)

    sources: dict = {}
    if title_n is not None:
        sources["商品名"] = title_n
    if pq is not None:
        sources["packageQuantity"] = pq
    if noi is not None:
        sources["numberOfItems(参考)"] = noi      # 参考。判定には使わない

    if title_n is not None and pq is not None:
        if title_n == pq:
            return SetCount(title_n, CONFIRMED, sources,
                            f"Amazon の1個 ＝ 卸の{title_n}点"
                            f"（商品名と packageQuantity が一致）。")
        n = max(title_n, pq)
        return SetCount(n, CONFLICT, sources,
                        f"商品名は{title_n}点・packageQuantity は{pq}点で食い違います。"
                        f"原価を安く見積もらないため大きい方（{n}点）で計算しますが、"
                        f"**人が卸サイトと Amazon の両方を見てください。**")

    only = title_n if title_n is not None else pq
    if only is not None:
        where = "商品名" if title_n is not None else "packageQuantity"
        return SetCount(only, SINGLE, sources,
                        f"Amazon の1個 ＝ 卸の{only}点（{where}だけが読めました）。"
                        + ("" if only == 1 else "2本目の裏が取れていないので人が確認してください。"))

    return SetCount(None, UNREADABLE, sources,
                    "商品名からも packageQuantity からもセット数が読めません"
                    "（『18食入り』型は中身の数とも個数とも読めます）。"
                    "原価の倍率が決まらないので**人が両方の画面を見てください。**")


# ── セット品ファミリ（同じ JAN にぶら下がる ASIN 群）────────────────────────


@dataclass
class Member:
    """ファミリの1員。1 ASIN ＝ 1行として採算を見ます。"""

    asin: str
    title: str
    set_count: SetCount
    sell: int | None = None
    rank_now: int | None = None
    rank_avg90: int | None = None
    monthly_sold: int | None = None
    parent_asin: str | None = None
    fee_pct: float | None = None        # 販売手数料率（税抜表示）。None なら未取得
    fba_yen: int | None = None          # FBA 配送代行（円）。None なら未取得
    package_quantity: int | None = None  # Keepa の生値（0 / -1 は「データなし」）
    number_of_items: int | None = None   # Keepa の生値（参考。1 が既定値として入る）
    season: object | None = None         # seasonality.Season。履歴が無ければ「判定不能」
    review_count: int | None = None      # COUNT_REVIEWS（rating=1 が無いと -1）


def family_members(products: list[dict]) -> list[Member]:
    """Keepa の `code` 逆引きが返した商品群 → セット品ファミリ。

    **1件に絞りません。**`discover._pick_best()` は「ランクが付いていて一番上位のもの」を
    1件だけ採っていましたが、それは**まとめ売りの口を全部捨てる**動きでした。
    返ってきた商品は全部すでに課金済みなので、拾わない理由がありません。
    """
    out: list[Member] = []
    for p in products:
        st = p.get("stats") or {}
        cur = st.get("current") or []
        avg = st.get("avg90") or []

        def at(seq, i):
            v = seq[i] if isinstance(seq, list) and len(seq) > i else None
            return None if v in (None, -1) else v

        sell = next((v for v in (st.get("buyBoxPrice"), at(cur, 1), at(cur, 0))
                     if v and v > 0), None)
        ms = p.get("monthlySold")
        fee = p.get("referralFeePercent")
        if fee in (None, -1):
            fee = p.get("referralFeePercentage")
        fee = None if fee in (None, -1) else float(fee)
        fba = (p.get("fbaFees") or {}).get("pickAndPackFee")
        fba = None if fba in (None, -1, 0) else int(fba)
        out.append(Member(
            asin=p.get("asin") or "",
            title=(p.get("title") or "")[:160],
            set_count=resolve(p.get("title"), p.get("packageQuantity"),
                              p.get("numberOfItems")),
            sell=sell,
            rank_now=at(cur, 3),
            rank_avg90=at(avg, 3),
            monthly_sold=None if ms in (None, -1) else ms,
            parent_asin=p.get("parentAsin") or None,
            fee_pct=fee, fba_yen=fba,
            package_quantity=p.get("packageQuantity"),
            number_of_items=p.get("numberOfItems"),
            season=seasonality.from_product(p),
            review_count=at(cur, 17),
        ))
    # 大きい口から見る（固定費を割れるのは大きい口なので、当たりが先に出る）。
    out.sort(key=lambda m: -(m.set_count.n or 0))
    return out


def extra_asins(products: list[dict]) -> list[str]:
    """同じ JAN には乗っていないが、同じ棚の可能性がある ASIN（バリエーション・親）。

    `variations` と `parentAsin` は**同じレスポンスに入っている**ので、ここを拾うのも
    追加トークン0です。実際に採算を見るには `stats` が要るので、
    呼び出し側が**1トークン/ASIN の安い段**でまとめて取り直してください。
    """
    seen: set[str] = {p.get("asin") for p in products if p.get("asin")}
    out: list[str] = []
    for p in products:
        for a in (p.get("parentAsin"),):
            if a and a not in seen:
                seen.add(a)
                out.append(a)
        for v in (p.get("variations") or []):
            a = v.get("asin") if isinstance(v, dict) else v
            if a and a not in seen:
                seen.add(a)
                out.append(a)
    return out


# ── 「黒字になるセット数の下限」を逆から攻める ──────────────────────────────

# 既定値。実額が分かっているときは必ず実額を渡してください（ここは目安の計算用）。
DEFAULT_FEE_PCT = 8.4            # 販売手数料率（税抜表示）。×1.1 で税込
DEFAULT_FBA_YEN = 415            # FBA 配送代行（小型〜標準の目安）
OTHER_UNIT_COSTS_YEN = 206       # 保管87 + 納品送料64 + 梱包資材55（商品台帳 L001 実測）
BAND_PCT = 7.0                   # 手残りの誤差幅（売価比）
BAND_FIXED = 200                 # 手残りの誤差幅（固定ぶん）
TAX = 1.1


def required_sell(wholesale_excl_per_point: float, n: int = 1,
                  fee_pct: float = DEFAULT_FEE_PCT, fba_yen: float = DEFAULT_FBA_YEN,
                  other: float = OTHER_UNIT_COSTS_YEN,
                  band_pct: float = BAND_PCT, band_fixed: float = BAND_FIXED
                  ) -> float | None:
    """**「n点セットとして出すなら、いくらで売れていないと駄目か」。**

        手残り = 売価 − 販売手数料 − FBA − 原価 − その他
        GO 条件: 手残り ≥ 売価 × band_pct% + band_fixed

      → 売価 ≥ (FBA + その他 + band_fixed + 1.1 × 卸値 × n) / (1 − 0.011×fee_pct − band_pct/100)

    既定値（fee 8.4% / FBA 415）だと分母 0.8376・分子の固定ぶん 821 で、
    カズヨが SD の実画面から出した式 `(821 + 1.1×卸値) ÷ 0.8376` と一致します。

    **固定費（FBA + その他 + 誤差幅 = 821円）は Amazon の1個につき1回しかかかりません。**
    だから n を増やすと1点あたりの必要売価は下がります（`required_sell_per_point`）。
    分母が 0 以下（手数料率が極端）なら None。
    """
    denom = 1.0 - (fee_pct * TAX / 100.0) - (band_pct / 100.0)
    if denom <= 0:
        return None
    fixed = float(fba_yen) + float(other) + float(band_fixed)
    return (fixed + TAX * float(wholesale_excl_per_point) * max(1, int(n))) / denom


def required_sell_per_point(wholesale_excl_per_point: float, n: int = 1, **kw) -> float | None:
    """n点セットの必要売価を**卸1点あたり**に直したもの（横並びで比べるため）。"""
    s = required_sell(wholesale_excl_per_point, n, **kw)
    return None if s is None else s / max(1, int(n))


def required_sell_table(wholesale_excl_per_point: float,
                        ns: tuple[int, ...] = (1, 2, 3, 5, 10, 20), **kw
                        ) -> list[tuple[int, int, int]]:
    """`[(n, 必要売価, 1点あたりの必要売価), ...]`。社長向けの表にそのまま出せます。"""
    out = []
    for n in ns:
        s = required_sell(wholesale_excl_per_point, n, **kw)
        if s is None:
            continue
        out.append((n, int(round(s)), int(round(s / n))))
    return out


def min_profitable_set_count(wholesale_excl_per_point: float, sell_per_point: float,
                             max_n: int = 200, **kw) -> int | None:
    """**黒字になるセット数の下限。**「1点あたりこの値段なら売れる」という前提から逆に引きます。

    `sell_per_point` は「Amazon でその棚が1点あたりいくらで売れているか」。
    n を1から増やし、`n × sell_per_point ≥ required_sell(w, n)` を最初に満たす n を返します。
    どの n でも成り立たなければ None（＝この卸値では、まとめ売りでも黒字にならない）。

    固定費を n で割る効果しか無いので、**単調**です（一度満たせば以降も満たす）。
    """
    if not sell_per_point or sell_per_point <= 0:
        return None
    for n in range(1, max(1, int(max_n)) + 1):
        need = required_sell(wholesale_excl_per_point, n, **kw)
        if need is not None and n * float(sell_per_point) >= need:
            return n
    return None


# ── 卸側の「口」を選ぶ（1点 / 10点 / 100点）──────────────────────────────


@dataclass
class Mouth:
    """卸側の1つの口（SD の規格 S1/S2/S3、NETSEA の `set[]` の1件）。

    `per_point_excl` は**必ず「卸1点あたりの税抜」**に直してから入れてください。
    画面の数字が「1セットあたり」なのか「1点あたり」なのかは**サイトと企業で違います**。
    読めないまま入れると、9/30・10/1 と同じ単位ずれを3回目として作ります。
    """

    code: str                       # SD品番 / NETSEA の識別子
    units_per_set: int | None       # 1セット◯点。**None なら選べません（推測しない）**
    per_point_excl: int | None      # 卸1点あたり（税抜）
    label: str = ""                 # 「1点」「×10点セット」など画面の表記
    min_lot_sets: int = 1           # 最小発注セット数


@dataclass
class MouthChoice:
    mouth: Mouth | None
    sets_to_order: int              # 卸で何セット買うか
    points_to_buy: int              # それが卸の何点になるか
    amazon_units: int               # Amazon 何個ぶんになるか
    leftover_points: int            # 余る点数（在庫として持つ）
    reason: str


def pick_mouth(mouths: list[Mouth], needed_points: int, amazon_set_count: int
               ) -> MouthChoice:
    """必要な点数に対して、**どの口を何セット買うか**を決める。

    選び方は「1点あたりが安い口」→「余りが少ない口」。入り数が読めない口は**候補から外します**
    （`units_per_set is None` を 1 と決め打つと原価を取り違えます）。
    選べる口が1つも無ければ `mouth=None`（＝UNKNOWN。人が卸サイトを見る）。
    """
    needed = max(1, int(needed_points))
    usable = [m for m in mouths
              if m.units_per_set and m.units_per_set > 0 and m.per_point_excl]
    if not usable:
        return MouthChoice(None, 0, 0, 0, 0,
                           "入り数か卸価格が読めている口がありません"
                           "（入り数を 1 と決め打ちません）。人が卸サイトを見てください。")

    best: tuple | None = None
    for m in usable:
        sets_ = max(int(m.min_lot_sets or 1), -(-needed // m.units_per_set))
        points = sets_ * m.units_per_set
        key = (m.per_point_excl, points - needed, m.units_per_set)
        if best is None or key < best[0]:
            best = (key, m, sets_, points)

    _key, m, sets_, points = best
    per = max(1, int(amazon_set_count or 1))
    return MouthChoice(
        mouth=m, sets_to_order=sets_, points_to_buy=points,
        amazon_units=points // per, leftover_points=points - needed,
        reason=(f"卸は「{m.label or m.units_per_set}」の口を{sets_}セット"
                f"（＝{points}点）買います。Amazon の1個が卸{per}点なので "
                f"{points // per}個ぶんになり、余り{points - needed}点です。"),
    )
