"""Sato-Scope Lite —— 利益判定エンジン Web UI（第1層 MVP）。

社長専用ローカルツール。卸価格・Amazon売値・カテゴリ・サイズ・送料を入れると
利益・利益率・ROI・損益分岐売値・判定（原石/あやしい/はずれ）を即表示します。

起動: code/ ディレクトリで `streamlit run app.py`

設計方針（タカシ）:
- このファイルは「画面」だけ。計算は一切しない（calc.profit に丸投げ）。
- 認証なし・DBなし・1人専用（YAGNI）。ローカル実行前提。
- 第2層（Keepa自動取得）が来ても、この画面の入力欄が自動入力に変わるだけ。
"""

import streamlit as st

from calc import fees
from calc.profit import (
    ProfitInput,
    calculate,
    VERDICT_GEM,
    VERDICT_SUSPICIOUS,
    VERDICT_MISS,
)

# 判定ごとの色（社長が一目で分かるように）
VERDICT_STYLE = {
    VERDICT_GEM: ("🟢", "#1b7f3b", "#e6f4ea"),        # 緑
    VERDICT_SUSPICIOUS: ("🟡", "#9a6b00", "#fff6e0"),  # 黄
    VERDICT_MISS: ("🔴", "#b00020", "#fde7ea"),        # 赤
}

st.set_page_config(page_title="Sato-Scope Lite｜利益判定", page_icon="💹", layout="wide")
st.title("💹 Sato-Scope Lite — Amazon物販 利益判定エンジン")
st.caption(
    "卸価格と Amazon 売値を入れると、利益・利益率・ROI・判定を即計算します。"
    "（第1層・ローカル実行・月額0円）"
)

# ─────────────────────────────────────────────────────────────
# サイドバー: 料率の出典と検証注意
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚠️ 数値の前提")
    st.markdown(
        "- 料率・FBA手数料は **2026年時点の Amazon.co.jp 公開料率の代表値**です。\n"
        "- **経理ハジメの検証前**の暫定値で、改定で変わる可能性があります。\n"
        "- 正確な判断の前に Seller Central の最新料金表と突き合わせてください。"
    )
    st.divider()
    st.subheader("判定の閾値")
    margin_th = st.slider("原石に必要な利益率（%）", 0, 50, 15) / 100.0
    profit_th = st.number_input("原石に必要な純利益（円）", min_value=0, value=500, step=100)


