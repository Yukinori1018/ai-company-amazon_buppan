"""メーカー仕入れ 方針v1.3 実走スキャナ（T-20260817-005）。

社長依頼: 「売れている かつ 仕入れられる商品を100個ほどピックアップ」。
抽出軸は **Keepa 月間ドロップ数**（BSR の急落回数＝推定販売件数）。ランクは足切りに使わない。

パイプライン:
  Phase1 Finder : Keepa Product Finder を A/B 2プリセットで叩き ASIN を集める
                  （salesRankDrops30 降順・perPage=1000 でトークン効率を最大化）
  Phase2 詳細   : 100件バッチで product?stats=365 を取得
                  → raw JSON を必ず gzip 保存（--from-raw で **トークン0** 再フィルタ可能）
                  → 段0(機械) / 段1(回転) / 段2(値下げ耐性) を適用し 1バッチごとに CSV へ追記
  Phase3 仕上げ : GO 行を「消化月数」昇順に並べ top100 CSV と summary.json を書く

トークン経済（律速）:
  Finder  = 10 + ceil(件数/100) トークン（perPage=1000 なら 1000件で 20 トークン）
  product = 1 トークン/件（stats=365 の追加コストは無い＝実測確認済 2026-08-21）
  残高が MIN_TOKENS を割ったら補充を待つ（落とさない・無人運転前提）

使い方:
  python3 scan_v13.py                     # 通常実行（既存 CSV から再開）
  python3 scan_v13.py --target-a 3000 --target-b 2000
  python3 scan_v13.py --from-raw          # API を叩かず raw/ だけで再集計（トークン0）
"""
import argparse
import csv
import gzip
import json
import math
import os
import re
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------------
# 依存: 既存の共有ライブラリ（Keepa 正規化・手数料表）
#   .env の実在場所は agent_output 側だけ（deliverables 側には無い）。過去に何度も踏んだ罠。
# --------------------------------------------------------------------------
ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
sys.path.insert(0, str(CODE))
for _line in open(CODE / ".env", encoding="utf-8"):
    _line = _line.strip()
    if _line and not _line.startswith("#") and "=" in _line:
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k, _v.strip().strip('"').strip("'"))

from adapters.amazon_data import _map_category_key  # noqa: E402
from calc import fees  # noqa: E402

OUT = ROOT / "workspace/output/deliverables/T-20260817-005"
RAW = OUT / "raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

CSV_ALL = OUT / "candidates_v13.csv"
CSV_TOP = OUT / "candidates_v13_top100.csv"
SUMMARY = OUT / "summary.json"
LOG = OUT / "scan_v13.log"
FINDER_JSON = OUT / "finder_selections.json"

# ==========================================================================
# v1.3 の基準値（社長裁可 2026-08-17）。ここだけ直せば条件を変えられる。
# ==========================================================================
KEEPA_DOMAIN_JP = 5
KEEPA_EPOCH_MIN = 21564000          # Keepa time(分) = unixtime/60 - この値

RANK_MAX = 300_000                  # ランクは「足切りに使わない」＝30万位まで開放
OFFERS_MIN, OFFERS_MAX = 2, 6       # 2以上=卸している証拠 / 6以下=取り分が残る
REVIEWS_MIN, REVIEWS_MAX = 5, 300   # 「あまり有名でない」の機械化
VARIATION_MIN, VARIATION_MAX = 1, 3
TRACKING_DAYS_MIN = 180             # 追跡180日以上（データが薄い商品を弾く）

PRESETS = {
    # name: (価格下限, 価格上限, 月間ドロップ数の下限)
    "A": (1500, 8000, 10),
    "B": (8000, 20000, 4),
}

# 除外4カテゴリ（ドラッグ／ビューティー／食品／アダルト）。
# Finder の categories_exclude（ルートID）＋ 後処理のキーワード二段構え。
EXCLUDE_ROOT_CATEGORIES = [
    160384011,   # ドラッグストア
    52374051,    # ビューティー
    57239051,    # 食品・飲料・お酒
]
NG_CATEGORY_WORDS = re.compile(
    r"(ドラッグ|医薬|サプリメント|ビューティー|コスメ|化粧|食品|飲料|お酒|"
    r"アダルト|大人のおもちゃ|成人)"
)
NG_TITLE_WORDS = re.compile(r"(アダルト|18禁|成人向|医薬品|指定第2類|第(1|2|3)類医薬品)")

