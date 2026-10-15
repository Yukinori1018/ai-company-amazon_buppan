"""人が実画面で見た結果（カート保持者・新品の出品可否・キーゾン実売）を判定に合流させる。

なぜ別モジュールか（2026-10-11 タカシ）
--------------------------------------
これまでは人の確認を台帳のセルに直接書き、`確認者` に「カズヨ」が入った行は機械が以後
一切触らない（凍結）運用だった。これだと

  - SD の卸価格が後から入っても、カートだけ人が見た行は採算が引き直されない
  - 人の確認の根拠がシートのセルにしか残らず、どの画面をいつ見たかが追えない

ので、**人の確認はファイル（agent_output の CSV ＝証跡）に置き、台帳を引き直すたびに
機械判定へ上書き合流する**形にした。台帳は「機械判定 × 人の確認」の投影であり、
ここに載っている ASIN は `ledger_refresh` が凍結せずに毎回引き直す（人の値は毎回同じに戻る）。

入力（すべて人が見たもの。機械の推定は入れない）
  - ledger20261010/cart_check_*.csv     カズヨ Chrome 実画面：カートの販売元・カート価格・過去1か月表示
  - ledger20261010/gate_check_*.csv     カズヨ セラセン実画面：restrictions/approve?itemcondition=New
  - ledger20261010/cart_maker_flags_*.csv  カートがメーカー/ブランド本人（確定・疑い）
  - シートのタブ「実売とゲート_20261005」  カズヨ キーゾン実画面（ASIN 単位・3か月）

判定のしかた（CLAUDE.md §3.3 / §3.5）
  #5  カート：Amazon.co.jp → FAIL／メーカー本人（確定）→ FAIL／疑い → UNKNOWN／
      カートなし・高値で非表示 → UNKNOWN（誰も持っていない＝相場に戻せば取れる可能性）／それ以外 PASS
  #1-2 ゲート：最新の確認日の結果を採る（ブランド申請の前後で変わる・§3.3-25）
  #9  実売：キーゾンがある ASIN はキーゾンだけで決める（兄弟の値は流用しない・§3.3-29）。
      キーゾン再現値（kz_estimate）も同等に扱う。人のキーゾン画面の値（表示なし含む）が勝つ。
      無ければ、Keepa の monthlySold があり実画面の「過去1か月」表示と一致すれば PASS。
      それ以外は UNKNOWN「キーゾン未確認」
  #10 取り分＝月販 ÷（カート対象の FBA ＋ カート対象の自己発送 ＋ 1）。3個/月未満は FAIL。
      在庫月数＝推奨初回点数 ÷ 取り分。6か月超は FAIL
"""
from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
WORK = REPO / "workspace/output/agent_output/T-20260920-003"
OUT = WORK / "ledger20261010"
KEIZON_TAB = "実売とゲート_20261005"
MIN_SHARE = 3          # §3.5 #10 取り分の下限（個/月）
MAX_MONTHS = 6         # §3.5 #10 在庫月数の上限
TARGET_MONTHS = 3      # 3か月を超えるのはロット・ゲート10点が理由のときだけ

#: Keepa 生データ（buyBoxEligibleOfferCounts を読むため）。後ろほど新しい
RAW_FILES = [WORK / "refetch20261004/raw.jsonl",
             WORK / "buylist20261009/resolve_raw.jsonl",
             WORK / "buylist20261009/buybox_raw.jsonl",
             OUT / "keepa_kz_hist_20261011.jsonl",      # 2026-10-11 キーゾン再現用の取得
             OUT / "keepa_unknown_20261011.jsonl",      # 2026-10-11 実売 UNKNOWN の取り直し
             WORK / "kz_entry/keepa_full.jsonl"]        # 2026-10-11 kz 入口（buybox=1）
#: 2026-10-12 UNKNOWN の段階解消（unknown_stages.py）の取り直し。後ろほど新しい＝後勝ち
RAW_FILES += sorted((WORK / "unknown_queue").glob("keepa_stage_*.jsonl"))


