"""罠フィルタ本番リサーチ（T-20260706-001）。

原石密度2周目のクリーン原石を入口に、Act①の罠フィルタを実装して精査し、
"小さく本番投入できる買い候補ショートリスト"を作る。

罠フィルタ:
  1. 入数不一致（差>2.5倍・セット表記×高比率）除去
  2. 名寄せ：仕入先の商品名を再取得しAmazon名とトークン一致度で別モデル誤突合を除去
  3. ブランド出品制限/真贋：拡張マスタで判定
  4. 薬機/カテゴリ許可：drugstore・食品・ペットフード等をフラグ
  5. Buy Box実在：実売価格で純利益を再計算
残った候補をスコアリングして上位を出力。実購入は社長承認事項（本スクリプトは提示まで）。
"""
import csv
import re
import sys
from pathlib import Path

CODE = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260521-005/code")
DELIV = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/code")
sys.path.insert(0, str(CODE)); sys.path.insert(0, str(DELIV))
import os
for _l in open(CODE / ".env"):
    _l = _l.strip()
    if _l and not _l.startswith("#") and "=" in _l:
        k, v = _l.split("=", 1); os.environ.setdefault(k, v.strip().strip('"').strip("'"))

from adapters.yahoo_shopping import YahooShoppingClient   # noqa: E402
from adapters.rakuten_shopping import RakutenShoppingClient  # noqa: E402
from calc.profit import ProfitInput, calculate  # noqa: E402

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260705-001")
INB = {"small": 150, "standard_1": 250, "standard_2": 300, "large_1": 380, "large_2": 480}
SET_RE = re.compile(r"(\d+)\s*(本|個|枚|袋|セット|kg|ケース|パック|入|台|巻)")

# 出品制限・真贋リスクの高いブランド/IP（初心者は相乗り不可の代表格）
BRANDS = [
    "シマノ", "shimano", "ダンロップ", "dunlop", "olympus", "オリンパス", "タムロン", "tamron",
    "di iii", "パナソニック", "panasonic", "京セラ", "リョービ", "バーミックス", "bamix",
    "sony", "ソニー", "nikon", "ニコン", "canon", "キヤノン", "sigma", "シグマ",
    "バンダイ", "bandai", "figuarts", "フィギュアーツ", "仮面ライダー", "ドラゴンボール",
    "ガンダム", "プレミアムバンダイ", "タカラトミー", "tomix", "グリーンマックス", "kato",
    "アニプレックス", "aniplex", "fate", "ドクターエア", "ゼクシオ", "スリクソン", "srixon",
    "diesel", "ディーゼル", "gucci", "coach", "continental", "コンチネンタル", "marumi",
    "tetra", "テトラ", "アディダス", "adidas", "nike", "ナイキ", "ダイワ", "daiwa",
    "アンパンマン", "西川", "レゴ", "lego", "ヨネックス", "yonex", "ミズノ", "mizuno",
]
# 要カテゴリ許可・薬機/規制（初心者が出品許可を要する代表）
GATED_CATS = {"drugstore", "food", "beauty"}
GATED_WORDS = ["ミルク", "サプリ", "健康", "医薬", "化粧", "ドッグフード", "キャットフード",
               "ピュリナ", "purina", "ロイヤルカナン", "食品", "酒", "ワイン"]


def tokens(name):
    """日本語名から比較用トークン（英数字・カタカナ連・型番）を抽出。"""
    name = name.lower()
    toks = set(re.findall(r"[a-z0-9]{2,}", name))
    toks |= set(re.findall(r"[゠-ヿ]{2,}", name))   # カタカナ連
    toks |= set(re.findall(r"[一-鿿]{2,}", name))   # 漢字連
    return {t for t in toks if len(t) >= 2}


def name_match(amazon_name, supplier_name):
    """0..1 のトークン一致度（別モデル誤突合の検知）。"""
    a, b = tokens(amazon_name), tokens(supplier_name)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a)   # Amazon名のうち仕入先名に現れる割合