# 大手・海外ブランドの検知（除外はしない・注記のみ）。
# v1.3 の「レビュー5〜300＝あまり有名でない」は新規SKUの大手品を素通しするため、
# 人が優先順位を決められるようにフラグだけ立てる（除外は社長判断の領域）。
BIG_BRAND_HINTS = re.compile(
    r"(SONY|ソニー|Panasonic|パナソニック|東芝|TOSHIBA|日立|SHARP|シャープ|"
    r"Nike|ナイキ|adidas|アディダス|Apple|Anker|アンカー|UGREEN|Baseus|"
    r"Logicool|Logitech|Canon|Nikon|BANDAI|バンダイ|TAKARA|タカラトミー|"
    r"任天堂|Nintendo|BUFFALO|バッファロー|ELECOM|エレコム|Philips|フィリップス|"
    r"SanDisk|Seagate|Xiaomi|シャオミ|EPSON|エプソン|Brother|ブラザー|"
    r"アイリスオーヤマ|IRIS|山善|YAMAZEN|KOKUYO|コクヨ|ZOJIRUSHI|象印|"
    r"TIGER|タイガー|CASIO|カシオ|SEIKO|セイコー|BURTLE|バートル)", re.I)

# FBA 標準サイズ（Amazon.co.jp）: 45×35×20cm 以内 かつ 9kg 以内。超えたら「大型」で除外。
FBA_STD_DIMS_MM = (450, 350, 200)
FBA_STD_WEIGHT_G = 9000

# 段1（回転）: 想定月販 = 月間ドロップ数 ÷ (出品者数+1)、消化月数 = 初回ロット ÷ 想定月販
LOT_SIZE = 10                       # v1.2「制限ありは初回10点以上」に合わせた保守側の既定
LOT_SIZE_ALT = 5                    # 本家の最小ロット。参考列として併記
TURNOVER_MONTHS_MAX = 3.0           # 消化月数3ヶ月以内＝GO

# 段2（値下げ耐性）: 損益分岐仕入れ値 = 過去1年最安売価 × 0.65 − 外注費
GROSS_KEEP_RATE = 0.65              # 経費35%概算（EC STARs セミナー値）。社長裁可の係数
# 外注費 = Amazon商品ラベル貼付22円(税込・公式G200483750) + 梱包外注10円(WAM NET) + 納品送料
OUTSOURCE_COST = {"small": 182, "standard_1": 282, "standard_2": 332, "unknown": 282}

MIN_TOKENS = 150                    # これを割ったら補充待ち
DETAIL_CHUNK = 100                  # product エンドポイントの1リクエスト上限
FINDER_PER_PAGE = 1000              # 実測: perPage=1000 が通る（1000件で20トークン）

FIELDS = [
    "preset", "ASIN", "商品名", "ブランド", "メーカー", "カテゴリ", "ランク",
    "月間ドロップ数", "月間販売数", "出品者数", "BuyBox価格", "過去1年最安値",
    "損益分岐仕入れ値", "損益分岐仕入れ値_精緻", "仕入れ掛け率上限%",
    "想定月販", "消化月数", "消化月数_ロット5", "FBAサイズ区分", "外注費", "規模フラグ",
    "段1回転", "段2値下げ耐性", "判定", "見送り理由", "出品制限チェック", "Amazonページ",
]


# ==========================================================================
# ユーティリティ
# ==========================================================================
def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def api_key() -> str:
    key = os.environ.get("KEEPA_API_KEY")
    if not key:
        raise SystemExit("KEEPA_API_KEY が未設定です（.env を確認）")
    return key


def token_status() -> dict:
    import requests
    return requests.get(
        f"https://api.keepa.com/token?key={api_key()}&domain={KEEPA_DOMAIN_JP}",
        timeout=30,
    ).json()


def wait_tokens(need: int = MIN_TOKENS) -> int:
    """トークンが need に届くまで待つ。落とさずに待つのが無人運転の肝。"""
    while True:
        try:
            d = token_status()
        except Exception:
            time.sleep(10)
            continue
        left = d.get("tokensLeft", 0)
        if left >= need:
            return left
        rate = d.get("refillRate") or 20
        wait = min(max((need - left) / rate * 60, 15), 300)
        log(f"  トークン補充待ち: left={left} need={need} → {wait:.0f}秒")
        time.sleep(wait)