def render_verdict(result):
    """判定を色付きカードで表示。"""
    icon, fg, bg = VERDICT_STYLE.get(result.verdict, ("⚪", "#333", "#eee"))
    st.markdown(
        f"""
        <div style="background:{bg};border-radius:12px;padding:18px 20px;margin:8px 0;">
          <div style="font-size:28px;font-weight:700;color:{fg};">
            {icon} {result.verdict}
          </div>
          <div style="font-size:20px;color:{fg};margin-top:6px;">
            純利益 <b>{result.net_profit:,.0f} 円</b> ／
            利益率 <b>{result.margin_rate*100:,.1f}%</b> ／
            ROI <b>{result.roi*100:,.1f}%</b>
          </div>
          <div style="font-size:13px;color:#555;margin-top:4px;">
            損益分岐売値: {result.breakeven_price:,.0f} 円
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# タブ: 単品判定 / 複数まとめ判定
# ─────────────────────────────────────────────────────────────
tab_single, tab_batch = st.tabs(["🔎 単品判定", "📋 まとめ判定（複数行）"])

with tab_single:
    cat_choices = fees.category_choices()
    size_choices = fees.size_choices()

    col1, col2 = st.columns(2)
    with col1:
        wholesale = st.number_input("① 卸仕入価格（円）", min_value=0.0, value=1000.0, step=50.0)
        tax_incl = st.radio("卸価格の税区分", ["税込", "税抜"], horizontal=True) == "税込"
        amazon = st.number_input("② Amazon売値（円・税込）", min_value=0.0, value=2980.0, step=50.0)
    with col2:
        cat_key = st.selectbox(
            "③ カテゴリ", options=[k for k, _ in cat_choices],
            format_func=lambda k: dict(cat_choices)[k], index=2,
        )
        size_key = st.selectbox(
            "④ サイズ区分（FBA）", options=[k for k, _ in size_choices],
            format_func=lambda k: dict(size_choices)[k], index=1,
        )
        inbound = st.number_input("⑤ 仕入送料（円）", min_value=0.0, value=200.0, step=50.0)
        other = st.number_input("その他経費（円・任意）", min_value=0.0, value=0.0, step=50.0)

    result = calculate(ProfitInput(
        wholesale_price=wholesale,
        amazon_price=amazon,
        category_key=cat_key,
        size_key=size_key,
        inbound_shipping=inbound,
        other_costs=other,
        wholesale_price_is_tax_included=tax_incl,
        threshold_margin_rate=margin_th,
        threshold_net_profit_yen=profit_th,
    ))

    render_verdict(result)

    with st.expander("コスト内訳を見る", expanded=True):
        st.table({
            "項目": [
                "Amazon売値", "Amazon販売手数料", "FBA手数料",
                "仕入(税込)", "仕入送料", "その他経費", "── 純利益 ──",
            ],
            "金額(円)": [
                f"{result.amazon_price:,.0f}",
                f"-{result.referral_fee:,.0f}（{result.category_label} {result.referral_rate*100:.0f}%）",
                f"-{result.fba_fee:,.0f}（{result.size_label}）",
                f"-{result.wholesale_price_incl_tax:,.0f}",
                f"-{result.inbound_shipping:,.0f}",
                f"-{result.other_costs:,.0f}",
                f"{result.net_profit:,.0f}",
            ],
        })
        for note in result.notes:
            st.info(note)

with tab_batch:
    st.markdown(
        "複数商品をまとめて判定できます。下の表に貼り付け／編集してください。"
        "（カテゴリ・サイズは下の凡例キーで指定）"
    )
    import pandas as pd

    default_df = pd.DataFrame([
        {"商品名": "サンプルA", "卸価格": 1000, "Amazon売値": 2980,
         "カテゴリ": "home_kitchen", "サイズ": "standard_1", "仕入送料": 200, "その他": 0},
        {"商品名": "サンプルB", "卸価格": 2500, "Amazon売値": 2980,
         "カテゴリ": "home_kitchen", "サイズ": "standard_1", "仕入送料": 200, "その他": 0},
    ])
    edited = st.data_editor(default_df, num_rows="dynamic", use_container_width=True)

    rows = []
    for _, r in edited.iterrows():
        try:
            res = calculate(ProfitInput(
                wholesale_price=float(r["卸価格"]),
                amazon_price=float(r["Amazon売値"]),
                category_key=str(r["カテゴリ"]),
                size_key=str(r["サイズ"]),
                inbound_shipping=float(r["仕入送料"]),
                other_costs=float(r["その他"]),
                threshold_margin_rate=margin_th,
                threshold_net_profit_yen=profit_th,
            ))
            icon = VERDICT_STYLE.get(res.verdict, ("⚪",))[0]
            rows.append({
                "商品名": r["商品名"],
                "判定": f"{icon} {res.verdict}",
                "純利益(円)": round(res.net_profit),
                "利益率(%)": round(res.margin_rate * 100, 1),
                "ROI(%)": round(res.roi * 100, 1),
                "損益分岐売値(円)": round(res.breakeven_price),
            })
        except Exception as e:  # 入力ミスは行単位でスキップ表示
            rows.append({"商品名": r.get("商品名", "?"), "判定": f"⚠️ 入力エラー: {e}"})

    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    with st.expander("カテゴリ／サイズの指定キー一覧"):
        st.write("**カテゴリキー**", dict(fees.category_choices()))
        st.write("**サイズキー**", dict(fees.size_choices()))

st.divider()
st.caption(
    "第2層（Keepa自動取得）は社長の課金承認（§4.1）後に有効化されます。"
    " adapters/keepa.py の TODO を参照。"
)
