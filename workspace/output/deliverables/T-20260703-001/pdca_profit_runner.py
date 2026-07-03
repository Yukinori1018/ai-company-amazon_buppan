"""T-20260703-001 電脳せどりPDCA用 利益計算ランナー。

既存の実働エンジン（T-20260521-005 calc/profit.py + fees.py）を読み込み、
候補SKUの Plan（仕入判定）と、Do/Check（実売の3シナリオ）の純利益を実数で出す。
数値はでっち上げず、この1ファイルに前提を集約する。
"""
import sys
from pathlib import Path

# 実働エンジンのパスを通す
ENGINE = Path(__file__).resolve().parents[1] / "T-20260521-005" / "code"
sys.path.insert(0, str(ENGINE))

from calc.profit import ProfitInput, calculate, format_result_lines  # noqa: E402


def run(title, **kw):
    print("=" * 64)
    print(title)
    print("-" * 64)
    res = calculate(ProfitInput(**kw))
    for line in format_result_lines(res):
        print(line)
    print()
    return res


if __name__ == "__main__":
    # ─── Plan: サトルの実相場データで3候補を仕入れ判定 ───
    # inbound_shipping=FBA納品までの1個あたり送料按分、other_costs=ラベル/資材/保管/返品引当
    run(
        "候補A シルバニア 赤い屋根の大きなお家（本命／toys・large1）",
        wholesale_price=5300, amazon_price=9500,
        category_key="toys", size_key="large_1",
        inbound_shipping=250, other_costs=180,
    )
    run(
        "候補B 象印STAN.電気ケトル CK-PA08（比較・赤字リスク／home_kitchen→8%不可なのでelectronics相当）",
        wholesale_price=7400, amazon_price=9300,
        category_key="electronics", size_key="standard_2",
        inbound_shipping=250, other_costs=180,
    )
    run(
        "候補C デオナチュレ ソフトストーンW 3個セット（比較・薄利高回転／drugstore・small）",
        wholesale_price=2100, amazon_price=3070,
        category_key="drugstore", size_key="small",
        inbound_shipping=120, other_costs=120,
    )