# ==========================================================================
# Phase1: Product Finder
# ==========================================================================
def build_selection(preset: str, page: int) -> dict:
    price_lo, price_hi, drops_min = PRESETS[preset]
    tracking_before = int(time.time() / 60) - KEEPA_EPOCH_MIN - TRACKING_DAYS_MIN * 24 * 60
    return {
        # --- 機械ふるい（v1.3）---
        "current_AMAZON_gte": -1, "current_AMAZON_lte": -1,      # Amazon本体不在
        "current_COUNT_NEW_gte": OFFERS_MIN, "current_COUNT_NEW_lte": OFFERS_MAX,
        "current_NEW_gte": price_lo, "current_NEW_lte": price_hi,
        "current_SALES_gte": 1, "current_SALES_lte": RANK_MAX,   # 足切りではなく上限開放
        "current_COUNT_REVIEWS_gte": REVIEWS_MIN, "current_COUNT_REVIEWS_lte": REVIEWS_MAX,
        "variationCount_gte": VARIATION_MIN, "variationCount_lte": VARIATION_MAX,
        "trackingSince_lte": tracking_before,
        "isAdultProduct": False,
        "categories_exclude": EXCLUDE_ROOT_CATEGORIES,
        "salesRankDrops30_gte": drops_min,                       # ★抽出軸
        # --- ページング ---
        "perPage": FINDER_PER_PAGE, "page": page,
        "sort": [["salesRankDrops30", "desc"]],                  # 回転の良い順に取る
    }


def finder_asins(preset: str, target: int) -> tuple:
    """preset の条件で ASIN を target 件まで集める。返り値 (asins, totalResults)。"""
    import requests
    got, total = [], None
    page = 0
    while len(got) < target:
        wait_tokens(need=40)
        sel = build_selection(preset, page)
        try:
            resp = requests.get(
                "https://api.keepa.com/query",
                params={"key": api_key(), "domain": KEEPA_DOMAIN_JP,
                        "selection": json.dumps(sel, separators=(",", ":"))},
                timeout=180,
            )
            payload = resp.json()
        except Exception as e:
            log(f"  [Finder {preset}] p{page} エラー: {e}")
            time.sleep(10)
            continue
        asins = payload.get("asinList") or []
        total = payload.get("totalResults") if total is None else total
        log(f"  [Finder {preset}] page={page} 取得={len(asins)} 累計={len(got) + len(asins)} "
            f"該当総数={total} tokensLeft={payload.get('tokensLeft')}")
        if not asins:
            break
        got.extend(asins)
        page += 1
        time.sleep(0.5)
    return list(dict.fromkeys(got))[:target], total


# ==========================================================================
# Phase2: 詳細取得 → 判定
# ==========================================================================
def keepa_products(asins: list) -> dict:
    """product?stats=365 を1回叩く。429 は待って再試行（無人運転で落とさない）。"""
    import requests
    params = {"key": api_key(), "domain": KEEPA_DOMAIN_JP, "stats": 365,
              "asin": ",".join(asins)}
    for attempt in range(5):
        resp = requests.get("https://api.keepa.com/product", params=params, timeout=300)
        if resp.status_code == 429:
            wait = min(30 * (attempt + 1), 180)
            log(f"    429（トークン上限）→ {wait}秒待機")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("Keepa product: 429 が解消しませんでした")


def _num(v):
    """Keepa の -1/-2/None は「データ無し」。数値だけ返す。"""
    if isinstance(v, (int, float)) and v >= 0:
        return v
    return None


def _stat_min(stats: dict, idx: int):
    """stats.min[idx] は [keepa時刻, 値] または null。値だけ取り出す。"""
    arr = stats.get("min") or []
    if len(arr) > idx and isinstance(arr[idx], list) and len(arr[idx]) == 2:
        return _num(arr[idx][1])
    return None


def fba_size_class(product: dict) -> tuple:
    """(size_key, 区分表示)。FBA標準サイズ(45x35x20cm/9kg)を超えたら大型。

    寸法・重量が Keepa に無い商品は「不明」。除外はせず列に出して人が判断する
    （除外すると母数が大きく削れるため。データは正直に、判断は人に渡す）。
    """
    dims = [product.get("packageLength"), product.get("packageWidth"),
            product.get("packageHeight")]
    dims = sorted([d for d in dims if isinstance(d, (int, float)) and d > 0], reverse=True)
    weight = product.get("packageWeight")
    weight = weight if isinstance(weight, (int, float)) and weight > 0 else None
    if len(dims) < 3 and weight is None:
        return "unknown", "不明"
    if len(dims) == 3:
        if any(d > lim for d, lim in zip(dims, FBA_STD_DIMS_MM)):
            return "large", "大型"
    if weight is not None and weight > FBA_STD_WEIGHT_G:
        return "large", "大型"
    if weight is None:
        return "unknown", "不明(重量欠落)"
    if weight <= 250 and (not dims or dims[0] <= 250):
        return "small", "標準(小型)"
    if weight <= 1000:
        return "standard_1", "標準1"
    return "standard_2", "標準2"


