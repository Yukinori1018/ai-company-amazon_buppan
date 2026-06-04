"""Sato-Scope Discovery — 利益ランキング UI（Streamlit プロトタイプ）。

起動: code/ ディレクトリで
    streamlit run app_discovery.py

設計方針（タカシ）:
- 計算もデータ取得も discovery / calc / adapters に任せ、このファイルは「表示」だけ。
- 02_mockup.html の質感（紺ヘッダ・サマリーカード・利益で色分けの表）を踏襲。
- キー（YAHOO_APP_ID / KEEPA_API_KEY）の有無でデータソースを自動判定する。
  キーが無いときだけ「サンプル」バナー/列を出し、本番（Keepa/Yahoo実データ）接続時は
  サンプル系の文言を一切出さない（＝データの正直さ・本番中の矛盾表現を排除）。
- 本番でも残る正当な注意（FBAサイズ推定・月販推定・相場変動）は本番時も表示する。
"""

import os

import pandas as pd
import streamlit as st

from adapters.amazon_data import KeepaBackend, SampleBackend, get_backend
from adapters.yahoo_shopping import YahooShoppingClient
from discovery import pipeline
from discovery.presets import (
    PRESETS,
    amazon_category_choices,
    get_amazon_category,
    get_preset,
    preset_choices,
)

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

if yahoo_live and keepa_live:
    # 仕入れ元(Yahoo)=本物 / Amazon(Keepa)=本物 の両方本番。最終形。
    st.markdown(
        '<div class="ss-live">'
        '<b>データソース状態（正直版）</b>：仕入れ元 Yahoo!ショッピング = <b>本番（実データ）</b> ／ '
        'Amazon売値・月販・ランキング・出品者数・在庫切れ率 = <b>本番（Keepa実データ）</b><br>'
        '✅ <b>(い)仕入れ元起点</b>は本物のYahoo候補 × 本物のAmazonデータで'
        '<b>実利益ランキング</b>を出します。表示の純利益は「確定利益」に近い実勢ベースです。<br>'
        '⚠ ただし次の<b>推定誤差は残ります</b>：(1) FBA手数料はパッケージ寸法/重量からの'
        '<b>サイズ区分推定</b>（実区分とズレる場合あり）、(2) 月販は Keepa の実測値があれば実測、'
        '無い商品は<b>ランキングからの粗い推定</b>、(3) 相場は<b>変動</b>します（出品時に再確認を）。'
        '</div>',
        unsafe_allow_html=True,
    )
