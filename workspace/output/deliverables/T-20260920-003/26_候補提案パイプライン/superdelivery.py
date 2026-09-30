#!/usr/bin/env python3
"""スーパーデリバリー（SD）アダプタ — Buyer API が無い卸を「読める形」にする。

なぜ SD を足したか（2026-09-30 カズヨの申し送り）
------------------------------------------------
NETSEA だけを突合先にしていたのは **道具の都合**でした（Buyer API があるから機械で読める）。
SD は API が無いだけで、当社は既に利用開始済み・一部の出展企業からは卸価格の承認も得ています。
**「API があるか」で探索範囲を決めると、事業の範囲が道具に従属します。**

この2つが SD で分かったこと（2026-09-30 実測）
--------------------------------------------
🔴 **1. JAN では検索できません。**`?word=<JAN>` は実在する JAN でも0件です（対照として
   無意味語も0件。件数が動く語では正しく動くので、検索そのものは効いています）。
   ＝ **JAN → SD の直行便はありません。**当てる順は「メーカー品番 → ブランド＋語 → 商品名」で、
   **開いた商品ページに載っている JAN で一致を確認する**、という遠回りになります。

🟢 **2. 商品ページには、卸価格以外のほぼ全部が非ログインで載っています。**
   JAN・メーカー品番・SD品番・入り数（1セット◯点）・上代・出展企業名・
   そして **販売規制（消費者への直送／ネット販売／仕入れ前の販売／画像転載）**。
   ＝ **卸価格だけがログイン＋出展企業ごとの承認待ち**です。

だから設計はこうなります
----------------------
| 段 | 誰がやるか | 取れるもの |
|---|---|---|
| 検索（`?word=`） | この module（非ログイン・2秒間隔・件数上限つき） | 出展企業名・商品名・商品ページURL |
| 商品ページ | この module（同上） | JAN・品番・入り数・上代・販売規制 |
| **卸価格** | **呼び出し側（カズヨのブラウザ）** | `merge_wholesale()` に渡せば行が埋まります |

**社長にブラウザ操作を頼む設計にはしていません**（CLAUDE.md 鉄則9）。
ログインが要るのは卸価格の1項目だけで、それはカズヨが自分のブラウザで見て
`sd_wholesale.json` に置けば済みます（形式は `merge_wholesale` の docstring）。

⛔ やらないこと
-------------
- **卸価格の「承認申請」は絶対に実行しません。**申請は出展企業への連絡＝CLAUDE.md §4.1。
  この module は `approval_requests()` で**申請したい企業の一覧を作るところまで**です。
- 画像は1枚も取りません（SD は「購入前の画像転載禁止」）。
- 取得の規模は**人が手で見る範囲**（2秒間隔・1回の上限つき）に留めます。
  robots.txt は `/p/do/psl/?word=` を許可、`/p/r/pd_p/` に禁止指定はなく、規約に自動取得の
  明示禁止もありません（法務ハルオ 2026-09-14 判定）。**これより広く回すなら再判定が必要です。**

公開の注意: 卸価格・卸サイトの商品URL は**戻り値と `agent_output/` にだけ**入ります。
リポ内の成果物には書きません（このリポは PUBLIC。`source-terms-guard` が止めます）。
"""

from __future__ import annotations

import html as htmllib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

BASE = "https://www.superdelivery.com"

# 人が手で見る範囲を超えないための2本の線。呼び出し側から上げられますが、既定は動かしません。
SLEEP_SEC = 2.0
DEFAULT_FETCH_CAP = 60

UA = {"User-Agent": "Mozilla/5.0 (T-20260920-003 manual-scale lookup)"}

JAN_RE = re.compile(r"^\d{12,13}$")


# ── 値オブジェクト ──────────────────────────────────────────────────────────


@dataclass
class SDSupplier:
    """出展企業。**社名は「購入元の名前」欄までの用途**に留めます（名簿化して外部連絡はしない）。"""

    supplier_id: str
    name: str