def evaluate(product: dict, preset: str) -> dict:
    """1商品を v1.3 の 段0/段1/段2 で評価して CSV 1行に落とす。"""
    stats = product.get("stats") or {}
    cur = stats.get("current") or []
    asin = product.get("asin") or ""
    title = product.get("title") or ""
    brand = (product.get("brand") or "").strip()
    maker = (product.get("manufacturer") or "").strip()
    cat_names = [c.get("name", "") for c in (product.get("categoryTree") or [])
                 if isinstance(c, dict)]
    cat_label = " > ".join(cat_names[:3])

    rank = _num(cur[3]) if len(cur) > 3 else None
    offers = _num(cur[11]) if len(cur) > 11 else None
    drops30 = _num(stats.get("salesRankDrops30"))
    monthly_sold = product.get("monthlySold")
    monthly_sold = int(monthly_sold) if isinstance(monthly_sold, (int, float)) and monthly_sold > 0 else ""
    buybox = _num(stats.get("buyBoxPrice")) or (_num(cur[1]) if len(cur) > 1 else None)
    low_365 = _stat_min(stats, 1)   # index 1 = NEW（マーケットプレイス新品最安）
    size_key, size_label = fba_size_class(product)
    outsource = OUTSOURCE_COST.get(size_key, OUTSOURCE_COST["unknown"])

    row = {
        "preset": preset, "ASIN": asin, "商品名": title[:80], "ブランド": brand,
        "メーカー": maker, "カテゴリ": cat_label, "ランク": int(rank) if rank else "",
        "月間ドロップ数": int(drops30) if drops30 else "",
        "月間販売数": monthly_sold,
        "出品者数": int(offers) if offers is not None else "",
        "BuyBox価格": int(buybox) if buybox else "",
        "過去1年最安値": int(low_365) if low_365 else "",
        "FBAサイズ区分": size_label, "外注費": outsource,
        "規模フラグ": ("大手/海外疑い" if BIG_BRAND_HINTS.search(f"{brand} {maker} {title}")
                  else "中小候補"),
        "出品制限チェック": "",
        "Amazonページ": f"https://www.amazon.co.jp/dp/{asin}",
    }

    # ---- 段0: 機械ふるい（Finder の取りこぼしをここで潰す）----
    reasons = []
    if NG_CATEGORY_WORDS.search(cat_label) or NG_TITLE_WORDS.search(title):
        reasons.append("除外カテゴリ")
    if size_label == "大型":
        reasons.append("FBA大型サイズ")
    if offers is None or not (OFFERS_MIN <= offers <= OFFERS_MAX):
        reasons.append(f"出品者数{offers}")
    if rank is None or rank > RANK_MAX:
        reasons.append("ランク圏外")
    if not drops30 or drops30 < PRESETS[preset][2]:
        reasons.append("ドロップ数不足")
    if not buybox:
        reasons.append("価格取得不可")
    if _num(cur[0]) is not None:
        reasons.append("Amazon本体あり")

    # ---- 段1: 回転 ----
    est_monthly = drops30 / (offers + 1) if (drops30 and offers is not None) else None
    months = (LOT_SIZE / est_monthly) if est_monthly else None
    months_alt = (LOT_SIZE_ALT / est_monthly) if est_monthly else None
    stage1 = bool(months is not None and months <= TURNOVER_MONTHS_MAX)
    row["想定月販"] = round(est_monthly, 2) if est_monthly else ""
    row["消化月数"] = round(months, 2) if months else ""
    row["消化月数_ロット5"] = round(months_alt, 2) if months_alt else ""
    row["段1回転"] = "GO" if stage1 else "NG"
    if not stage1:
        reasons.append("回転不足(消化月数>3)")

    # ---- 段2: 値下げ耐性 ----
    breakeven = None
    breakeven_fine = None
    if low_365:
        breakeven = low_365 * GROSS_KEEP_RATE - outsource
        # 精緻版: 販売手数料(カテゴリ実料率) + FBA配送代行 + 外注費 を実額で引く
        cat_key = _map_category_key(product)
        cfg = fees.REFERRAL_FEE_TABLE.get(cat_key, fees.REFERRAL_FEE_TABLE["default"])
        referral = max(low_365 * cfg["rate"], cfg.get("min_fee_yen", 0))
        fba_key = size_key if size_key in fees.FBA_FEE_TABLE else "standard_1"
        fba_fee = fees.FBA_FEE_TABLE[fba_key]["fba_fee_yen"]
        breakeven_fine = low_365 - referral - fba_fee - outsource
    stage2 = bool(breakeven is not None and breakeven > 0)
    row["損益分岐仕入れ値"] = int(math.floor(breakeven)) if breakeven is not None else ""
    row["損益分岐仕入れ値_精緻"] = int(math.floor(breakeven_fine)) if breakeven_fine is not None else ""
    row["仕入れ掛け率上限%"] = (round(breakeven / buybox * 100, 1)
                          if (breakeven and buybox and breakeven > 0) else "")
    row["段2値下げ耐性"] = "GO" if stage2 else "NG"
    if not stage2:
        reasons.append("最安値で黒字化不能" if low_365 else "過去1年最安値なし")

    row["判定"] = "GO" if not reasons else "見送り"
    row["見送り理由"] = " / ".join(reasons)
    return row


