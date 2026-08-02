"""メーカー仕入れ候補の抽出ハーネス（T-20260705-002・サトル）。

狙い: 狙いの商品 → その裏のメーカー（ブランド/manufacturer）を炙り出し、
「問い合わせ先メーカー一覧（メーカー台帳CSV）」の種を作る。

既存資産を再利用する（再実装しない）:
  - adapters.amazon_data.KeepaBackend の _fetch_finder_asins / _request / _product_to_amazon
  - discovery/keepa 由来の selection 形式（selection.json をそのまま流す）

★重要な補足（このスクリプト独自）:
  既存 _product_to_amazon() は brand/manufacturer を捨てる（AmazonProduct に列が無い）。
  メーカー抽出にはこの2フィールドが必須なので、raw な Keepa product dict から
  brand / manufacturer / eanList を直接読む。これらは product 応答に既に含まれ、
  追加トークンは消費しない（stats=90 の1バッチで取得済み）。

トークン厳格キャップ（社長制約・残トークン僅少）:
  - Finder query 1コール（10token + ASIN数/100）
  - product 詳細は MAX_DETAIL 件（既定15）に厳格キャップ、1バッチのみ
  → 想定消費: おおむね 25〜45 token。実行前に /token で残高を確認する。

使い方:
  python3 extract_maker_candidates.py            # selection.json を使い実走
  python3 extract_maker_candidates.py --dry      # トークン残高だけ表示して終了
  MAX_DETAIL は環境変数 MAX_DETAIL でも上書き可（既定15・上限20）。
"""
import csv
import gzip
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 既存資産（コード本体）。agent_output を優先、無ければ deliverables。
CODE_CANDIDATES = [
    Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260521-005/code"),
    Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/code"),
]
CODE = next((p for p in CODE_CANDIDATES if p.exists()), CODE_CANDIDATES[-1])
sys.path.insert(0, str(CODE))

# .env（KEEPA_API_KEY 等）を CODE 側から読み込む（agent_output に実在）。
ENV_PATH = None
for c in CODE_CANDIDATES:
    if (c / ".env").exists():
        ENV_PATH = c / ".env"
        break
if ENV_PATH:
    for _l in open(ENV_PATH):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            k, v = _l.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.amazon_data import KeepaBackend, _product_to_amazon  # noqa: E402

SELECTION_PATH = HERE / "selection.json"
OUT_CSV = HERE / "maker_candidates.csv"
AGENT_OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260705-002")
RAW_JSON = AGENT_OUT / "keepa_raw_products.json"

MAX_DETAIL = min(int(os.environ.get("MAX_DETAIL", "15")), 20)  # 詳細取得ASINの厳格上限

# 規制カテゴリ相当の後処理ブロックリスト（カテゴリ除外の取りこぼしを名寄せで潰す）。
# 薬機法/PSE/酒/医療/化粧品/サプリ/食品 に該当しそうなタイトル語を弾く。
BLOCK_WORDS = [
    "医薬", "第一類", "第二類", "第三類", "指定医薬", "医療機器", "サプリ", "サプリメント",
    "化粧品", "コスメ", "美容液", "化粧水", "乳液", "日焼け止め", "ワイン", "日本酒",
    "焼酎", "ウイスキー", "ビール", "リキュール", "アルコール度数", "食品", "飲料",
    "健康食品", "栄養機能", "コンタクトレンズ", "マスク", "体温計", "血圧計",
    # メディア/成人向け（メーカー仕入れの対象外＝再販できない/直取引不可）。
    "MOODYZ", "ムーディーズ", "中出し", "本番", "AV女優", "アダルト", "DVD", "Blu-ray",
    "ブルーレイ", "Deluxe Edition", "CD)", "(CD", "写真集", "アイドル",
]

# categoryTree に出たら除外する規制/対象外カテゴリ名（カテゴリ名寄せの二段ガード）。
BLOCK_CATEGORY_WORDS = [
    "アダルト", "DVD", "ミュージック", "CD", "本", "洋書", "Kindle", "医薬",
    "ドラッグストア", "ビューティー", "コスメ", "食品", "飲料", "お酒", "サプリ",
]

