"""Sato-Scope Discovery — 利益ランキング UI（Streamlit プロトタイプ）。

起動: code/ ディレクトリで
    streamlit run app_discovery.py

設計方針（タカシ）:
- 計算もデータ取得も discovery / calc / adapters に任せ、このファイルは「表示」だけ。
- 02_mockup.html の質感（紺ヘッダ・サマリーカード・利益で色分けの表）を踏襲。
- サンプルデータで動いている間は画面上部に黄色バナーで「サンプル」と明示する
  （本物の利益数字と誤認させないため＝データの正直さ）。
- キー（YAHOO_APP_ID / KEEPA_API_KEY）が入ると自動で本番接続に切り替わる旨も表示。
"""

import os

import pandas as pd
import streamlit as st

from adapters.amazon_data import KeepaBackend, SampleBackend, get_backend
from adapters.yahoo_shopping import YahooShoppingClient
from discovery import pipeline
from discovery.presets import PRESETS, get_preset, preset_choices

st.set_page_config(page_title="Sato-Scope Discovery", layout="wide")

# ----- スタイル（mockup.html の配色を最小移植）-----------------------------
st.markdown(
    """
    <style>
      .ss-header {background:linear-gradient(135deg,#2c3e50,#34495e);color:#fff;
        padding:16px 22px;border-radius:10px;margin-bottom:14px;}
      .ss-header h1 {font-size:20px;margin:0;}
      .ss-header .sub {font-size:11px;opacity:.8;}
      .ss-sample {background:#fff3cd;border:1px solid #ffe066;color:#856404;
        padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px;}
      .ss-live {background:#e8f5e9;border:1px solid #a5d6a7;color:#2e7d32;
        padding:10px 14px;border-radius:6px;font-size:13px;margin-bottom:12px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="ss-header">
      <h1>Sato-Scope Discovery — 利益が出る商品の自動リサーチ（プロト）</h1>
      <div class="sub">仕入れ元起点(電脳せどり) / Amazon起点 の2モード · 利益計算は経理検証済みエンジン</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----- データソース状態の判定（キーの有無で本番/サンプル）-------------------
yahoo_live = bool(os.environ.get("YAHOO_APP_ID"))
keepa_live = bool(os.environ.get("KEEPA_API_KEY"))

if yahoo_live and not keepa_live:
    # 仕入れ元(Yahoo)=本物 / Amazon(Keepa)=サンプル の混在状態を正直に明示。
    st.markdown(
        '<div class="ss-live">'
        '<b>データソース状態（正直版）</b>：仕入れ元 Yahoo!ショッピング = <b>本番（実データ）</b> ／ '
        'Amazon売値・月販・ランキング = <b>サンプル（Keepa未契約）</b><br>'
        '⚠ いま表示される<b>純利益・利益率はAmazon側がダミー</b>のため「確定利益」ではありません。'
        'Keepa契約までは仕入れ元の実在候補確認用です。<br>'
        '⚠ <b>(い)仕入れ元起点</b>は本物JANをサンプルAmazonに突合するため'
        '<b>通常0件</b>になります（架空JANと一致しないのが正常）。実候補の一覧は'
        '次のKeepa契約で初めて利益付きランキングになります。'
        '</div>',
        unsafe_allow_html=True,
    )
elif yahoo_live or keepa_live:
    st.markdown(
        f'<div class="ss-live">本番データ接続中: '
        f'Yahoo={"ON(実データ)" if yahoo_live else "OFF(サンプル)"} / '
        f'Amazon(Keepa)={"ON(実データ)" if keepa_live else "OFF(サンプル)"}</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="ss-sample">⚠ サンプルデータで動作中です。表示される利益数字は'
        'デモ用のダミーであり、実在の相場ではありません。'
        '環境変数 YAHOO_APP_ID / KEEPA_API_KEY を設定すると本番データに切り替わります。</div>',
        unsafe_allow_html=True,
    )

# ----- 操作パネル -----------------------------------------------------------
with st.sidebar:
    st.header("検索条件")
    mode = st.radio(
        "モード",
        ["(い) 仕入れ元起点（電脳せどり）", "(あ) Amazon起点ディスカバリー"],
    )
    preset_key = st.selectbox(
        "プリセット（絞り込み条件）",
        options=[k for k, _ in preset_choices()],
        format_func=lambda k: get_preset(k).label,
    )
    st.caption("⚠ プリセット閾値はサトル監修前の暫定値です。")
    st.caption(get_preset(preset_key).description)

    query = ""
    if mode.startswith("(い)"):
        query = st.text_input("仕入れキーワード（空欄=サンプル全件）", "")
    assumed = 0.5
    if mode.startswith("(あ)"):
        assumed = st.slider("想定原価率（仕入元未特定時の仮置き）", 0.2, 0.9, 0.5, 0.05)

    run = st.button("リサーチ実行", type="primary")


# ----- 実行 -----------------------------------------------------------------
def _build_rows():
    amazon = get_backend()  # キー有無で Keepa/Sample 自動切替
    yahoo = YahooShoppingClient()
    if mode.startswith("(い)"):
        rows = pipeline.discover_from_supplier(
            query, preset_key=preset_key, amazon_backend=amazon, yahoo_client=yahoo
        )
        # Amazon側がサンプルだと突合0件になりやすい。実在の仕入れ候補を社長が
        # 確認できるよう、生の Yahoo 候補も併せて保持する（正直なフォールバック）。
        raw = yahoo.search(query, results=30)
        return rows, raw
    rows = pipeline.discover_from_amazon(
        preset_key=preset_key, amazon_backend=amazon,
        assumed_cost_rate=assumed, yahoo_client=yahoo,
    )
    return rows, []


if run or "ss_rows" not in st.session_state:
    try:
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = _build_rows()
    except NotImplementedError as e:
        st.error(f"本番バックエンドが未実装です: {e}")
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = [], []
    except Exception as e:  # noqa: BLE001  本番API障害時にUIごと落とさない
        st.error(f"取得エラー: {e}")
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = [], []

rows = st.session_state.get("ss_rows", [])
raw_yahoo = st.session_state.get("ss_raw_yahoo", [])

# ----- サマリーカード -------------------------------------------------------
if rows:
    gem = sum(1 for r in rows if r.verdict == "原石")
    avg_margin = sum(r.margin_rate for r in rows) / len(rows)
    top = rows[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("候補件数", f"{len(rows)} 件")
    c2.metric("原石（推奨）", f"{gem} 件")
    c3.metric("平均利益率", f"{avg_margin*100:.1f} %")
    c4.metric("トップ純利益", f"{int(top.net_profit):,} 円")

# ----- 生Yahoo候補（仕入れ元=本物。Amazon未突合でも実在を見せる）-------------
if raw_yahoo and mode.startswith("(い)"):
    with_jan = sum(1 for it in raw_yahoo if it.jan)
    live_note = "本番（実データ）" if not raw_yahoo[0].is_sample else "サンプル"
    st.subheader(f"仕入れ元の実在候補（Yahoo!ショッピング・{live_note}）")
    st.caption(
        f"取得 {len(raw_yahoo)} 件 / うち JAN付き {with_jan} 件"
        f"（{round(with_jan/len(raw_yahoo)*100)}%）。"
        "JANが付いている商品だけが将来 Amazon と突合できます。"
        "※この表は仕入れ元の実在確認用。Amazon売値・利益はKeepa契約後に付きます。"
    )
    raw_df = pd.DataFrame(
        [
            {
                "商品名": it.name,
                "Yahoo価格(円)": it.price,
                "JAN": it.jan or "（無し→突合不可）",
                "ポイント率(%)": it.point_rate,
                "ストア": it.store,
                "仕入元": it.url,
            }
            for it in raw_yahoo
        ]
    )
    st.dataframe(
        raw_df,
        use_container_width=True,
        height=320,
        column_config={
            "仕入元": st.column_config.LinkColumn("仕入元", display_text="開く"),
        },
    )
    st.divider()

# ----- 結果テーブル（Amazon突合済み・利益ランキング）-----------------------
if not rows:
    if raw_yahoo:
        st.info(
            "Amazonと突合できた利益ランキングは0件です。"
            "Amazon側がサンプルのため実在JANと一致しないのが原因で、これは正常な挙動です。"
            "Keepa契約後に、上の実在候補へAmazon売値・月販が付いて利益ランキングになります。"
        )
    else:
        st.info("条件に合う候補がありませんでした。プリセットを『広く拾う』にすると増えます。")
else:
    df = pd.DataFrame(
        [
            {
                "商品名": r.name,
                "仕入値(円)": r.supplier_price,
                "Amazon売値(円)": int(r.amazon_price),
                "純利益(円)": int(r.net_profit),
                "利益率(%)": round(r.margin_rate * 100, 1),
                "ROI(%)": round(r.roi * 100, 1),
                "月販推定": r.monthly_sales,
                "ランキング": r.sales_rank,
                "出品者数": r.offer_count,
                "在庫切れ率(%)": None if r.oos_rate_90d is None else round(r.oos_rate_90d * 100),
                "判定": r.verdict,
                "突合": r.match_status,
                "カテゴリ": r.category_label,
                "仕入元": r.supplier_url,
                "サンプル": "★" if r.is_sample else "",
            }
            for r in rows
        ]
    )

    # 並べ替え UI（既定は純利益降順 = パイプラインの出力順）
    sort_col = st.selectbox(
        "並べ替え", ["純利益(円)", "利益率(%)", "ROI(%)", "月販推定", "ランキング"], index=0
    )
    ascending = sort_col == "ランキング"  # ランキングだけは小さいほど良い
    df = df.sort_values(sort_col, ascending=ascending, na_position="last")

    def _hl(row):
        color = "#e8f5e9" if row["純利益(円)"] > 0 else "#ffebee"
        return [f"background-color:{color}"] * len(row)

    st.dataframe(
        df.style.apply(_hl, axis=1),
        use_container_width=True,
        height=480,
        column_config={
            "仕入元": st.column_config.LinkColumn("仕入元", display_text="開く"),
        },
    )
    st.caption(
        "判定『原石』=利益率15%以上かつ純利益500円以上 / 突合『Amazon起点(仕入元未特定)』"
        "の仕入値は想定原価率での仮置きです。"
    )