# ==========================================================================
# CSV 入出力（早期確定＝落ちても結果が残る）
# ==========================================================================
def append_rows(rows: list) -> None:
    new = not CSV_ALL.exists()
    with open(CSV_ALL, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def read_existing_asins() -> set:
    if not CSV_ALL.exists():
        return set()
    with open(CSV_ALL, encoding="utf-8-sig") as f:
        return {r["ASIN"] for r in csv.DictReader(f) if r.get("ASIN")}


def write_top100() -> tuple:
    """GO 行を消化月数の昇順で並べ、上位100件を書き出す。水増しはしない。"""
    if not CSV_ALL.exists():
        return 0, 0
    with open(CSV_ALL, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    go = [r for r in rows if r.get("判定") == "GO"]
    seen, uniq = set(), []
    for r in go:                       # 念のため ASIN 重複排除
        if r["ASIN"] not in seen:
            seen.add(r["ASIN"])
            uniq.append(r)

    def key(r):
        try:
            return float(r.get("消化月数") or 9999)
        except ValueError:
            return 9999.0

    uniq.sort(key=key)
    top = uniq[:100]
    with open(CSV_TOP, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in top:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    return len(uniq), len(top)


# ==========================================================================
# raw JSON（トークン0で再フィルタするための保険）
# ==========================================================================
def save_raw(preset: str, idx: int, payload: dict) -> None:
    path = RAW / f"{preset}_{idx:05d}.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def iter_raw():
    for path in sorted(RAW.glob("*.json.gz")):
        preset = path.name.split("_")[0]
        with gzip.open(path, "rt", encoding="utf-8") as f:
            payload = json.load(f)
        for product in payload.get("products") or []:
            yield preset, product


# ==========================================================================
# main
# ==========================================================================
def run_from_raw() -> None:
    log("=== --from-raw: 保存済み raw JSON から再集計（トークン消費0）===")
    if CSV_ALL.exists():
        CSV_ALL.unlink()
    rows, seen = [], set()
    for preset, product in iter_raw():
        asin = product.get("asin")
        if not asin or asin in seen:
            continue
        seen.add(asin)
        rows.append(evaluate(product, preset))
    append_rows(rows)
    n_go, n_top = write_top100()
    log(f"再集計完了: {len(rows)}行 / GO {n_go}件 / top100 {n_top}件")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-a", type=int, default=3000)
    ap.add_argument("--target-b", type=int, default=2000)
    ap.add_argument("--from-raw", action="store_true")
    args = ap.parse_args()

    if args.from_raw:
        run_from_raw()
        return

    t0 = time.time()
    tokens_start = token_status().get("tokensLeft", 0)
    log(f"=== v1.3 実走開始 tokensLeft={tokens_start} 目標 A={args.target_a} B={args.target_b} ===")

    # ---- Phase1 ----
    targets = {"A": args.target_a, "B": args.target_b}
    finder_meta = {}
    asin_plan = []          # [(preset, asin), ...]
    for preset, target in targets.items():
        asins, total = finder_asins(preset, target)
        finder_meta[preset] = {"selection": build_selection(preset, 0),
                               "totalResults": total, "asins_taken": len(asins)}
        asin_plan.extend((preset, a) for a in asins)
        log(f"[Finder {preset}] 確定 {len(asins)}件（該当総数 {total}）")
    FINDER_JSON.write_text(json.dumps(finder_meta, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    # 同一 ASIN が A/B 双方に出ることは価格帯が排他なので無いが、念のため先勝ちで排除
    seen = read_existing_asins()
    if seen:
        log(f"[resume] 既存 CSV の {len(seen)}件をスキップ")
    plan, planned = [], set()
    for preset, asin in asin_plan:
        if asin in seen or asin in planned:
            continue
        planned.add(asin)
        plan.append((preset, asin))
    log(f"=== Phase2: 詳細取得 {len(plan)}件（1件=1トークン）===")

    # ---- Phase2 ----
    stat = {"fetched": 0, "rows": 0, "go": 0}
    by_preset = {}
    for preset, asin in plan:
        by_preset.setdefault(preset, []).append(asin)
    # 再開時に raw/ を上書きしないよう、既存ファイル数から採番を続ける
    chunk_idx = len(list(RAW.glob("*.json.gz")))
    for preset, asins in by_preset.items():
        for i in range(0, len(asins), DETAIL_CHUNK):
            chunk = asins[i:i + DETAIL_CHUNK]
            wait_tokens(need=max(MIN_TOKENS, len(chunk) + 20))
            try:
                payload = keepa_products(chunk)
            except Exception as e:
                log(f"    詳細取得エラー: {e}")
                time.sleep(15)
                continue
            save_raw(preset, chunk_idx, payload)
            chunk_idx += 1
            rows = [evaluate(p, preset) for p in (payload.get("products") or [])]
            append_rows(rows)
            stat["fetched"] += len(chunk)
            stat["rows"] += len(rows)
            stat["go"] += sum(1 for r in rows if r["判定"] == "GO")
            log(f"  [{preset}] {i + len(chunk)}/{len(asins)} 行={stat['rows']} "
                f"GO累計={stat['go']} tokensLeft={payload.get('tokensLeft')}")
            time.sleep(0.3)

    # ---- Phase3 ----
    n_go, n_top = write_top100()
    tokens_end = token_status().get("tokensLeft", 0)
    elapsed = time.time() - t0
    # 消費トークン = 実測の残高差 + 経過時間ぶんの補充分（補充を待ちながら走るため）
    refilled = elapsed / 60 * 20
    consumed = int(tokens_start - tokens_end + refilled)

    reasons = {}
    with open(CSV_ALL, encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))
    for r in all_rows:
        if r["判定"] == "GO":
            continue
        for reason in (r.get("見送り理由") or "").split(" / "):
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1

    summary = {
        "ticket": "T-20260817-005",
        "criteria_version": "v1.3（社長裁可 2026-08-17）",
        "run_finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_sec": int(elapsed),
        "elapsed_hhmm": time.strftime("%H:%M:%S", time.gmtime(elapsed)),
        "keepa": {
            "tokens_at_start": tokens_start,
            "tokens_at_end": tokens_end,
            "tokens_consumed_estimate": consumed,
            "refill_per_min": 20,
        },
        "finder": finder_meta,
        "assumptions": {
            "初回ロット": LOT_SIZE,
            "初回ロット_参考": LOT_SIZE_ALT,
            "消化月数の上限": TURNOVER_MONTHS_MAX,
            "粗利残存率(段2)": GROSS_KEEP_RATE,
            "外注費(サイズ別)": OUTSOURCE_COST,
            "過去1年最安値の定義": "Keepa stats(365日) の NEW(新品最安, index=1) の最小値",
            "FBA標準サイズ": "45x35x20cm かつ 9kg 以内。超過は大型として除外。寸法欠落は『不明』で残す",
        },
        "counts": {
            "detail_fetched": stat["fetched"],
            "rows_written": len(all_rows),
            "go": n_go,
            "top100_written": n_top,
        },
        "reject_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "outputs": {
            "candidates": str(CSV_ALL),
            "top100": str(CSV_TOP),
            "raw_dir": str(RAW),
            "log": str(LOG),
        },
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log("=== 完了 ===")
    log(json.dumps(summary["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
