#!/usr/bin/env python3
"""終売フラグ（CLAUDE.md §3.5 #12「生産終了でないか」の機械の前段）。純関数・通信0。

2026-10-11 タカシ（T-20260920-003）。

なぜ要るか
----------
2026-10-11、GO にした蛍光灯 FLR910（DN ライティング）は、水俣条約で一般照明用の蛍光ランプの
製造・輸出入が段階的に禁止される品目だった。§3.5 #12 は「メーカー公式で見る」項目で、
機械判定のどこにも入っていなかった。**終売品は消極条件（本体なし・出品者少・卸が安い・
回転あり）を全部通る**ので（memory: knowledge_discontinued_bias_in_margin_ranking）、
機械側で先に印を付ける。

2段構え
-------
① **終売の印**（`RULES` ＋ 卸の「廃番」記載）… 法令で製造・輸入の終了が決まっている品目
   （根拠 URL を辞書に持つ）と、仕入れ先自身が廃番と書いている商品。**印を付けるだけで自動では落とさない。**
② **兆候**（`signs()`）… Keepa の履歴から「終売の匂い」を拾う。当たっても `UNKNOWN`
   （人がメーカー公式の製品DBで確認する）。**兆候だけでは落とさない。**

🔴 2026-10-12 社長方針（CLAUDE.md §3.5 #12）：「**今だけ、儲かるなら、廃止が決まっているものも仕入れて良い**」。
   ①の印が付いた商品は、次の3条件（`NowOnly`）で判定する。
     (a) 仕入れ先に在庫がある
     (b) 廃止期限（製造終了日）・在庫切れまでに売り切れる＝在庫月数 ≦ 期限までの月数
         （期限が過ぎている／期限が無い卸の廃番は `AFTER_END_MONTHS`＝3か月の仮置き）
     (c) 価格が上昇〜横ばい（下落トレンドでない）
   3つとも満たせば PASS（印は判定理由に残す）、1つでも満たさなければ NO-GO、確かめていなければ UNKNOWN。
   2026-10-11 までは①に当たれば一律 NO-GO だった（理由＝リピート不可）。

⚠️ 法令の「製造・輸出入禁止」は**販売の禁止ではありません**（環境省「蛍光ランプの使用・販売・
購入は禁止されません」）。終売品のリスクは違法性ではなく、**供給が止まる＝リピートできない**ことと
**在庫が売れ残ったまま市場が縮む**こと。後者を (b)(c) で見る。

使い方
------
    from discontinued import check
    d = check(product, amazon_title, wholesale_title="", wholesale_note="", now_unix=fetched)
    d = check(..., now_only=NowOnly(in_stock=True, months_to_sell=1.6, price_trend=UP_OR_FLAT,
                                    today=date(2026, 10, 12)))
    d.verdict   # "NO-GO" / "UNKNOWN" / "PASS"
    d.marked    # 終売の印（法令品目・卸の廃番）。PASS でも True のことがある
    d.label()   # 台帳の判定理由に入れる1行
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from statistics import median

NO_GO = "NO-GO"
UNKNOWN = "UNKNOWN"
PASS = "PASS"

KEEPA_EPOCH_MIN = 21564000          # Keepa 時刻（分）= Unix 分 − これ

ENV_LAMP_URL = "https://www.env.go.jp/chemi/tmms/lamp.html"


@dataclass(frozen=True)
class Rule:
    """法令などで製造終了が決まっている品目の1行。"""

    key: str
    label: str
    ends: str                 # 製造・輸出入が止まる日（人が読む文字列）
    source_url: str
    source_note: str
    confirmed: bool           # 公的資料で確かめたか。False のルールは UNKNOWN に留める
    pattern: re.Pattern


# ── 品目の当て方 ──────────────────────────────────────────────────────────
# 🔴 「蛍光灯」という語だけでは当てない。**LED 蛍光灯（LED の直管）は規制対象外**で、
#    「蛍光灯カバー」「蛍光ペン」「蛍光灯器具」も別物。型番（JIS の形式記号）か、
#    「蛍光ランプ/蛍光灯/蛍光管」＋ LED でない、で当てる。
_LED = re.compile(r"LED|ＬＥＤ|ｌｅｄ|発光ダイオード", re.I)
_NOT_LAMP = re.compile(r"カバー|ペン|マーカー|塗料|テープ|シール|器具|スタンド|ソケット|"
                       r"安定器|グロー|点灯管|反射板|ホルダー|ガード|蛍光色|蛍光イエロー|"
                       r"蛍光ピンク|蛍光グリーン|蛍光オレンジ|蛍光ブルー|蛍光剤|増白")
_LAMP_WORD = re.compile(r"蛍光ランプ|蛍光灯|蛍光管|ツイン蛍光|コンパクト形蛍光|電球形蛍光|電球型蛍光")

# JIS C 7601 系の形式記号。数字が直後に続くものだけ（"FL" 単独や "FLAT" に当てない）
_BULB = re.compile(r"(?<![A-Z])EF[ADGT]\s?\d{1,3}", re.I)                   # 電球形
_COMPACT = re.compile(r"(?<![A-Z])F(?:PL|HT|DL|ML|GL|HP|PR|DT)\s?\d{1,3}", re.I)  # コンパクト形
_RING = re.compile(r"(?<![A-Z])F(?:CL|HC|HD)\s?\d{2,3}", re.I)               # 環形
_TUBE = re.compile(r"(?<![A-Z])F(?:LR|HF|L)\s?\d{2,3}", re.I)                # 直管形


def _norm(s: str | None) -> str:
    return unicodedata.normalize("NFKC", s or "")


def lamp_kind(title: str | None) -> str | None:
    """一般照明用の蛍光ランプなら種類（電球形/コンパクト形/環形/直管形/種類不明）を返す。"""
    t = _norm(title)
    if not t or _LED.search(t):
        return None
    word = bool(_LAMP_WORD.search(t))
    if _NOT_LAMP.search(t) and not (_BULB.search(t) or _COMPACT.search(t)
                                    or _RING.search(t) or _TUBE.search(t)):
        return None
    if _BULB.search(t) or re.search(r"電球形蛍光|電球型蛍光", t):
        return "電球形"
    if _COMPACT.search(t) or re.search(r"コンパクト形蛍光|ツイン蛍光", t):
        return "コンパクト形"
    if _RING.search(t) or (word and re.search(r"丸形|環形|サークライン", t)):
        return "環形"
    if _TUBE.search(t) or (word and re.search(r"直管", t)):
        return "直管形"
    if word:
        return "種類不明"
    return None


# 環境省「一般照明用の蛍光ランプの規制」（2026-10-11 に原文を確認）
#   電球形 2026年1月1日（30W超は2027年1月1日）／コンパクト形 2027年1月1日／
#   直管形・環形 2028年1月1日（ハロりん酸塩を主成分とする蛍光体は2027年1月1日）
LAMP_ENDS = {
    "電球形": "2026-01-01（30W超は2027-01-01）",
    "コンパクト形": "2027-01-01",
    "環形": "2028-01-01（ハロりん酸塩系は2027-01-01）",
    "直管形": "2028-01-01（ハロりん酸塩系は2027-01-01）",
    "種類不明": "2026-01-01〜2028-01-01（種類で異なる）",
}

RULES: tuple[Rule, ...] = (
    Rule("fluorescent", "一般照明用の蛍光ランプ（水俣条約・水銀汚染防止法施行令 2024年12月改正）",
         "種類別（LAMP_ENDS）", ENV_LAMP_URL,
         "環境省：一般照明用の蛍光ランプは種類ごとに製造・輸出入を禁止。"
         "使用・販売・購入は禁止されない＝在庫の流通は続くが供給は止まる",
         True, re.compile(r"$^")),   # 判定は lamp_kind() で行う（パターンは使わない）
    Rule("hg_hid", "一般照明用の高圧水銀ランプ",
         "2021-01-01", "https://cgi.jp.sharp/business/led_lighting/images/pamphlet.pdf",
         "民間資料（シャープ）の記載のみ。公的資料で未確認のため UNKNOWN に留める",
         False, re.compile(r"高圧水銀ランプ|水銀灯|(?<![A-Z])HF\s?\d{2,4}(?:X|BH|Y)", re.I)),
    Rule("incandescent", "一般照明用の白熱電球",
         "法令上の期限なし（2012年に国内大手が生産終了・行政の要請）", "",
         "法令ではなくメーカーの自主的な生産終了。中小メーカーは継続している例があるので"
         "UNKNOWN に留める（人がメーカー公式で現行品か確認）",
         False, re.compile(r"白熱電球|白熱球|シリカ電球|クリア電球|ミニクリプトン")),
    Rule("hg_medical", "水銀体温計・水銀血圧計",
         "未確認（水銀汚染防止法の特定水銀使用製品と推定）", "",
         "公的資料で期限を確かめていない。UNKNOWN に留める",
         False, re.compile(r"水銀体温計|水銀血圧計|水銀式体温計|水銀式血圧計")),
)


@dataclass
class RuleHit:
    rule: Rule
    detail: str = ""
    ends: str = ""

    def text(self) -> str:
        src = f" 根拠 {self.rule.source_url}" if self.rule.source_url else ""
        return (f"{self.rule.label}{('・' + self.detail) if self.detail else ''}"
                f"（製造・輸出入の終了 {self.ends or self.rule.ends}）。"
                f"{self.rule.source_note}。{src}")


def classify(*titles: str | None) -> RuleHit | None:
    """分類ルール。Amazon の商品名と卸の商品名のどちらかに当たれば返す。"""
    for t in titles:
        kind = lamp_kind(t)
        if kind:
            return RuleHit(RULES[0], f"種類：{kind}", LAMP_ENDS[kind])
    for t in titles:
        nt = _norm(t)
        if not nt:
            continue
        for r in RULES[1:]:
            if r.pattern.search(nt) and not (r.key == "incandescent" and _LED.search(nt)):
                return RuleHit(r)
    return None


# ── 「今だけ」判定（2026-10-12 社長方針・§3.5 #12） ───────────────────────

UP_OR_FLAT = "上昇〜横ばい"
DOWN = "下落"
#: 製造終了日を過ぎた品目／期限の無い卸の廃番は、在庫がいつ尽きるか分からない。
#: 3か月で売り切れる量だけを通す（仮置き・§3.1。実績で直す）。
AFTER_END_MONTHS = 3.0
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class NowOnly:
    """「今だけ」判定の材料。None は未確認（＝UNKNOWN になる）。"""

    in_stock: bool | None = None           # (a) 仕入れ先に在庫
    months_to_sell: float | None = None    # (b) 在庫月数（推奨初回点数 ÷ 取り分）
    price_trend: str | None = None         # (c) UP_OR_FLAT / DOWN / None
    today: date | None = None


def end_date(ends: str | None) -> date | None:
    """「2028-01-01（ハロりん酸塩系は2027-01-01）」の先頭の日付＝その種類の主たる終了日。"""
    m = _ISO.search(ends or "")
    return date.fromisoformat(m.group(0)) if m else None


def now_only_verdict(ctx: NowOnly | None, ends: str | None) -> tuple[str, str]:
    """(PASS/NO-GO/UNKNOWN, 理由)。3条件を全部満たせば PASS。"""
    ctx = ctx or NowOnly()
    today = ctx.today or date.today()
    d = end_date(ends)
    if d and d > today:
        limit = round((d - today).days / 30.4, 1)
        lim_txt = f"製造終了 {d.isoformat()} まで {limit}か月"
    else:
        limit = AFTER_END_MONTHS
        lim_txt = (f"製造終了 {d.isoformat()} を過ぎている" if d else "終了日の記載なし") \
            + f"ため {AFTER_END_MONTHS:g}か月（仮置き）"
    fails, unknowns, oks = [], [], []
    if ctx.in_stock is None:
        unknowns.append("(a)仕入れ先の在庫 未確認")
    elif ctx.in_stock:
        oks.append("(a)仕入れ先に在庫あり")
    else:
        fails.append("(a)仕入れ先に在庫なし")
    if ctx.months_to_sell is None:
        unknowns.append(f"(b)在庫月数 未確認（上限 {lim_txt}）")
    elif ctx.months_to_sell <= limit:
        oks.append(f"(b)在庫 {ctx.months_to_sell:.1f}か月 ≦ {lim_txt}")
    else:
        fails.append(f"(b)在庫 {ctx.months_to_sell:.1f}か月 ＞ {lim_txt}")
    if ctx.price_trend is None:
        unknowns.append("(c)価格の傾き 未確認")
    elif ctx.price_trend == DOWN:
        fails.append("(c)価格が下落トレンド（値崩れ）")
    else:
        oks.append(f"(c)価格は{ctx.price_trend}")
    verdict = NO_GO if fails else (UNKNOWN if unknowns else PASS)
    head = {PASS: "今だけ仕入れ可", NO_GO: "今だけ仕入れ不可", UNKNOWN: "今だけ仕入れ 判定待ち"}[verdict]
    return verdict, f"{head}：" + "・".join(fails + unknowns + oks)


def now_only_from(stock_status: str | None, months_to_sell: float | None,
                  price_verdict: str | None, today: date | None = None) -> NowOnly:
    """パイプラインのゲート表から NowOnly を作る（台帳・仕入れ先ふるいの共通口）。

    stock_status  … 「仕入れ」ゲートの PASS / FAIL / UNKNOWN
    price_verdict … price_history.PriceLevel.verdict（下落トレンド→下落・使える/高値→上昇〜横ばい・他→未確認）
    """
    stock = {"PASS": True, "FAIL": False}.get(stock_status or "")
    trend = {"下落トレンド": DOWN, "使える": UP_OR_FLAT, "高値": UP_OR_FLAT}.get(price_verdict or "")
    return NowOnly(stock, months_to_sell, trend, today)


# ── 商品名・卸の注記に書かれた終売の語 ────────────────────────────────────

# 卸側が自分で「廃番」と書いている＝仕入れ先自身が終わりを宣言している → NO-GO
SUPPLIER_END_RE = re.compile(r"廃番|廃盤|生産終了|製造終了|製造中止|生産中止|終売|取扱終了|取扱い終了|"
                             r"取り扱い終了|販売終了|メーカー欠品|再入荷予定なし|再生産なし")
# Amazon の商品名に出る「在庫限り」系 → 兆候（UNKNOWN）
AMAZON_END_RE = re.compile(r"在庫限り|在庫処分|廃番|廃盤|生産終了|製造終了|終売|旧モデル|旧型|"
                           r"旧パッケージ|販売終了")


# ── Keepa の履歴から拾う兆候 ──────────────────────────────────────────────

CSV_AMAZON, CSV_NEW, CSV_RANK, CSV_COUNT_NEW = 0, 1, 3, 11
DAY = 1440


def _pairs(csv_list, idx: int) -> list[tuple[int, int]]:
    c = csv_list[idx] if csv_list and len(csv_list) > idx and csv_list[idx] else []
    return [(c[i], c[i + 1]) for i in range(0, len(c) - 1, 2)]


@dataclass
class Sign:
    key: str
    strong: bool
    text: str


def signs(product: dict, now_unix: int | None) -> list[Sign]:
    """終売の兆候。**強い兆候1つ、または弱い兆候2つ以上で UNKNOWN**（`check()`）。

    強い兆候
      - 新品出品者数の崖落ち：120〜30日前の中央値が3社以上 → いま1社以下
      - 新品の出品が60日以上ゼロ（新品最安が -1 のまま）
      - ランク（csv[3]）の更新が60日以上止まっている
    弱い兆候
      - Amazon 本体：180〜540日前に在庫を持っていたのに、直近180日は一度も在庫なし
        （第三者だけの棚では普通に起きるので、これ単独では落とさない）
    """
    if not product or not now_unix:
        return []
    now = now_unix // 60 - KEEPA_EPOCH_MIN
    csv_list = product.get("csv") or []
    out: list[Sign] = []

    cnt = _pairs(csv_list, CSV_COUNT_NEW)
    if cnt:
        past = [v for t, v in cnt if now - 120 * DAY <= t < now - 30 * DAY and v >= 0]
        # 30日前時点の値（窓の中に点が無ければ直前の値を持ち越す）
        before = [v for t, v in cnt if t < now - 120 * DAY and v >= 0]
        if not past and before:
            past = [before[-1]]
        cur = cnt[-1][1]
        if past and median(past) >= 3 and 0 <= cur <= 1:
            out.append(Sign("offer_cliff", True,
                            f"新品出品者数が崖落ち（120〜30日前の中央値 {median(past):g}社 → いま {cur}社）"))

    new = _pairs(csv_list, CSV_NEW)
    if new and new[-1][1] == -1:
        last_pos = max((t for t, v in new if v > 0), default=None)
        since = new[-1][0] if last_pos is None else last_pos
        days = (now - since) // DAY
        if days >= 60:
            out.append(Sign("no_new_offer", True, f"新品の出品が {days}日以上ゼロ"))

    rank = _pairs(csv_list, CSV_RANK)
    if rank:
        last_t, last_v = rank[-1]
        days = (now - last_t) // DAY
        if last_v == -1 and days >= 60:
            out.append(Sign("rank_gone", True, f"売れ筋ランクが {days}日前から消えている"))
        elif days >= 60 and last_v > 0:
            out.append(Sign("rank_stale", True, f"売れ筋ランクの更新が {days}日止まっている"))

    amz = _pairs(csv_list, CSV_AMAZON)
    if amz:
        old = any(v > 0 for t, v in amz if now - 540 * DAY <= t < now - 180 * DAY)
        # 直近180日：窓の中の点と、窓に入る直前の値（持ち越し）の両方を見る
        prior = [v for t, v in amz if t < now - 180 * DAY]
        recent = [v for t, v in amz if t >= now - 180 * DAY] + (prior[-1:] if prior else [])
        if old and recent and all(v <= 0 for v in recent):
            out.append(Sign("amazon_gone", False,
                            "Amazon 本体が180〜540日前は在庫を持っていたが直近180日は在庫なし"))
    return out


# ── まとめ ────────────────────────────────────────────────────────────────


@dataclass
class Discontinued:
    verdict: str                       # NO-GO / UNKNOWN / PASS
    rule: RuleHit | None = None
    reasons: list[str] = field(default_factory=list)
    marked: bool = False               # 終売の印（法令品目・卸の廃番）。PASS でも残す

    def label(self) -> str:
        if self.verdict == PASS and not self.marked:
            return "終売の印なし（分類ルール・兆候とも該当なし。メーカー公式は未確認）"
        if self.marked:
            head = {PASS: "終売・今だけ可", NO_GO: "🔴終売・今だけ不可"}.get(self.verdict, "終売・判定待ち")
        else:
            head = "🔴終売" if self.verdict == NO_GO else "終売疑い"
        return f"【{head}】" + " ／ ".join(self.reasons)


# 出品（ASIN）単位で起きる兆候。同じ JAN の別 ASIN が売れていれば「その出品が死んだ」だけで、
# 商品の終売ではない（2026-10-11：SD の ドライニング 10個セット等、何年も前に止まったセット出品が
# 「終売疑い」に16件並んだ。単品は月11個売れている）。
LISTING_LEVEL = ("no_new_offer", "rank_gone", "rank_stale")


def check(product: dict | None, amazon_title: str | None, wholesale_title: str | None = "",
          wholesale_note: str | None = "", now_unix: int | None = None,
          family_alive: bool = False, now_only: NowOnly | None = None) -> Discontinued:
    """§3.5 #12 の機械の前段。NO-GO / UNKNOWN / PASS を返す。

    `family_alive` … 同じ JAN にぶら下がる別の ASIN が直近60日にランクを持っている
    （＝商品そのものは売れている）。True なら出品単位の兆候（LISTING_LEVEL）を終売の根拠にしない。
    `now_only` … 終売の印が付いたときの「今だけ」3条件の材料。渡さなければ UNKNOWN（未確認）。
    **終売の印だけでは NO-GO にしない**（2026-10-12 社長方針）。
    """
    reasons: list[str] = []
    verdict = PASS

    hit = classify(amazon_title, wholesale_title)
    if hit:
        reasons.append("分類ルール：" + hit.text())

    sup = SUPPLIER_END_RE.search(_norm(f"{wholesale_title or ''} {wholesale_note or ''}"))
    if sup:
        reasons.append(f"仕入れ先の記載に「{sup.group(0)}」（卸自身が終わりを書いている＝リピート不可）")

    marked = bool(hit or sup)
    if marked:
        # 法令品目は製造終了日まで、卸の廃番は終了日なし（＝仮置きの月数）で売り切れるかを見る
        ends = (hit.ends or hit.rule.ends) if (hit and not sup) else None
        verdict, why = now_only_verdict(now_only, ends)
        reasons.append(why)

    sg = signs(product or {}, now_unix)
    if family_alive:
        dead = [x for x in sg if x.key in LISTING_LEVEL]
        sg = [x for x in sg if x.key not in LISTING_LEVEL]
        if dead:
            reasons.append("出品単位の停止（" + "・".join(x.text for x in dead)
                           + "）。同じ JAN の別 ASIN は販売中なので終売の兆候とはみなさない")
    am = AMAZON_END_RE.search(_norm(amazon_title))
    if am:
        sg.append(Sign("title_word", True, f"Amazon の商品名に「{am.group(0)}」"))
    strong = [s for s in sg if s.strong]
    if strong or len(sg) >= 2:
        reasons.append("兆候：" + "・".join(s.text for s in sg)
                       + "（人がメーカー公式の製品DBで現行品か確認）")
        if verdict == PASS:
            verdict = UNKNOWN
    elif sg:
        reasons.append("弱い兆候（単独では落とさない）：" + sg[0].text)
    return Discontinued(verdict, hit, reasons, marked)