elif yahoo_live and not keepa_live:
    # 仕入れ元(Yahoo)=本物 / Amazon(Keepa)=サンプル の混在状態を正直に明示。
    st.markdown(
        '<div class="ss-live">'
        '<b>データソース状態（正直版）</b>：仕入れ元 Yahoo!ショッピング = <b>本番（実データ）</b> ／ '
        'Amazon売値・月販・ランキング = <b>サンプル（KEEPA_API_KEY未設定）</b><br>'
        '⚠ いま表示される<b>純利益・利益率はAmazon側がダミー</b>のため「確定利益」ではありません。'
        'KEEPA_API_KEY を設定すると Amazon 側も本番（実データ）に切り替わります。'
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
        _q_help = "" if keepa_live else "（空欄=サンプル全件）"
        query = st.text_input(f"仕入れキーワード{_q_help}", "")

    # (あ) Amazon起点：キーワード不要。カテゴリの売れ筋から原石を探す。
    amazon_cat_key = "home_kitchen"
    use_assumed = False
    assumed = 0.5
    if mode.startswith("(あ)"):
        amazon_cat_key = st.selectbox(
            "探索カテゴリ（売れ筋を自動収集）",
            options=[k for k, _ in amazon_category_choices()],
            format_func=lambda k: get_amazon_category(k).label,
        )
        if keepa_live:
            st.info(
                "🔎 キーワード不要。選んだカテゴリの **Amazon売れ筋ランキング** から最大10商品を"
                "自動収集し、Yahooで仕入元を当てて利益化します。"
                "1回の探索で **Keepaトークンを約20〜30消費**します（詳細10件＋売れ筋取得）。"
            )
        use_assumed = st.checkbox(
            "仕入元が見つからない商品も『想定原価率』で仮計算する（学習用・正直でない）",
            value=False,
            help="OFF（推奨）: 仕入元が無い商品は利益をでっち上げず『候補保留』にします。",
        )
        if use_assumed:
            assumed = st.slider("想定原価率（仮置き）", 0.2, 0.9, 0.5, 0.05)

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
    cat = get_amazon_category(amazon_cat_key)
    rows = pipeline.discover_from_amazon(
        preset_key=preset_key, amazon_backend=amazon,
        assumed_cost_rate=assumed, use_assumed_cost=use_assumed,
        yahoo_client=yahoo, category_id=cat.category_id, max_asins=10,
    )
    # 探索後の残トークンを表示用に session_state へ（Keepaバックエンドのみ）。
    st.session_state["ss_tokens_left"] = getattr(amazon, "last_tokens_left", None)
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
    needs_check = sum(1 for r in rows if not r.qty_reliable)
    avg_margin = sum(r.margin_rate for r in rows) / len(rows)
    top = rows[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("候補件数", f"{len(rows)} 件")
    c2.metric("原石🟢(数量一致)", f"{gem} 件")
    c3.metric("⚠️数量要確認", f"{needs_check} 件")
    c4.metric("平均利益率", f"{avg_margin*100:.1f} %")
    c5.metric("トップ純利益", f"{int(top.net_profit):,} 円")

# (あ)Amazon起点でKeepaを実消費したら、残トークンを正直に表示する。
if mode.startswith("(あ)") and keepa_live:
    _tok = st.session_state.get("ss_tokens_left")
    if _tok is not None:
        st.caption(f"🪙 Keepa残トークン: 約 {_tok} （この探索で詳細最大10件＋売れ筋取得を消費）")

# ----- 生Yahoo候補（仕入れ元=本物。Amazon未突合でも実在を見せる）-------------
if raw_yahoo and mode.startswith("(い)"):
    with_jan = sum(1 for it in raw_yahoo if it.jan)
    live_note = "本番（実データ）" if not raw_yahoo[0].is_sample else "サンプル"
    st.subheader(f"仕入れ元の実在候補（Yahoo!ショッピング・{live_note}）")
    keepa_on = bool(os.environ.get("KEEPA_API_KEY"))
    match_note = (
        "JANが付いている商品だけが Amazon（Keepa）と突合され、下の利益ランキングに乗ります。"
        "※トークン節約のため JAN付きの先頭10件のみ Amazon に問い合わせます。"
        if keepa_on
        else "JANが付いている商品だけが将来 Amazon と突合できます。"
        "※この表は仕入れ元の実在確認用。Amazon売値・利益はKEEPA_API_KEY設定後に付きます。"
    )
    st.caption(
        f"取得 {len(raw_yahoo)} 件 / うち JAN付き {with_jan} 件"
        f"（{round(with_jan/len(raw_yahoo)*100)}%）。" + match_note
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
        if os.environ.get("KEEPA_API_KEY"):
            st.info(
                "Amazonと突合できた利益ランキングは0件でした。"
                "考えられる理由：(1) JAN付き候補がAmazonに存在しない、"
                "(2) プリセットの絞り込み（ランキング/出品者数/利益率など）で全件除外、"
                "(3) この仕入値ではAmazon売値との差が小さく黒字化しない。"
                "プリセットを『広く拾う（学習用）』にすると、黒字なら全件表示されます。"
            )
        else:
            st.info(
                "Amazonと突合できた利益ランキングは0件です。"
                "Amazon側がサンプルのため実在JANと一致しないのが原因で、これは正常な挙動です。"
                "KEEPA_API_KEY設定後に、上の実在候補へAmazon売値・月販が付いて利益ランキングになります。"
            )
    else:
        st.info("条件に合う候補がありませんでした。プリセットを『広く拾う』にすると増えます。")
else:
    def _amazon_url(asin: str) -> str:
        # ASIN がある行だけ Amazon 商品ページへのリンクを張る（空なら "-"）。
        return f"https://www.amazon.co.jp/dp/{asin}" if asin else "-"

    def _qty_label(q):
        return "?" if q is None else q

    df = pd.DataFrame(
        [
            {
                "仕入元商品名": r.name,
                "Amazon商品名": r.amazon_name or "（取得不可）",
                "数量フラグ": r.qty_flag or "—",
                "数量(Yahoo/Amazon)": f"{_qty_label(r.supplier_qty)} / {_qty_label(r.amazon_qty)}",
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
                "Amazon": _amazon_url(r.asin),
                # 「サンプル」列は本番（Keepa実データ）時は出さない。下で keepa_live により列ごと落とす。
                "サンプル": "★" if r.is_sample else "",
            }
            for r in rows
        ]
    )
    # 本番（Keepa実データ）接続時は「サンプル」列ごと表示しない（矛盾表現の排除）。
    if keepa_live and "サンプル" in df.columns:
        df = df.drop(columns=["サンプル"])

    # 並べ替え UI（既定は純利益降順 = パイプラインの出力順）
    sort_col = st.selectbox(
        "並べ替え", ["純利益(円)", "利益率(%)", "ROI(%)", "月販推定", "ランキング"], index=0
    )
    ascending = sort_col == "ランキング"  # ランキングだけは小さいほど良い
    df = df.sort_values(sort_col, ascending=ascending, na_position="last")

    def _hl(row):
        # 数量フラグが警告（⚠️）の行は黄色で「要・個数目視」を強調（偽の原石の温床）。
        flag = str(row.get("数量フラグ", ""))
        if flag.startswith("⚠️"):
            color = "#fff8e1"  # 黄: 数量要確認/補正 → 原石にしない
        elif row["純利益(円)"] > 0:
            color = "#e8f5e9"  # 緑: 黒字かつ数量一致
        else:
            color = "#ffebee"  # 赤: 赤字
        return [f"background-color:{color}"] * len(row)

    st.dataframe(
        df.style.apply(_hl, axis=1),
        use_container_width=True,
        height=480,
        column_config={
            "仕入元": st.column_config.LinkColumn("仕入元", display_text="開く"),
            "Amazon": st.column_config.LinkColumn("Amazon", display_text="Amazonで開く"),
        },
    )
    st.caption(
        "🟢 判定『原石』=**数量が一致して信頼できる**行のうち利益率15%以上かつ純利益500円以上。 "
        "🟡『数量フラグ』に⚠️が付く行は **仕入元の個数と販売先(Amazon)の個数が違う／不明** な行です。"
        "『1個入りを仕入れて20個入りとして売る』ような誤突合を防ぐため、これらは原石にせず"
        "『要確認』に降格しています（"
        "数量補正の仕入値は1個あたり単価×Amazon個数での**推定**＝人間の目視照合が前提）。 "
        "必ず『仕入元商品名』と『Amazon商品名』の個数を見比べ、両リンクから現物を確認してください。"
    )