@dataclass
class Cart:
    holder: str
    price: str
    sold_label: str        # 実画面の「過去1か月で◯点以上購入」の◯+（空＝表示なし）
    checked_at: str
    maker: str = ""        # "確定" / "疑い" / ""
    maker_note: str = ""
    has_cart: bool | None = None   # 実画面で「カートあり=Y」。保持者名は未取得のことがある
    holder_src: str = "人"         # "人"（実画面で読んだ）／"Keepa"（Y だが名前は Keepa で補った）
    #: キーゾンの「アマゾン直販」（§3.5 #6 補助・2026-10-12）。単独では落とさないが判定理由に書く
    amazon_direct: str = ""
    #: 出品一覧の実画面（§3.5 #7・2026-10-15）。新品の件数と本体の有無（browser_results の #7）
    offers_new: int | None = None
    amazon_on_listing: str = ""     # "なし" / "あり" / ""（未確認）


@dataclass
class Keizon:
    label: str             # 例 "9/13/12（平均11個）"・"表示なし"
    avg: float | None
    months: list[str] = field(default_factory=list)
    checked: str = ""


@dataclass
class ScreenChecks:
    cart: dict[str, Cart]
    gate: dict[str, dict]
    keizon: dict[str, Keizon]
    season: dict[str, dict] = field(default_factory=dict)   # 人が12か月ランクを見た季節判定
    ip: dict[str, dict] = field(default_factory=dict)       # 人が見た §3.5 #8 知財のサイン

    def covers(self, asin: str) -> bool:
        """人の確認の証跡があるか（凍結解除の判定に使う）。キーゾン再現値（機械）は数えない。"""
        k = self.keizon.get(asin)
        return (asin in self.cart or asin in self.gate or asin in self.season or asin in self.ip
                or bool(k and not k.checked.startswith("Keepa")))

    def has_any(self, asin: str) -> bool:
        """人の確認 or キーゾン再現値のどれかがあるか（判定に合流させるかの判定）。"""
        return self.covers(asin) or asin in self.keizon


def _num(x) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(x or "").replace(",", ""))
    return float(m.group()) if m else None