# 大手メーカー疑い（◎/○/△判定用）。ここに載る＝直取引しづらい大手の可能性。
BIG_MAKERS = [
    "パナソニック", "panasonic", "ソニー", "sony", "花王", "kao", "ライオン", "lion",
    "資生堂", "shiseido", "サンスター", "コクヨ", "kokuyo", "アイリスオーヤマ", "iris",
    "山善", "yamazen", "象印", "zojirushi", "タイガー", "tiger", "シャープ", "sharp",
    "東芝", "toshiba", "日立", "hitachi", "ブラザー", "brother", "エレコム", "elecom",
    "バッファロー", "buffalo", "ロジクール", "logicool", "logitech", "3m", "コニカ",
    "ニトリ", "無印", "casio", "カシオ", "セイコー", "seiko", "シチズン", "citizen",
    "ピジョン", "pigeon", "コンビ", "combi", "レゴ", "lego", "バンダイ", "bandai",
    "タカラトミー", "takara", "epson", "エプソン", "canon", "キヤノン", "nikon",
]


def _get_key():
    return os.environ.get("KEEPA_API_KEY")


def check_tokens():
    key = _get_key()
    if not key:
        return None
    url = "https://api.keepa.com/token?key=%s" % key
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
        d = json.loads(raw)
    return d


def _brand_of(prod: dict) -> str:
    """raw Keepa product から「メーカー名の当たり」を決める。

    優先: brand > manufacturer > partNumber接頭 の順。両方 None なら空。
    Keepa は brand/manufacturer を product 応答に含める（追加トークン無し）。
    """
    b = (prod.get("brand") or "").strip()
    m = (prod.get("manufacturer") or "").strip()
    if b:
        return b
    if m:
        return m
    return ""


def _big_maker_verdict(maker: str) -> str:
    ml = maker.lower()
    for w in BIG_MAKERS:
        if w.lower() in ml:
            return "△大手疑い"
    return ""  # 空＝後段で ◎/○ を人手/Web調査で確定（自動では中小と断定しない）


def _blocked(title: str) -> bool:
    return any(w in title for w in BLOCK_WORDS)


def _blocked_category(prod: dict) -> bool:
    tree = prod.get("categoryTree") or []
    names = " / ".join(c.get("name", "") for c in tree if isinstance(c, dict))
    return any(w in names for w in BLOCK_CATEGORY_WORDS)


def _est_monthly(ap) -> str:
    """想定月販 ＝ 平均月販 ÷ (出品者数+1)。月販/出品者が欠けたら空。"""
    ms = getattr(ap, "monthly_sales", None)
    oc = getattr(ap, "offer_count", None)
    if ms is None or oc is None:
        return ""
    return str(round(ms / (oc + 1), 1))


def _rows_from_products(prods):
    """raw Keepa product 群 → 台帳行（規制/対象外/重複を除外）。トークン0。"""
    rows = []
    seen_asin = set()
    skipped_block = 0
    for prod in prods:
        ap = _product_to_amazon(prod)
        if ap is None:
            continue
        if ap.asin in seen_asin:
            continue
        seen_asin.add(ap.asin)
        title = prod.get("title") or ""
        if _blocked(title) or _blocked_category(prod):
            skipped_block += 1
            continue
        maker = _brand_of(prod)
        eans = [str(c) for c in (prod.get("eanList") or [])]
        cat_tree = prod.get("categoryTree") or []
        cat_name = cat_tree[-1]["name"] if cat_tree and isinstance(cat_tree[-1], dict) else ""
        rows.append({
            "メーカー名": maker or "(不明)",
            "種商品名": title,
            "ASIN": ap.asin,
            "カテゴリ": cat_name or ap.category_key,
            "現ランク": ap.sales_rank if ap.sales_rank is not None else "",
            "現FBA出品者数": ap.offer_count if ap.offer_count is not None else "",
            "推定月販": _est_monthly(ap),
            "参考価格": int(ap.current_price) if ap.current_price else "",
            "公式HP": "",           # Web調査で埋める（自動では入れない）
            "問い合わせ手段": "",     # Web調査で埋める
            "中小メーカー判定": _big_maker_verdict(maker),
            "JAN": eans[0] if eans else "",
            "備考": "",
        })
    return rows, skipped_block