def brand_flag(name):
    n = name.lower()
    return any(b in n for b in BRANDS)


def gated_flag(name, cat):
    if cat in GATED_CATS:
        return True
    n = name.lower()
    return any(w.lower() in n for w in GATED_WORDS)


def ratio(r):
    try:
        return float(r["bb_confirmed"]) / float(r["buy"])
    except (ValueError, ZeroDivisionError):
        return 0


def is_qty_mismatch(r):
    rt = ratio(r)
    return rt > 2.5 or (rt > 1.8 and SET_RE.search(r.get("name", "")))


def net_at_bb(r):
    res = calculate(ProfitInput(
        wholesale_price=float(r["buy"]), amazon_price=float(r["bb_confirmed"]),
        category_key="default", size_key=r.get("size") or "standard_1",
        inbound_shipping=INB.get(r.get("size"), 250), other_costs=150))
    return res.net_profit, res.margin_rate


def main():
    yahoo = YahooShoppingClient(); rakuten = RakutenShoppingClient()
    liq = [r for r in csv.DictReader(open(OUT / "density_v2_gems_liquidity.csv"))
           if r["liquid"] == "True" and not is_qty_mismatch(r)]
    print(f"入口: クリーン流動性原石 {len(liq)}件")

    out = []
    for r in liq:
        name = r["name"]
        brand = brand_flag(name)
        gated = gated_flag(name, r.get("category", ""))
        # 名寄せ：仕入先名を再取得（安いソース優先で1件取れれば十分）
        sup_name = ""; sup_url = ""
        for cli in (yahoo, rakuten):
            try:
                hits = cli.search(jan_code=r["jan"], results=3)
            except Exception:
                hits = []
            for it in hits:
                if it.price and it.price > 0:
                    sup_name = it.name; sup_url = it.url
                    break
            if sup_name:
                break
        nm = name_match(name, sup_name) if sup_name else 0.0
        net, mg = net_at_bb(r)
        cap = float(r["buy"]); offers = int(r["offer_count"] or 999); ms = int(r["monthly_sales"] or 0)
        # スコア: 利益額 × 利益率 × 回転 ÷ 資本、相乗り余地で補正、名寄せで信頼度
        score = (net * mg * max(ms, 1)) / (cap ** 0.5) * (1.0 if offers <= 6 else 0.6) * (nm if nm > 0 else 0.4)
        clean = (not brand) and (not gated) and (nm >= 0.35)
        out.append({
            "採否": "候補" if clean else "除外",
            "除外理由": ("ブランド制限" if brand else "") + ("/薬機・許可" if gated else "") + ("/名寄せ低" if nm < 0.35 else ""),
            "商品名(Amazon)": name, "asin": r["asin"], "jan": r["jan"],
            "カテゴリ": r["category"], "仕入最安": int(cap), "仕入先名": sup_name[:40],
            "BuyBox実価格": int(float(r["bb_confirmed"])), "差(倍)": round(ratio(r), 2),
            "純利益": round(net), "利益率%": round(mg * 100, 1),
            "相乗り数": offers, "月販(推定)": ms, "名寄せ一致": round(nm, 2),
            "score": round(score), "仕入URL": sup_url,
        })

    out.sort(key=lambda x: (x["採否"] != "候補", -x["score"]))
    with open(OUT / "buy_shortlist.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

    cand = [x for x in out if x["採否"] == "候補"]
    print(f"罠フィルタ通過（買い候補）: {len(cand)}件 / 除外 {len(out)-len(cand)}件")
    print("=== 買い候補 上位15（スコア順）===")
    for x in cand[:15]:
        print(f"  利{x['純利益']:>5} 率{x['利益率%']:>4}% 相乗{x['相乗り数']:>2} 月販{x['月販(推定)']:>2} 資{x['仕入最安']:>6} 名寄{x['名寄せ一致']} {x['カテゴリ']:11}| {x['商品名(Amazon)'][:28]}")


if __name__ == "__main__":
    main()