def load_cart() -> dict[str, Cart]:
    flags = {}
    for p in sorted(OUT.glob("cart_maker_flags_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            flags[r["ASIN"]] = (r["区分"], r["根拠"])
    out = {}
    for p in sorted(OUT.glob("cart_check_*.csv")):          # 名前順＝日付順。後の確認が勝つ
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            a = r["ASIN"].strip()
            holder = (r.get("カート保持者(実画面)") or "").strip()
            yn = (r.get("カートあり") or "").strip().upper()
            if yn == "N" and not holder:
                holder = "カートなし"
            sold = (r.get("過去1か月(実画面)") or r.get("過去1か月(実画面・下限)") or "").strip()
            c = Cart(holder, (r.get("カート価格") or "").strip(), sold, r.get("確認時刻", ""),
                     has_cart=(True if yn == "Y" else False if yn == "N" else None),
                     amazon_direct=(r.get("アマゾン直販(キーゾン)") or "").strip())
            n_new = (r.get("新品出品者数(出品一覧)") or "").strip()
            c.offers_new = int(n_new) if n_new.isdigit() else None
            c.amazon_on_listing = (r.get("Amazon本体(出品一覧)") or "").strip()
            if "疑い" in (r.get("注意") or ""):
                c.maker, c.maker_note = "疑い", r["注意"]
            if a in flags:
                c.maker, c.maker_note = flags[a]
            out[a] = c
    return out


def load_gate(fallback: dict[str, dict]) -> dict[str, dict]:
    """{ASIN: {"ゲート判定": OK/NG, "根拠", "確認日", "確認者"}}。新しい確認が勝つ。"""
    out = dict(fallback)
    for p in sorted(OUT.glob("gate_check_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            ok = r["新品の出品可否"].strip().upper().startswith("OK")
            out[r["ASIN"].strip()] = {
                "ゲート判定": "OK" if ok else "NG",
                "根拠": (("新品可（その他の商品なし）"
                          + ("・ブランド出品許可が必要＝書類申請（請求書10点）" if "書類" in r["新品の出品可否"] else ""))
                         if ok else r["新品の出品可否"]),
                "確認日": (r.get("確認時刻") or "")[:10],
                "確認者": r.get("確認者") or "",
                "人": True,
                # 「OK(書類申請…)」＝新品の申請経路はあるがブランド出品許可が要る（請求書10点）
                "書類": ok and "書類" in r["新品の出品可否"],
            }
    return out


def load_keizon(sheet) -> dict[str, Keizon]:
    try:
        vals = sheet.worksheet(KEIZON_TAB).get_all_values()
    except Exception:
        return {}
    h = vals[0]
    out = {}
    for row in vals[1:]:
        r = dict(zip(h, row))
        lab = r.get("キーゾン実売（ASIN単位）", "")
        m = re.match(r"\s*(\d+)/(\d+)/(\d+)", lab)
        out[r["ASIN"]] = Keizon(lab, _num(r.get("平均月販")) if m else None,
                                list(m.groups()) if m else [], r.get("確認者", ""))
    return out


def load_kz_estimate() -> dict[str, Keizon]:
    """キーゾン再現値（kz_estimate_*.csv）。CLAUDE.md §3.3-16（9c673a11）でキーゾン実数と同等に扱う。
    式＝30日窓ごとにランクが直前観測より3%超改善した回数（キーゾン実画面75点中69点が完全一致）。
    人がキーゾン画面で見た値（シートのタブ）があればそちらが勝つ（load() で上書き）。"""
    out = {}
    for p in sorted(OUT.glob("kz_estimate_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            if (r.get("3か月平均") or "") == "":
                continue
            m = [r["推定m1"], r["推定m2"], r["推定m3"]]
            note = (r.get("注意") or "").strip()
            lab = f"{'/'.join(m)}（平均{r['3か月平均']}個）"
            out[r["ASIN"].strip()] = Keizon(
                lab, float(r["3か月平均"]), m,
                "Keepa ランク改善3%超で再現（キーゾン同等・§3.3-16）" + (f"・注意：{note}" if note else ""))
    return out


def load_season() -> dict[str, dict]:
    """ledger20261010/season_check_*.csv（人が Keepa の12か月ランクを目視した季節判定）。
    列：ASIN, 季節の窓(PASS/FAIL/UNKNOWN), 根拠, 追記（判定理由に足す注意）, 確認時刻, 確認者"""
    out = {}
    for p in sorted(OUT.glob("season_check_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[r["ASIN"].strip()] = {k: (v or "").strip() for k, v in r.items()}
    return out


def load_legal() -> dict[str, tuple[str, str]]:
    """法務判定で販売を止める行（{ASIN: (区分, 判定理由に書く文)}）。"""
    out = {}
    for p in sorted(OUT.glob("legal_flags_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[r["ASIN"].strip()] = (r["区分"].strip(), r["判定理由に書く文"].strip())
    return out


#: 法務46（電気用品・危険物）。GO 行に「発注前に書類を取り寄せる」を足すための語。
#: 🔴 ふるい落とし・並べ替えには使わない（§3.3-20：語で判定しない）。注記だけに使う
PSE_WORDS = ("蛍光灯", "蛍光ランプ", "ランプ", "ヘアアイロン", "ケーブル", "ブロワ", "ACアダプタ")
SDS_WORDS = ("スプレー", "エアゾール", "ミスト", "洗剤", "消臭", "芳香", "クリーナー", "電池", "霧")


def doc_note(name: str) -> str:
    need = []
    if any(w in name for w in PSE_WORDS):
        need.append("PSE 書類")
    if any(w in name for w in SDS_WORDS):
        need.append("SDS")
    if not need:
        return ""
    return f"発注前にメーカーから {'／'.join(need)} を取り寄せ（Amazon の審査用・法務46）"


def load_keizon_screen() -> dict[str, Keizon]:
    """ledger20261010/kz_screen_*.csv（カズヨがキーゾンを実画面で見た3か月の実数・2026-10-11 夜〜）。

    シートのタブ（KEIZON_TAB）と同じく人の観測。証跡をファイルに置く形に揃えた。
    🔴 月の列が空の行（キーゾンの販売数表が出なかった）は**載せない**＝未確認のまま。
       「表が出ない」は「0個」とも「表示なし」とも区別できないので、0 と書かない。
    平均はキーゾン画面の「平均月間」の表示値をそのまま使う（3か月合計÷3 に直さない）。"""
    out = {}
    for p in sorted(OUT.glob("kz_screen_*.csv")):           # 名前順。後のファイルが勝つ
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            m = [(r.get(c) or "").strip() for c in ("キーゾン過去1ヶ月目", "過去2ヶ月目", "過去3ヶ月目")]
            avg = _num(r.get("平均月間"))
            if not all(x != "" for x in m) or avg is None:
                continue
            out[r["ASIN"].strip()] = Keizon(
                f"{'/'.join(m)}（平均{avg:g}個）", avg, m,
                f"{(r.get('確認者') or '').strip()} {(r.get('確認時刻') or '').strip()}".strip())
    return out


def load_offer_checks() -> dict[str, tuple[int, int, str]]:
    """ledger20261010/offer_check_*.csv（出品一覧の実画面で数えたカート対象の競合）。

    列：ASIN, カート対象FBA, 即納の自己発送, 取り寄せ型, 内訳, 確認時刻, 確認者
    §3.5 #10 の分母は「FBA ＋ 即納の自己発送 ＋ 1」。取り寄せ型は数えない。
    ここに載った ASIN は Keepa の buyBoxEligibleOfferCounts より優先する（§3.5 #7＝画面実数が正）。"""
    out = {}
    for p in sorted(OUT.glob("offer_check_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[r["ASIN"].strip()] = (int(r["カート対象FBA"]), int(r["即納の自己発送"]),
                                      f"実画面 {r.get('確認者', '').strip()} {r.get('確認時刻', '').strip()}"
                                      f"・{r.get('内訳', '').strip()}")
    return out


def backorder_only(asin: str) -> str:
    """出品一覧の実画面で、即納の出品（FBA・即納の自己発送）が0本で取り寄せ型しか無いなら理由を返す。

    §3.5 #13「資格なし・取り寄せ型の価格しかない」＝落とす条件。Keepa の90日中央値は
    その取り寄せ型の出品者が付けた値で、即納で売れる相場の根拠にならない（2026-10-11 夜 B008FIN7NQ）。"""
    for p in sorted(OUT.glob("offer_check_*.csv"), reverse=True):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            if r["ASIN"].strip() != asin:
                continue
            if int(r["カート対象FBA"]) == 0 and int(r["即納の自己発送"]) == 0 \
                    and int(r.get("取り寄せ型") or 0) > 0:
                return (f"即納の出品が0本・取り寄せ型 {r['取り寄せ型']}本だけ（{r.get('内訳', '').strip()}・"
                        f"{r.get('確認者', '').strip()} {r.get('確認時刻', '').strip()}）＝売価の根拠が"
                        "取り寄せ型の出品者の値付けしかない")
            return ""
    return ""


def load_ip_checks() -> dict[str, dict]:
    """ledger20261010/ip_check_*.csv（§3.5 #8 知財申立てのサインを人が実画面で見た結果・2026-10-15〜）。

    列：ASIN, 知財のサイン(PASS/FAIL/UNKNOWN), 根拠, 確認時刻, 確認者。名前順＝日付順・後勝ち。
    例：出品一覧に「【公式】<ブランド>」が出品している＝ブランド公式が売っている棚（§3.3-5）＝FAIL"""
    out = {}
    for p in sorted(OUT.glob("ip_check_*.csv")):
        for r in csv.DictReader(p.open(encoding="utf-8-sig")):
            out[r["ASIN"].strip()] = {k: (v or "").strip() for k, v in r.items()}
    return out


def merge_keizon(est: dict[str, Keizon], human: dict[str, Keizon]) -> dict[str, Keizon]:
    """人がキーゾン画面で見た値が常に勝つ（「表示なし」も人の観測なので残す）。

    2026-10-11 に「人の表示なし → 再現値で埋める」を試したが、人の行（確認者=カズヨ）の
    キーゾン列を機械値で上書きすることになるため撤回（秘書指示「人の行は上書きしない」）。
    表示なしの行を再現値で解くなら、人がキーゾン画面を見直してタブを更新する。"""
    out = dict(est)
    out.update(human)
    return out


def load(sheet, gate_fallback: dict[str, dict]) -> ScreenChecks:
    kz = merge_keizon(load_kz_estimate(), {**load_keizon(sheet), **load_keizon_screen()})
    return ScreenChecks(load_cart(), load_gate(gate_fallback), kz, load_season(), load_ip_checks())


_OFFERS: dict[str, tuple[int, int, str]] | None = None


def offers(asin: str) -> tuple[int, int, str] | None:
    """(カート対象 FBA 数, カート対象 自己発送数, 取得元)。Keepa buyBoxEligibleOfferCounts。"""
    global _OFFERS
    human = load_offer_checks()
    if asin in human:
        return human[asin]
    if _OFFERS is None:
        _OFFERS = {}
        for f in RAW_FILES:
            if not f.exists():
                continue
            for line in f.open():
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                p = o.get("product") or {}
                bb = p.get("buyBoxEligibleOfferCounts")
                if o.get("asin") and bb and len(bb) >= 2:
                    _OFFERS[o["asin"]] = (max(bb[0], 0), max(bb[1], 0), f"Keepa {f.parent.name}")
    return _OFFERS.get(asin)


AMAZON_JP = "AN1VRQENFRJN5"
_STRIP = re.compile(r"株式会社|有限会社|合同会社|\(株\)|（株）|㈱|公式|オフィシャル|ストア|ショップ|"
                    r"store|shop|official|online|japan|jp|[\s・\-_（）()【】\[\]　]", re.I)


def _norm(x: str) -> str:
    return _STRIP.sub("", (x or "").lower())


def maker_suspect(seller: str, brand: str, maker: str) -> str:
    """出品者名にブランド名・メーカー名が含まれていれば理由を返す（疑い止まり。確定は人）。"""
    sn = _norm(seller)
    for label, w in (("ブランド", brand), ("メーカー", maker)):
        wn = _norm(w)
        if len(wn) >= 2 and len(sn) >= 2 and (wn in sn or sn in wn):
            return f"出品者名「{seller}」が{label}「{w}」と一致（Keepa 機械判定）"
    return ""


def supplement_holder(c: Cart, sid: str | None, name: str | None, brand: str = "",
                      maker: str = "") -> Cart:
    """実画面でカートあり（名前未取得）の行に、Keepa の buyBoxSellerId で保持者名を補う。"""
    from dataclasses import replace
    if c.holder or not c.has_cart or not sid or sid == "-1":
        return c
    if sid == AMAZON_JP:
        return replace(c, holder="Amazon.co.jp（Keepa buyBoxSellerId）", holder_src="Keepa")
    nm = name or sid
    sus = "" if c.maker else maker_suspect(nm, brand, maker)
    return replace(c, holder=f"{nm}（{sid}）", holder_src="Keepa",
                   maker=c.maker or ("疑い" if sus else ""), maker_note=c.maker_note or sus)


# ── 各項目 ────────────────────────────────────────────────────────────

def cart_gate(c: Cart) -> tuple[str, str]:
    """(状態, 理由)。§3.3-1・§3.3-5。キーゾンのアマゾン直販（#6 補助）が在庫ありなら理由に足す。"""
    st, why = _cart_gate(c)
    if c.amazon_direct and "在庫あり" in c.amazon_direct:
        why += ("。🔴 #6 キーゾンのアマゾン直販が在庫あり（Amazon 本体が出品中＝カートを取り返される"
                "おそれ。§3.5 #6 は補助情報で単独では落とさない）")
    return st, why


def _cart_gate(c: Cart) -> tuple[str, str]:
    h = c.holder
    if "Amazon.co.jp" in h:
        src = ("Keepa buyBoxSellerId・カートの有無はカズヨ実画面" if c.holder_src == "Keepa"
               else "カズヨ実画面")
        return "FAIL", f"カートは Amazon.co.jp（{src} {c.checked_at}）"
    if c.maker == "確定":
        return "FAIL", f"カートはメーカー/ブランド本人：{h}（{c.maker_note}）"
    if c.maker == "疑い":
        return "UNKNOWN", f"カート {h} はメーカー/ブランド本人の疑い（{c.maker_note}）"
    if not h and c.has_cart:
        return "UNKNOWN", (f"カートあり（カズヨ実画面 {c.checked_at}・{c.price}円）だが保持者名は未取得"
                           "（Keepa にも buyBoxSellerId が無い）")
    if c.holder_src == "Keepa" and c.maker != "確定":
        if c.maker == "疑い":
            return "UNKNOWN", f"カート {h} はメーカー/ブランド本人の疑い（{c.maker_note}）"
        return "PASS", (f"カートは第三者 {h}（カートの有無と価格 {c.price}円はカズヨ実画面 "
                        f"{c.checked_at}・保持者名は Keepa buyBoxSellerId）")
    # 🔴 2026-10-11 夜：保持者欄が「カートなし(一般的な価格より高いため非表示)」のように注記つきだと
    #    完全一致に当たらず「第三者がカート」で PASS していた（B0C8HD3F37 が GO に化けた）。
    #    カートあり=N か、欄が「カートなし」「高値」「非表示」を含めば UNKNOWN にする
    if (c.has_cart is False or not h or h.startswith("カートなし")
            or "高値" in h or "非表示" in h):
        return "UNKNOWN", (f"カートなし（{h or '表示なし'}・カズヨ実画面 {c.checked_at}）"
                           "＝誰もカートを持っていない。売価を相場に戻せば取れる可能性")
    # 2026-10-15：価格を読まずに保持者だけ見た確認（browser_results）では「（円・」と出ていた
    price = f"{c.price}円・" if c.price else ""
    return "PASS", f"カートは第三者 {h}（{price}カズヨ実画面 {c.checked_at}）"


def sales(asin: str, s: dict, machine_st: str, sc: ScreenChecks) -> tuple[str, str, float | None]:
    """(状態, 理由, 月販)。キーゾンが最優先・無ければ Keepa monthlySold ＋実画面表示の一致。"""
    k = sc.keizon.get(asin)
    if k:
        if k.avg is None:
            return "UNKNOWN", f"キーゾン表示なし（{k.checked}）＝この ASIN の実数が取れない", None
        # 観測少で0：キーゾン自身も同じ Keepa データから0を出す＝人が画面で見ても「3か月0個」で落とす。
        # §3.3-16（9c673a11）で再現値はキーゾン実数と同等なので FAIL に揃える（注意は理由に残す）
        if k.avg <= 0:
            return "FAIL", f"キーゾン3か月 {k.label}＝実質ゼロ（{k.checked}）", 0
        return "PASS", f"キーゾン3か月 {k.label}（ASIN 単位・{k.checked}）", k.avg
    ms = s.get("monthlySold")
    c = sc.cart.get(asin)
    shown = _num(c.sold_label) if c else None
    if machine_st == "PASS" and ms:
        if c is None:
            return "PASS", f"Keepa 過去1か月 {ms}個（実画面未確認）", float(ms)
        if not shown:
            return ("UNKNOWN", f"Keepa は月{ms}個だが実画面に販売数表示なし（2根拠がずれる・"
                    "キーゾン未確認）", None)
        lo, hi = sorted((float(ms), shown))
        if hi >= 2 * lo:
            return ("UNKNOWN", f"Keepa 月{ms}個と実画面 {c.sold_label} が2倍以上ずれる（キーゾン未確認）",
                    None)
        return "PASS", f"実画面 過去1か月 {c.sold_label}（Keepa {ms}個と一致）", min(float(ms), shown)
    if not ms and shown and shown >= 50:
        # 実画面の「過去1か月で◯点以上購入」は Amazon が出している ASIN 単位の実数（下限値）。
        # 人が画面で見た実数なので §3.3-16 を満たす。Keepa の monthlySold は未反映なだけ。
        return ("PASS", f"実画面 過去1か月 {c.sold_label}（Amazon 表示・下限値・カズヨ {c.checked_at}。"
                        "Keepa monthlySold は未反映）", shown)
    return "UNKNOWN", "キーゾン未確認（月販表示なし＝月50個未満。ASIN 単位の実数が無い）", None


def share_gate(asin: str, monthly: float, qty: int | None, min_lot: float | None,
               gated_needs_10: bool) -> tuple[str, str, dict]:
    """§3.5 #10。(状態, 理由, 付帯情報)。"""
    off = offers(asin)
    if not off:
        return "UNKNOWN", "出品者の内訳が取れない（Keepa 生データなし）", {}
    fba, fbm, src = off
    share = monthly / (fba + fbm + 1)
    info = {"fba": fba, "fbm": fbm, "share": share, "src": src, "human": src.startswith("実画面")}
    brk = f"カート対象 FBA {fba}・自己発送 {fbm}（{src}）"
    if share < MIN_SHARE:
        need = math.ceil(MIN_SHARE * (fba + fbm + 1))
        rivals_ok = int(monthly // MIN_SHARE) - 1        # 取り分3個を満たす競合数の上限
        fix = f"月販が {need}個以上になる月なら可（キーゾンで毎月の実数を見て再判定）"
        if rivals_ok >= 0 and rivals_ok < fba + fbm:
            fix += (f"／出品一覧の画面実数で、カート対象の競合が {rivals_ok}社以下なら可"
                    f"（{src} では {fba + fbm}社）")
        elif rivals_ok < 0:
            fix += f"／月販 {monthly:g}個では競合ゼロでも3個に届かない"
        return ("FAIL", f"取り分 {share:.1f}個/月（基準3個）＝月販 {monthly:g}÷({fba}+{fbm}+1)。{brk}",
                {**info, "fix": fix})
    floor = max(int(min_lot or 1), 10 if gated_needs_10 else 1)
    # 2026-10-12：採算の点数（qty）が書類申請の10点や最小ロットより少ないと、そのまま推奨に
    # なっていた（不二貿易 B0C5WXSTKF：卸ロット6点・ブランド申請で10点要るのに推奨6点）。下限を当てる
    rec = max(qty or floor, floor)
    if rec / share > TARGET_MONTHS:
        rec = max(floor, math.floor(share * TARGET_MONTHS))
    months = rec / share
    info.update(rec=rec, months=months, floor=floor)
    if months > MAX_MONTHS:
        return ("FAIL", f"最小ロット {floor}点で在庫 {months:.1f}か月（上限6か月）。取り分 {share:.1f}個/月",
                {**info, "fix": f"最小ロットが {math.floor(share * MAX_MONTHS)}点以下の仕入れ先なら可"})
    why = f"取り分 {share:.1f}個/月・推奨初回 {rec}点で在庫 {months:.1f}か月。{brk}"
    if months > TARGET_MONTHS:
        why += f"（3か月超は最小ロット {floor}点のため）"
    return "PASS", why, info