def _write_csv(rows):
    cols = ["メーカー名", "種商品名", "ASIN", "カテゴリ", "現ランク", "現FBA出品者数",
            "推定月販", "参考価格", "公式HP", "問い合わせ手段", "中小メーカー判定",
            "JAN", "備考"]
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    dry = "--dry" in sys.argv
    # --from-raw: 保存済み raw JSON から再フィルタのみ（トークン0）。
    if "--from-raw" in sys.argv:
        prods = json.load(open(RAW_JSON, encoding="utf-8"))
        rows, skipped = _rows_from_products(prods)
        _write_csv(rows)
        print("[from-raw] メーカー候補 %d件（規制/対象外除外 %d件）: %s" % (
            len(rows), skipped, OUT_CSV))
        from collections import Counter
        cnt = Counter(r["メーカー名"] for r in rows if r["メーカー名"] != "(不明)")
        print("ユニークメーカー数=%d" % len(cnt))
        return

    key = _get_key()
    if not key:
        print("ERROR: KEEPA_API_KEY 未設定。CODE/.env を確認してください。")
        print("  探索した CODE:", CODE)
        print("  探索した .env:", ENV_PATH)
        sys.exit(2)

    tok = check_tokens()
    if tok is not None:
        print("Keepa tokensLeft=%s refillRate=%s/min" % (
            tok.get("tokensLeft"), tok.get("refillRate")))
    if dry:
        print("--dry: トークン残高のみ表示して終了。")
        return

    left = (tok or {}).get("tokensLeft", 0) or 0
    # 安全マージン: Finder(10+) + product 15件(~30) ≒ 45 は最低欲しい。
    need = 20 + MAX_DETAIL
    if left < need:
        print("STOP: 残トークン %s < 必要目安 %s。補充を待って再実行してください"
              "（refillRate=%s/min）。" % (left, need, (tok or {}).get("refillRate")))
        print("  待機の目安: (需要-残)/refillRate 分。selection.json はそのまま使えます。")
        sys.exit(3)

    selection = json.loads(open(SELECTION_PATH, encoding="utf-8").read())
    # _comment は Keepa に送らない（無害だが念のため除去）。
    selection = {k: v for k, v in selection.items() if not k.startswith("_")}

    be = KeepaBackend(api_key=key)
    print("Product Finder query 実行... selection=", json.dumps(selection, ensure_ascii=False))
    asins = be._fetch_finder_asins(selection)  # noqa: SLF001（既存資産の再利用）
    print("Finder 該当ASIN=%d件 tokensLeft=%s" % (len(asins), be.last_tokens_left))
    if not asins:
        print("該当0件。条件を緩めるか別カテゴリで再実行してください。")
        sys.exit(0)

    asins = asins[:MAX_DETAIL]
    print("詳細取得 %d件（厳格キャップ MAX_DETAIL=%d）" % (len(asins), MAX_DETAIL))
    payload = be._request(asin=",".join(asins))  # noqa: SLF001
    print("詳細取得 consumed=%s tokensLeft=%s" % (
        payload.get("tokensConsumed"), payload.get("tokensLeft")))

    prods = payload.get("products") or []
    AGENT_OUT.mkdir(parents=True, exist_ok=True)
    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(prods, f, ensure_ascii=False, indent=1)
    print("raw products を保存:", RAW_JSON)

    rows, skipped_block = _rows_from_products(prods)
    _write_csv(rows)
    print("メーカー候補 %d件を書き出し（規制/対象外除外 %d件）: %s" % (
        len(rows), skipped_block, OUT_CSV))
    # ブランド別の集約サマリ（重複メーカーを可視化）。
    from collections import Counter
    cnt = Counter(r["メーカー名"] for r in rows if r["メーカー名"] != "(不明)")
    print("ユニークメーカー数=%d" % len(cnt))
    for m, c in cnt.most_common(10):
        print("  %s x%d" % (m, c))


if __name__ == "__main__":
    main()