@dataclass
class SDSet:
    """SD の1行＝「規格（セット）」。NETSEA の `set[]` と同じ粒度です。

    `wholesale_price_excl` は**非ログインでは必ず None**です（「卸価格は会員のみ公開」）。
    None を 0 や「無し」に畳まないこと。**UNKNOWN であって NO-GO ではありません。**
    """

    sd_code: str                      # SD品番（例 13681795S1）。この module の一意キー
    product_id: str                   # 商品ページの ID（13681795）
    name: str = ""
    maker_code: str = ""              # メーカー品番
    jan: str = ""
    units_per_set: int | None = None  # 1セット◯点。**原価の倍率に効くので推測しない**
    retail_excl: int | None = None    # 上代（税抜）
    wholesale_price_excl: int | None = None   # 卸価格（ログイン＋承認後のみ）
    approval: str = "未確認"          # 承認済み / 卸価格未承認 / 未確認
    stock: str = "未確認"
    supplier: SDSupplier | None = None
    net_sales_ok: str = "未確認"      # ネット販売（○/×/未確認）
    direct_ship_ok: str = "未確認"    # 消費者への直送（○/×/未確認）
    url: str = ""                     # 商品ページ URL（**リポには書かない**）
    notes: list[str] = field(default_factory=list)


# ── URL の組み立て ─────────────────────────────────────────────────────────


def search_url(word: str, supplier_id: str | None = None) -> str:
    """検索 URL。`?word=` は robots.txt で許可されている唯一の検索経路です。

    `as=` `br=` `ed=` `so=pricedown` `exw=` の組み合わせは Disallow なので**付けません**。
    """
    q = urllib.parse.quote(word)
    if supplier_id:
        return f"{BASE}/p/do/dpsl/{supplier_id}/?word={q}"
    return f"{BASE}/p/do/psl/?word={q}"


def product_url(product_id: str) -> str:
    """商品ページ。`sd_code` に `S1` のような枝番が付いていても商品 ID は数字部分だけ。"""
    return f"{BASE}/p/r/pd_p/{str(product_id).split('S')[0]}/"


# ── HTML → 値（純関数。ネットワークに触りません＝テストできます）────────────


