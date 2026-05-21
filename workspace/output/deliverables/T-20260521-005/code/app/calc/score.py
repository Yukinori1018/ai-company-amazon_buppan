"""
おすすめスコアと判定ロジック
- 利益額・利益率・月販・Drop30 を組み合わせて 0〜100 のスコアを出す
- 副業初心者向けに「在庫リスクが低い」「利益が安定」を重視
"""
from typing import Optional


def calc_score(
    profit: int,                # MSS 利益額 (円)
    rate: float,                # MSS 利益率 (%)
    monthly_sales: int,         # 月販個数
    drop_30: int,               # 30日間ドロップ回数
    competitors: Optional[int] = None,  # 競合セラー数 (未取得なら None)
) -> int:
    """0〜100 のスコアを返す"""
    # 4要素を各 0〜25 にスケール
    s_profit = min(25.0, profit / 100)         # ¥2,500 で満点
    s_rate = min(25.0, rate * 1.5)             # 16.7% で満点
    s_sales = min(25.0, monthly_sales / 2.0)   # 50個/月 で満点
    s_drop = min(25.0, drop_30 * 1.0)          # 25回 で満点

    score = s_profit + s_rate + s_sales + s_drop

    # 競合数で減点
    if competitors is not None:
        if competitors > 20:
            score -= 15
        elif competitors > 10:
            score -= 5

    return max(0, min(100, round(score)))


def judge(profit: int, rate: float, monthly_sales: int, drop_30: int) -> str:
    """🟢 原石 / 🟡 要検討 / 🔴 除外 の判定"""
    if rate >= 15 and profit >= 500 and monthly_sales >= 5 and drop_30 >= 10:
        return "green"
    if rate >= 5 and profit >= 300:
        return "yellow"
    return "red"
