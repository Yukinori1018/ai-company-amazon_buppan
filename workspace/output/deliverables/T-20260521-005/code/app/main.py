"""
Sato-Scope FastAPI アプリケーション

エンドポイント:
- GET /         : モック画面（HTML）
- GET /search   : 利益商品を探す（JSON）
- GET /health   : 稼働状況確認
"""
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .adapters import keepa, rakuten, yahoo
from .calc.profit import ProfitInput, calc_all
from .calc.score import calc_score, judge
from .compliance.brand_warnings import check_brand

app = FastAPI(title="Sato-Scope", version="0.2.0")


@app.get("/health")
def health():
    """稼働状況。モックモードか実 API モードかを返す"""
    return {
        "ok": True,
        "version": "0.2.0",
        "use_mock": {
            "keepa": keepa.USE_MOCK,
            "rakuten": rakuten.USE_MOCK,
            "yahoo": yahoo.USE_MOCK,
        },
    }


@app.get("/search")
def search(
    min_monthly_sales: int = 5,
    min_drop_30: int = 5,
):
    """利益商品を探す（Discovery 型エンドポイント）"""
    products = keepa.find_profitable_products(min_monthly_sales, min_drop_30)
    results = []

    for k in products:
        r = rakuten.find_by_asin(k.asin)
        y = yahoo.find_by_asin(k.asin)

        # より安い仕入れ元を選択
        if r and y:
            if r.price <= y.price:
                best, source = r, "rakuten"
            else:
                best, source = y, "yahoo"
        elif r:
            best, source = r, "rakuten"
        elif y:
            best, source = y, "yahoo"
        else:
            continue  # 仕入れ元なし → スキップ

        # 真の利益計算（3パターン）
        p_in = ProfitInput(sell_price=k.price_amazon, cost=best.price)
        profits = calc_all(p_in)

        # スコア・判定
        score = calc_score(
            profit=profits["self_mss"].profit,
            rate=profits["self_mss"].rate,
            monthly_sales=k.monthly_sales,
            drop_30=k.drop_30,
        )
        j = judge(
            profits["self_mss"].profit, profits["self_mss"].rate,
            k.monthly_sales, k.drop_30,
        )
        warn = check_brand(k.title)

        results.append({
            "asin": k.asin,
            "title": k.title,
            "image_emoji": k.image_emoji,
            "amazon_price": k.price_amazon,
            "amazon_url": f"https://www.amazon.co.jp/dp/{k.asin}",
            "monthly_sales": k.monthly_sales,
            "drop_30": k.drop_30,
            "source": source,
            "source_price": best.price,
            "source_url": best.url,
            "point_rate": best.point_rate,
            "actual_price": round(best.price * (1 - best.point_rate / 100)),
            "fba_profit": profits["fba"].profit,
            "fba_rate": profits["fba"].rate,
            "mss_profit": profits["self_mss"].profit,
            "mss_rate": profits["self_mss"].rate,
            "score": score,
            "judge": j,
            "warning": warn,
        })

    # スコア降順
    results.sort(key=lambda x: -x["score"])
    return {"count": len(results), "results": results}


# 静的ファイル
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    """ルート: 静的 HTML を返す（あれば）"""
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return JSONResponse({
        "message": "Sato-Scope v0.2 Phase 1",
        "endpoints": ["/search", "/health"],
        "note": "static/index.html を配置するとモック画面が表示されます",
    })