def _text(fragment: str) -> str:
    """タグを落として空白を畳む。HTML 実体参照（`&yen;` `&amp;`）も戻します。"""
    s = re.sub(r"<script.*?</script>|<style.*?</style>", " ", fragment, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _int(s: str | None) -> int | None:
    if not s:
        return None
    digits = re.sub(r"[^\d]", "", unicodedata.normalize("NFKC", str(s)))
    return int(digits) if digits else None


def parse_search(html: str) -> tuple[list[SDSupplier], list[str], int | None]:
    """検索結果 → (出展企業, 商品ページID, 全社数)。

    SD の検索結果は既定で「企業ごと表示」で、1社の下に数件の商品がぶら下がります。
    **「全N社」は社数であって商品数ではありません。**0件のときは
    「該当する商品はございませんでした」が出て、社も商品も返りません。
    """
    if "ございませんでした" in _text(html):
        return [], [], 0
    suppliers: list[SDSupplier] = []
    seen: set[str] = set()
    # 企業名は企業内検索リンク `/p/do/dpsl/<id>/` のアンカーテキスト。
    for sid, label in re.findall(r'href="/p/do/dpsl/(\d+)/"[^>]*>(.*?)</a>', html, re.S):
        name = _text(label)
        # 「（すべてのジャンル）」等のジャンルリンクや空アンカーは企業名ではない
        if not name or "すべてのジャンル" in name or sid in seen:
            continue
        seen.add(sid)
        suppliers.append(SDSupplier(sid, name))
    product_ids = list(dict.fromkeys(re.findall(r"/p/r/pd_p/(\d+)/", html)))
    m = re.search(r"全\s*([\d,]+)\s*社", _text(html))
    return suppliers, product_ids, _int(m.group(1)) if m else None


def _parse_restrictions(html: str) -> dict[str, str]:
    """販売規制の表（消費者への直送／ネット販売／…）を読む。非ログインでも出ています。"""
    out: dict[str, str] = {}
    for th, td in re.findall(r"<th>([^<]+)</th>\s*<td[^>]*>(.*?)</td>", html, re.S):
        out[_text(th)] = _text(td)
    return out


def parse_product(html: str, url: str = "", logged_in: bool = False) -> list[SDSet]:
    """商品ページ → 規格（セット）ごとの行。

    **卸価格は非ログインでは取れません**（「会員のみ公開」）。その場合 `approval='未確認'` で返し、
    `wholesale_price_excl` は None のままにします。ログイン済みの HTML を渡せば、
    同じ関数が金額を読んで `approval='承認済み'` にします。

    `logged_in` を呼び出し側が宣言するのは、**「金額が無い」の意味が文脈で変わる**からです。

    | 文脈 | 金額が無い | 意味 |
    |---|---|---|
    | 非ログイン | 当たり前 | **未確認**（承認済みか未承認かは判らない） |
    | ログイン済み | 情報 | **卸価格未承認**（申請すれば見える） |

    ⚠️ 2026-09-30: `logged_in` を作る前は「会員のみ公開の文字が無ければ未承認」と読んでいて、
    **品切れ（SOLD OUT）の行10件を「卸価格未承認」と書いていました**。品切れの行では
    卸価格の欄に SOLD OUT が入るので「会員のみ公開」が出ません。
    **画面に出ていない理由を1つに決めつけると、未確認が未承認に化けます。**
    """
    product_id = (re.search(r"SD品番[：:]\s*(\d+)", _text(html)) or [None, ""])[1]
    sup = re.search(r'class="dl-name-txt"\s+href="/p/do/dpsl/(\d+)/"[^>]*>(.*?)</a>', html, re.S)
    supplier = SDSupplier(sup.group(1), _text(sup.group(2))) if sup else None

    r = _parse_restrictions(html)
    net_ok = r.get("ネット販売", "未確認") or "未確認"
    direct_ok = r.get("消費者への直送", "未確認") or "未確認"

    rows: list[SDSet] = []
    # 1行＝<tr> …ただし SD は行の末尾に別テーブルを入れ子にするので、SD品番で行を切ります。
    for block in re.split(r'<tr class="ts-tr02">', html)[1:]:
        tx = _text(block)
        code = (re.search(r"SD品番[：:]\s*([\dA-Za-z]+)", tx) or [None, ""])[1]
        if not code:
            continue
        jan = (re.search(r"JAN[：:]\s*(\d{12,13})", tx) or [None, ""])[1]
        maker = (re.search(r"メーカー品番[：:]\s*([^\s/]+)", tx) or [None, ""])[1]
        units = _int((re.search(r"1セット\s*\((\d+)\s*点\)", tx) or [None, None])[1])
        if units is None:
            # 「数量」列の「N点」。1セットの表記が無い（1点売り）ページ向けの控え。
            units = _int((re.search(r"(\d+)\s*点", tx) or [None, None])[1])
        retail = _int((re.search(r"¥\s*([\d,]+)\s*/\s*1点", tx) or [None, None])[1])
        # 名前は内訳セルの先頭。メーカー品番の括弧より前まで。
        name = _text((re.search(r'class="[^"]*td-set-detail[^"]*"[^>]*>(.*?)</td>',
                                block, re.S) or [None, ""])[1])
        name = re.split(r"[（(]", name)[0].strip()

        # 卸価格は「卸価格」列＝`class="stock-info"` のセルだけを見ます。
        # 行全体から `¥` を拾うと**上代（メーカー希望小売価格）を卸価格として読みます**。
        # 上代は卸価格より高いので、読み違えると「儲かる」方向に間違えます ── いちばん危ない向き。
        cell = _text((re.search(r'<td class="stock-info[^"]*"[^>]*>(.*?)</td>', block, re.S)
                      or [None, ""])[1])
        price = None
        approval = "未確認"
        notes: list[str] = []
        m = re.search(r"¥\s*([\d,]+)", cell)
        price = _int(m.group(1)) if m else None
        if price:
            approval = "承認済み"
        elif logged_in:
            # ログイン済みで金額が無い＝この企業の卸価格をまだ見せてもらえていない。
            approval = "卸価格未承認"
        else:
            # 非ログイン。**承認の有無はここでは判りません**（未承認と同じ表示になる）。
            notes.append("非ログイン取得のため卸価格は不明")
        stock = "在庫なし" if "SOLD OUT" in (cell or tx).upper() else "未確認"

        rows.append(SDSet(
            sd_code=code, product_id=product_id or code.split("S")[0], name=name,
            maker_code=maker, jan=jan, units_per_set=units, retail_excl=retail,
            wholesale_price_excl=price, approval=approval, stock=stock,
            supplier=supplier, net_sales_ok=net_ok, direct_ship_ok=direct_ok,
            url=url or product_url(product_id or ""), notes=notes,
        ))
    return rows


# ── 当て方（JAN では検索できないので順番が要る）────────────────────────────


def lookup_plan(jan: str = "", maker_code: str = "", brand: str = "",
                title: str = "") -> list[str]:
    """SD に投げる検索語を、**当たりやすい順**に並べる。

    JAN を入れないのは意地ではなく実測です（実在する JAN でも0件）。
    商品名の丸投げも効きません（SD 自身が「文章や長い文字列はキーワードに分けて」と案内している）。
    なので **型番 → ブランド＋名詞2語 → 名詞2語** の順にします。
    """
    plan: list[str] = []
    if maker_code:
        plan.append(maker_code.strip())
    words = _keywords(title)
    if brand and words:
        plan.append(f"{brand.strip()} {words[0]}")
    if brand:
        plan.append(brand.strip())
    # 語を減らしながら広げる。**広い語から始めると商品ページを開く枚数が無駄に増えます。**
    if len(words) >= 2:
        plan.append(" ".join(words[:2]))
    if words:
        plan.append(words[0])
    return [p for p in dict.fromkeys(plan) if p]


_NOISE = re.compile(
    r"^(?:\d+[点個枚袋本箱組セットpcs]*|約?\d+(?:\.\d+)?(?:mm|cm|ml|l|g|kg|粒|枚|入)"
    r"|【[^】]*】|日本製|送料無料|新品|正規品|まとめ買い|セット|×\d+)$", re.I)


def _keywords(title: str) -> list[str]:
    """商品名を検索語に割る。数量・サイズ・煽り文はキーワードにしない。"""
    t = unicodedata.normalize("NFKC", title or "")
    t = re.sub(r"【[^】]*】|\[[^\]]*\]|（[^）]*）|\([^)]*\)", " ", t)
    parts = [p for p in re.split(r"[\s/・,、_|＋+]+", t) if p]
    return [p for p in parts if len(p) >= 2 and not _NOISE.match(p)][:4]


# ── 取得（規模を自分で縛る）────────────────────────────────────────────────


class Fetcher:
    """2秒間隔・回数上限つきの取得。**上限に当たったら黙って0件を返さず例外にします。**

    黙って空を返す取得は「SD には無かった」と読み違えられます。
    （9/30 に共有 NETSEA アダプタで同型の事故がありました ── 400 を握って
    サンプルデータにフォールバックし、実在する JAN が「0件」に見えた。）
    """

    class CapReached(RuntimeError):
        pass

    def __init__(self, cap: int = DEFAULT_FETCH_CAP, sleep: float = SLEEP_SEC):
        self.cap = cap
        self.sleep = sleep
        self.used = 0

    def __call__(self, url: str) -> str:
        if self.used >= self.cap:
            raise self.CapReached(f"取得上限 {self.cap} 回に達しました（使用 {self.used}）")
        req = urllib.request.Request(url, headers=UA)
        body = urllib.request.urlopen(req, timeout=40).read()
        self.used += 1
        time.sleep(self.sleep)
        return body.decode("utf-8", errors="replace")


# 検索が広すぎるときは商品ページを開きません。
# 実測（2026-09-30）: 「ライオン」で25社93件、「La」で25社97件。先頭4枚を開いても当たりません。
# **広い語の先頭4枚は当てずっぽう**で、1枚2秒を捨てるだけです。
TOO_BROAD_SUPPLIERS = 8


def find_by_identity(jan: str = "", maker_code: str = "", brand: str = "", title: str = "",
                     fetch=None, max_products_per_query: int = 4,
                     log=print) -> tuple[list[SDSet], dict]:
    """Amazon 側の1商品を SD で当てる。**一致の確認は JAN で行います。**

    検索語は当たりやすい順に試し、**JAN が一致した瞬間に止めます**。
    JAN が一致しないものは `near` に入れて返します（同じブランドの別品番＝人が見る価値あり）。

    戻り値: (JAN 一致した規格, 経過の記録)
    """
    fetch = fetch or Fetcher()
    trace = {"queries": [], "fetched": 0, "near": []}
    for q in lookup_plan(jan, maker_code, brand, title):
        try:
            html = fetch(search_url(q))
        except Fetcher.CapReached:
            trace["stopped"] = "取得上限"
            break
        except OSError as e:                             # noqa: BLE001 - 1語で全体を止めない
            trace["queries"].append({"q": q, "error": str(e)})
            continue
        sups, pids, total = parse_search(html)
        trace["queries"].append({"q": q, "suppliers": len(sups), "products": len(pids),
                                 "total_suppliers": total})
        log(f"    SD 検索「{q}」→ 企業 {len(sups)}社・商品 {len(pids)}件")
        if (total or len(sups)) > TOO_BROAD_SUPPLIERS:
            trace["queries"][-1]["skipped"] = "広すぎる（商品ページを開かない）"
            log(f"      広すぎるので商品ページは開きません（{total or len(sups)}社）")
            continue
        for pid in pids[:max_products_per_query]:
            try:
                page = fetch(product_url(pid))
            except Fetcher.CapReached:
                trace["stopped"] = "取得上限"
                return [], trace
            except OSError:
                continue
            trace["fetched"] += 1
            rows = parse_product(page, product_url(pid))
            hit = [r for r in rows if jan and r.jan == jan]
            if hit:
                log(f"    ✅ JAN 一致 {jan} → SD品番 {hit[0].sd_code}"
                    f"（{hit[0].supplier.name if hit[0].supplier else '?'}）")
                return hit, trace
            for r in rows:
                if r.jan:
                    trace["near"].append({"sd_code": r.sd_code, "jan": r.jan,
                                          "name": r.name[:60],
                                          "supplier": r.supplier.name if r.supplier else ""})
    return [], trace


def index_by_words(words: list[str], fetch=None, products_per_word: int = 6,
                   log=print) -> tuple[list[SDSet], dict]:
    """**仕入れ先起点**で積む（社長指示②）。JAN での当て込みはしません。

    「Amazon で売れている棚を SD で当てる」向きは、SD が JAN で引けないぶん高くつきます
    （実測: 10件に48リクエスト・一致0件）。逆向き ── **SD にある商品をとにかく索引に入れる** ──
    なら、1リクエストで数件ぶんの JAN が取れ、**次からの突合は0リクエスト**になります。

    引数の `words` は「当社が扱いたい棚」の語（SD が得意な生活雑貨・キッチン・インテリア等）。
    戻り値の行は卸価格が空（非ログイン）ですが、**JAN・入り数・販売規制は埋まります**。
    """
    fetch = fetch or Fetcher()
    rows: list[SDSet] = []
    trace = {"words": [], "fetched": 0}
    for w in words:
        try:
            html = fetch(search_url(w))
        except Fetcher.CapReached:
            trace["stopped"] = "取得上限"
            break
        except OSError as e:                             # noqa: BLE001
            trace["words"].append({"word": w, "error": str(e)})
            continue
        sups, pids, total = parse_search(html)
        got = 0
        for pid in pids[:products_per_word]:
            try:
                page = fetch(product_url(pid))
            except Fetcher.CapReached:
                trace["stopped"] = "取得上限"
                trace["words"].append({"word": w, "suppliers": total, "indexed": got})
                return rows, trace
            except OSError:
                continue
            trace["fetched"] += 1
            new = [r for r in parse_product(page, product_url(pid)) if r.jan]
            rows.extend(new)
            got += len(new)
        trace["words"].append({"word": w, "suppliers": total, "products": len(pids),
                               "indexed": got})
        log(f"    SD「{w}」→ 企業 {total}社・商品 {len(pids)}件 → JAN 付き {got}件を索引")
    return rows, trace


# ── ログインが要る値を呼び出し側から埋める ────────────────────────────────


def merge_wholesale(rows: list[SDSet], filled: dict) -> list[SDSet]:
    """カズヨがブラウザで見た卸価格を行に流し込む。

    `filled` の形（`agent_output/.../sd_wholesale.json`）:

        {"13681795S1": {"卸価格": 620, "承認状態": "承認済み", "在庫": "在庫あり"},
         "13681795S2": {"承認状態": "卸価格未承認"}}

    - 金額が入れば `承認済み`。`卸価格未承認` は**申請すれば見える**状態で、**NO-GO ではありません**。
    - **人が入れた値を機械が上書きしません。**この関数は人の値で機械の値を上書きする方向だけです。
    """
    for r in rows:
        v = filled.get(r.sd_code) or filled.get(r.product_id)
        if not v:
            continue
        price = _int(v.get("卸価格"))
        if price:
            r.wholesale_price_excl = price
            r.approval = v.get("承認状態") or "承認済み"
        elif v.get("承認状態"):
            r.approval = v["承認状態"]
        if v.get("在庫"):
            r.stock = v["在庫"]
        if v.get("入り数"):
            r.units_per_set = _int(v["入り数"])
        r.notes.append("卸価格は人がブラウザで確認")
    return rows


def approval_requests(rows: list[SDSet], asin_by_jan: dict | None = None) -> list[dict]:
    """卸価格の承認申請をしたい出展企業を、**申請理由つき**でまとめる。

    ⛔ **申請そのものは実行しません**（出展企業への連絡＝CLAUDE.md §4.1）。
    社長承認はカズヨが取ります。ここが作るのは「誰に・なぜ」の一覧だけです。

    ⚠️ **理由は事実に合わせて書き分けます。**`asin_by_jan` で Amazon 側の突合が
    取れている企業は「実売のある棚と一致」、取れていない企業は「品揃えが当社の棚に近い」。
    突合していないのに「Amazon で一致」と書くと、**申請の優先順位を社長が読み違えます。**
    """
    asin_by_jan = asin_by_jan or {}
    by: dict[str, dict] = {}
    for r in rows:
        if r.approval == "承認済み" or not r.supplier:
            continue
        e = by.setdefault(r.supplier.supplier_id,
                          {"出展企業": r.supplier.name,
                           "supplier_id": r.supplier.supplier_id,
                           "該当商品数": 0, "Amazon突合済み": 0,
                           "扱い商品の傾向": [], "ネット販売": r.net_sales_ok,
                           "消費者直送": r.direct_ship_ok, "JAN例": []})
        e["該当商品数"] += 1
        if asin_by_jan.get(r.jan):
            e["Amazon突合済み"] += 1
        if r.name and r.name[:40] not in e["扱い商品の傾向"] and len(e["扱い商品の傾向"]) < 5:
            e["扱い商品の傾向"].append(r.name[:40])
        if r.jan and r.jan not in e["JAN例"] and len(e["JAN例"]) < 3:
            e["JAN例"].append(r.jan)
    out = sorted(by.values(), key=lambda e: (-e["Amazon突合済み"], -e["該当商品数"]))
    for e in out:
        if e["Amazon突合済み"]:
            e["申請したい理由"] = (
                f"Amazon 側で実売のある棚 {e['Amazon突合済み']}件が、この企業の出品と JAN 一致。"
                f"卸価格が見えないと採算が確定できない（ネット販売 {e['ネット販売']}）")
        else:
            e["申請したい理由"] = (
                f"当社が狙う棚（生活雑貨・インテリア系）の品揃えが {e['該当商品数']}件。"
                f"**Amazon 側との突合はまだ取れていない**ので、卸価格が見えれば"
                f"採算のあたりを付けられる（ネット販売 {e['ネット販売']}）")
    return out


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {}
