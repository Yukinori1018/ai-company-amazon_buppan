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

from adapters.amazon_data import (
    KeepaBackend,
    KeepaRateLimitError,
    SampleBackend,
    get_backend,
)
# 仕入元クライアントは pipeline.default_supplier_client()（Yahoo+楽天）経由で使う。
from discovery import pipeline
from discovery.presets import (
    PRESETS,
    active_gem_criteria_text,
    amazon_category_choices,
    finder_preset_choices,
    get_amazon_category,
    get_finder_preset,
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
      <div class="sub">カテゴリから自動で探す（キーワード不要） ／ 仕入れ元から探す ／ 利益計算は検証済みエンジン</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ----- データソース状態の判定（キーの有無で本番/サンプル）-------------------
yahoo_live = bool(os.environ.get("YAHOO_APP_ID"))
keepa_live = bool(os.environ.get("KEEPA_API_KEY"))
# 楽天は新API仕様上、キー(app_id+access_key)に加え「許可ドメイン(RAKUTEN_REFERER)」が
# 揃って初めて本番に行ける（無いと403で弾かれる）。アダプタの is_live 判定と揃える。
rakuten_live = (
    bool(os.environ.get("RAKUTEN_APP_ID"))
    and bool(os.environ.get("RAKUTEN_ACCESS_KEY"))
    and bool(os.environ.get("RAKUTEN_REFERER"))
)
rakuten_has_keys = (
    bool(os.environ.get("RAKUTEN_APP_ID"))
    and bool(os.environ.get("RAKUTEN_ACCESS_KEY"))
)
# NETSEA(卸)はアクセストークン1本で本番に行ける（Authorization: Bearer）。
netsea_live = bool(os.environ.get("NETSEA_API_TOKEN"))

if yahoo_live and keepa_live:
    # 仕入れ元(Yahoo)=本物 / Amazon(Keepa)=本物 の両方本番。最終形。
    st.markdown(
        '<div class="ss-live">'
        '<b>データソース状態（正直版）</b>：仕入れ元 Yahoo!ショッピング = <b>本番（実データ）</b> ／ '
        'Amazon売値・月販・ランキング・出品者数・在庫切れ率 = <b>本番（Keepa実データ）</b><br>'
        '<b>仕入れ元から探す</b>モードは、実際のYahoo!ショッピングの候補と実際のAmazonデータを使って'
        '<b>利益ランキング</b>を表示します。表示される純利益は、実際の相場に近い数値です。<br>'
        'ただし、次の<b>推定による誤差は残ります</b>。(1) FBA手数料は、パッケージの寸法・重量からの'
        '<b>サイズ区分推定</b>（実区分とズレる場合あり）、(2) 月販は Keepa の実測値があれば実測、'
        '無い商品は<b>ランキングからのおおまかな推定</b>です。(3) 相場は<b>変動</b>します（出品前に再確認してください）。'
        '</div>',
        unsafe_allow_html=True,
    )
elif yahoo_live and not keepa_live:
    # 仕入れ元(Yahoo)=本物 / Amazon(Keepa)=サンプル の混在状態を正直に明示。
    st.markdown(
        '<div class="ss-live">'
        '<b>データソース状態（正直版）</b>：仕入れ元 Yahoo!ショッピング = <b>本番（実データ）</b> ／ '
        'Amazon売値・月販・ランキング = <b>サンプル（KEEPA_API_KEY未設定）</b><br>'
        'いま表示される<b>純利益・利益率は、Amazon側がサンプルのため正確ではありません</b>。'
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
        '<div class="ss-sample">サンプルデータで動作中です。表示される利益数字は'
        'デモ用のダミーであり、実在の相場ではありません。'
        '環境変数 YAHOO_APP_ID / KEEPA_API_KEY を設定すると本番データに切り替わります。</div>',
        unsafe_allow_html=True,
    )

# ----- 仕入れ先（複数）の本番/サンプル状態（Yahoo + 楽天 の2本）----------------
# 仕入元が2本になると同JANで最安の仕入値を採れるため、突合の母数＝原石の歩留まりが上がる。
_yahoo_badge = "ON（実データ）" if yahoo_live else "OFF（サンプル）"
if rakuten_live:
    _rakuten_badge = "ON（実データ）"
elif rakuten_has_keys:
    # キーはあるがドメイン未登録＝403で弾かれるためサンプル運用。社長の次アクションを明示。
    _rakuten_badge = "キー有・ドメイン未登録（サンプル）"
else:
    _rakuten_badge = "OFF（サンプル）"
_netsea_badge = "ON（実データ）" if netsea_live else "未設定（サンプル）"
st.markdown(
    f'<div class="ss-live">'
    f'<b>仕入れ先（突合の対象）</b>：Yahoo!ショッピング = <b>{_yahoo_badge}</b> ／ '
    f'楽天市場 = <b>{_rakuten_badge}</b> ／ '
    f'NETSEA(卸) = <b>{_netsea_badge}</b><br>'
    f'仕入れ先が3本あると、同じJANで<b>最も安い有効な仕入値</b>を自動採用し、'
    f'Yahoo/楽天に無い商品も<b>NETSEA(卸)</b>で拾えるため<b>原石候補の母数が広がります</b>。'
    f'卸（NETSEA）は同じJANコードで最安値になりやすく、黒字と判定される商品が増えます。'
    + (
        '<br>楽天は <b>RAKUTEN_REFERER</b>（楽天デベロッパー管理画面で登録した'
        '「許可するWebサイト」ドメイン）が未設定のためサンプル動作です。'
        'ドメインを1つ登録し同じ値を .env の RAKUTEN_REFERER に入れると本番に切り替わります。'
        if (rakuten_has_keys and not rakuten_live) else ""
    )
    + (
        '<br>NETSEA は <b>NETSEA_API_TOKEN</b> が未設定のため、サンプル動作です。'
        'NETSEAマイページ（https://www.netsea.jp/account/）のAPI設定画面でアクセストークンを発行し、'
        '.env の NETSEA_API_TOKEN に入れると本番（実データ・卸価格）に切り替わります。'
        if not netsea_live else ""
    )
    + '</div>',
    unsafe_allow_html=True,
)

# =============================================================================
# PoiPoi風 3フェーズ縦並びレイアウト（2026-06-09 タカシ・PoiPoiポケットに寄せる改修）
#   ① 抽出条件(Phase1) → ② 取り込み/実行(Phase2) → ③ 絞り込み&最終判断(Phase3)
# 既存の (い)キーワード/(あ)カテゴリ自動/NETSEA卸/売れ筋 は Phase1 の「抽出方法」に統合。
# Keepa検索URL貼り付けは上級者向け expander として追加（任意・両立）。
# =============================================================================
from discovery import keepa_query_url  # noqa: E402  (URL貼り付けパーサ)

# 抽出方法（Phase1 の主役）。PoiPoi同様「条件で自動抽出」を主役にしつつ既存機能を温存。
MODE_FINDER = "カテゴリから自動で探す（キーワード不要・おすすめ）"
MODE_KEYWORD = "キーワードで探す"
MODE_NETSEA = "卸から自動で探す（NETSEA・キーワード不要）"
MODE_LEGACY = "Amazon売れ筋から探す"
MODE_KEEPA_URL = "Keepaで作った検索条件を貼り付ける"

st.markdown("## ① 抽出条件（Phase 1：対象を絞る）")
st.caption(
    "PoiPoiポケットと同じ考え方です。まず Amazon側で「出せば売れそうな中位帯」を条件で絞り込みます。"
    "下の抽出方法を選び、必要なら条件プリセットを変えてください。"
)

mode = st.radio(
    "抽出方法を選ぶ",
    [MODE_FINDER, MODE_KEYWORD, MODE_NETSEA, MODE_LEGACY, MODE_KEEPA_URL],
    index=0,
)

is_finder = mode == MODE_FINDER
is_netsea = mode == MODE_NETSEA
is_legacy_amazon = mode == MODE_LEGACY
is_keyword = mode == MODE_KEYWORD
is_keepa_url = mode == MODE_KEEPA_URL

# モード別の1行ヘルプ。
if is_finder:
    st.caption("**カテゴリを選ぶだけ**（キーワード不要）。中位ランク帯の有望商品を条件で自動抽出します。PoiPoiの Phase1 に最も近い動線です。")
elif is_keyword:
    st.caption("**キーワードを入力**して、楽天・Yahooの仕入元とAmazonの価格差を探します。")
elif is_netsea:
    st.caption("**NETSEAの承認サプライヤーの商品を一覧取得**（キーワード不要）。卸価格でAmazonと突合して黒字候補をランキングします。")
elif is_legacy_amazon:
    st.caption("選んだカテゴリのAmazon**売れ筋上位**を取得します（競争が激しく赤字になりやすいモードです）。")
else:
    st.caption("Keepaの Product Finder で作った検索条件（SHOW API QUERY のURL/JSON）を貼り付けて、その条件で抽出します。")

query = ""
finder_preset_key = "finder_genseki_beginner"
preset_key = "hunting_beginner"
amazon_cat_key = "home_kitchen"
use_assumed = False
assumed = 0.5
keepa_url_selection = None  # 上級者URL貼り付けでパースした selection（あれば優先）
netsea_supplier_ids = None
netsea_max_suppliers = 10
netsea_max_items = 100
netsea_max_jan = 100

col_left, col_right = st.columns([3, 2])

with col_left:
    # ── キーワードモード ──
    if is_keyword:
        _q_help = "" if keepa_live else "（空欄=サンプル全件）"
        query = st.text_input(
            f"仕入れキーワード{_q_help}",
            "",
            placeholder="例: アンパンマン ブロック / ○○ シャンプー など",
            help="商品名・ブランド名・型番などを入力してください。",
        )
        preset_key = st.selectbox(
            "プリセット（絞り込み条件）",
            options=[k for k, _ in preset_choices()],
            format_func=lambda k: get_preset(k).label,
        )
        st.caption(get_preset(preset_key).description)

    # ── カテゴリ自動（Finder）モード ──
    elif is_finder:
        finder_preset_key = st.selectbox(
            "原石プリセット（抽出条件）",
            options=[k for k, _ in finder_preset_choices()],
            format_func=lambda k: get_finder_preset(k).label,
            help="『PoiPoi標準』を選ぶと、社長提供動画の自動化せどり基準（出品者2人以上×3,000円以上×Amazon在庫切れ×ランク5〜15万位）で抽出します。",
        )
        st.caption(get_finder_preset(finder_preset_key).description)
        amazon_cat_key = st.selectbox(
            "探索カテゴリ",
            options=[k for k, _ in amazon_category_choices()],
            format_func=lambda k: get_amazon_category(k).label,
            help="いくつか試して、原石が出やすいカテゴリを見つけてください。",
        )

    # ── 売れ筋トップ（旧）モード ──
    elif is_legacy_amazon:
        preset_key = st.selectbox(
            "プリセット（絞り込み条件）",
            options=[k for k, _ in preset_choices()],
            format_func=lambda k: get_preset(k).label,
        )
        st.caption(get_preset(preset_key).description)
        amazon_cat_key = st.selectbox(
            "探索カテゴリ",
            options=[k for k, _ in amazon_category_choices()],
            format_func=lambda k: get_amazon_category(k).label,
        )

    # ── Keepa URL 貼り付け（上級者）モード ──
    elif is_keepa_url:
        finder_preset_key = st.selectbox(
            "利益フィルタに使うプリセット（抽出条件はURL優先）",
            options=[k for k, _ in finder_preset_choices()],
            format_func=lambda k: get_finder_preset(k).label,
            help="抽出条件は貼り付けたURLを使い、利益率/利益額の原石判定だけこのプリセットの値を使います。",
        )
        with st.expander("▼ Keepaで作った検索条件URL/JSONを貼り付ける（任意）", expanded=True):
            st.caption(
                "Keepaの Product Finder で条件を作り『SHOW API QUERY』を押すと出るURL、"
                "または selection の JSON をそのまま貼り付けてください。"
                "（通常はこの貼り付けは不要です。上の『カテゴリから自動で探す』だけで完結します）"
            )
            _pasted = st.text_area(
                "KeepaのURL または selection JSON",
                "",
                height=120,
                placeholder='https://api.keepa.com/query?...&selection={...}  または  {"current_SALES_gte":50000,...}',
            )
            if _pasted.strip():
                try:
                    keepa_url_selection = keepa_query_url.parse_keepa_query(_pasted)
                    st.success(
                        "条件を読み取りました： "
                        + keepa_query_url.describe_selection(keepa_url_selection)
                    )
                except keepa_query_url.KeepaQueryParseError as _pe:
                    st.error(f"貼り付け内容を読み取れませんでした：{_pe}")

    # ── NETSEA 卸モード ──
    elif is_netsea:
        preset_key = st.selectbox(
            "プリセット（絞り込み条件）",
            options=[k for k, _ in preset_choices()],
            format_func=lambda k: get_preset(k).label,
        )
        st.caption(get_preset(preset_key).description)
        try:
            _ns = pipeline.default_netsea_client()
            _suppliers = _ns.list_suppliers()
        except Exception as _e:  # noqa: BLE001
            _suppliers = []
            st.caption(f"サプライヤー一覧の取得に失敗: {_e}")
        _sup_label = {s["id"]: f'{s["name"]}（ID:{s["id"]}）' for s in _suppliers}
        st.caption(
            f"承認サプライヤー {len(_suppliers)} 社"
            + ("（サンプル擬似一覧）" if not netsea_live else "（本番）")
        )
        _scope = st.radio("対象サプライヤー", ["承認全社", "選んで指定"], index=0)
        if _scope == "選んで指定" and _suppliers:
            _picked = st.multiselect(
                "対象にするサプライヤー",
                options=[s["id"] for s in _suppliers],
                format_func=lambda i: _sup_label.get(i, str(i)),
            )
            netsea_supplier_ids = _picked or None
        netsea_max_suppliers = st.slider(
            "対象にする会社数の上限", 1, max(1, max(10, len(_suppliers))), 10,
            help="多いほど多くの商品を調べられますが、取得時間とKeepaのトークン消費が増えます。",
        )
        netsea_max_items = st.slider(
            "1社あたりの取得商品数の上限", 20, 300, 100, 20,
        )
        netsea_max_jan = st.slider(
            "Amazonと突合するJAN数の上限（トークン予算）", 10, 200, 100, 10,
            help="10JANでKeepa約1回の問い合わせ。多いほどトークンを消費します。",
        )

with col_right:
    # 仕入元未特定の商品も想定原価率で仮計算するか（Amazon起点系で共通）。
    if is_finder or is_legacy_amazon or is_keepa_url:
        use_assumed = st.checkbox(
            "仕入元が見つからない商品も「想定原価率」で仮計算する（学習用・実数値ではありません）",
            value=False,
            help="OFF（推奨）: 仕入元が無い商品は、利益を仮計算せず「候補保留」にします。",
        )
        if use_assumed:
            assumed = st.slider("想定原価率（仮置き）", 0.2, 0.9, 0.5, 0.05)
            st.markdown(
                '<div style="color:#c62828;font-weight:bold;font-size:12px;">'
                '※ これは推定値であり、実在する仕入先ではありません。'
                f'仕入値＝Amazon売値×{int(assumed*100)}%の仮置きで、利益数値も架空です。'
                '</div>',
                unsafe_allow_html=True,
            )

st.markdown("## ② 取り込み・実行（Phase 2：価格差を自動計算）")
st.caption(
    "選んだ条件で Amazon と仕入元を突合し、利益を自動計算します。"
    "PoiPoiの『インポート→自動価格差計算』にあたる工程を、このボタン1つで行います。"
)
run = st.button("リサーチ実行", type="primary")


# ----- 実行 -----------------------------------------------------------------
def _build_rows():
    amazon = get_backend()  # キー有無で Keepa/Sample 自動切替
    # 仕入元は Yahoo + 楽天 の2本（突合の網を広げる）。各クライアントはキー無しなら
    # 自前でサンプルへフォールバックするため、片方だけ本番でも安全に動く。
    supplier = pipeline.default_supplier_client()
    if is_keyword:
        rows = pipeline.discover_from_supplier(
            query, preset_key=preset_key, amazon_backend=amazon, yahoo_client=supplier
        )
        # (い)でも Keepa を突合で実消費する。残/消費トークンを正直に表示用へ保持。
        st.session_state["ss_tokens_left"] = getattr(amazon, "last_tokens_left", None)
        st.session_state["ss_tokens_consumed"] = getattr(amazon, "last_tokens_consumed", None)
        # Amazon側がサンプルだと突合0件になりやすい。実在の仕入れ候補を社長が
        # 確認できるよう、生の仕入れ候補（Yahoo+楽天）も併せて保持する（正直なフォールバック）。
        raw = supplier.search(query, results=60)
        return rows, raw

    if is_netsea:
        # (う) 卸起点：NETSEA承認サプライヤーの棚卸し → 卸価格でAmazon突合 → ランキング。
        netsea = pipeline.default_netsea_client()
        rows, cov = pipeline.discover_from_netsea(
            preset_key=preset_key,
            supplier_ids=netsea_supplier_ids,
            amazon_backend=amazon,
            netsea_client=netsea,
            max_suppliers=netsea_max_suppliers,
            max_items_per_supplier=netsea_max_items,
            max_jan_lookups=netsea_max_jan,
        )
        st.session_state["ss_netsea_cov"] = cov
        st.session_state["ss_tokens_left"] = getattr(amazon, "last_tokens_left", None)
        st.session_state["ss_tokens_consumed"] = getattr(amazon, "last_tokens_consumed", None)
        return rows, []

    if is_keepa_url and keepa_url_selection is None:
        # 上級者URLモードだが貼り付け未／パース失敗。勝手に別条件で探索しない（正直）。
        return [], []

    cat = get_amazon_category(amazon_cat_key)
    if is_keepa_url and keepa_url_selection is not None:
        # (上級者) 貼り付けた Keepa selection をそのまま Product Finder に流す。
        rows = pipeline.discover_by_finder(
            finder_preset_key=finder_preset_key,
            override_selection=keepa_url_selection,
            amazon_backend=amazon, yahoo_client=supplier,
            use_assumed_cost=use_assumed, assumed_cost_rate=assumed,
            max_asins=15,
        )
    elif is_finder:
        # (あ) 原石オートサーチ：Keepa Product Finder で条件抽出 → Yahoo突合。
        rows = pipeline.discover_by_finder(
            finder_preset_key=finder_preset_key,
            category_ids=[cat.category_id],
            amazon_backend=amazon, yahoo_client=supplier,
            use_assumed_cost=use_assumed, assumed_cost_rate=assumed,
            max_asins=15,
        )
    else:
        # (あ旧) 売れ筋トップ。
        rows = pipeline.discover_from_amazon(
            preset_key=preset_key, amazon_backend=amazon,
            assumed_cost_rate=assumed, use_assumed_cost=use_assumed,
            yahoo_client=supplier, category_id=cat.category_id, max_asins=15,
        )
    # 探索後の消費/残トークンを表示用に session_state へ（Keepaバックエンドのみ）。
    st.session_state["ss_tokens_left"] = getattr(amazon, "last_tokens_left", None)
    st.session_state["ss_tokens_consumed"] = getattr(amazon, "last_tokens_consumed", None)
    return rows, []


if run or "ss_rows" not in st.session_state:
    try:
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = _build_rows()
    except KeepaRateLimitError as e:
        # Keepa のトークン上限（混雑）。赤いトレースバックでなく、待てば直ることを親切に案内。
        _wait = getattr(e, "retry_after", None)
        _wait_txt = f"目安 約{_wait}秒。" if _wait else "目安 30〜60秒。"
        st.warning(
            "**Keepaのトークン上限に達しました（混雑）。**\n\n"
            f"{_wait_txt} しばらく置いてから、もう一度『リサーチ実行』を押してください。"
            "**1回の取得件数を減らす**（プリセットを絞る／探索カテゴリを変える）と"
            "上限に当たりにくく安定します。\n\n"
            "※ これはエラーではなく、Keepa の無料トークン（20/分）を使い切った一時的な状態です。"
            "時間をおけば自動で回復します。"
        )
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = [], []
    except NotImplementedError as e:
        st.error(f"本番バックエンドが未実装です: {e}")
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = [], []
    except Exception as e:  # noqa: BLE001  本番API障害時にUIごと落とさない
        # 429 が requests.HTTPError 等で漏れてくる場合も「混雑」として親切に拾う。
        _msg = str(e)
        if "429" in _msg or "Too Many Requests" in _msg:
            st.warning(
                "**Keepa・仕入れ元APIが混雑しています（レート上限の可能性）。**\n\n"
                "30〜60秒ほど置いてから、もう一度『リサーチ実行』を押してください。"
                "1回の取得件数を減らすと安定します。"
            )
        else:
            st.error(f"取得エラー: {_msg}")
        st.session_state["ss_rows"], st.session_state["ss_raw_yahoo"] = [], []

rows = st.session_state.get("ss_rows", [])
raw_yahoo = st.session_state.get("ss_raw_yahoo", [])

# ----- サマリーカード -------------------------------------------------------
# サマリーは「実仕入元が付いた行（実利益が計算できる行）」だけで集計する。
# 仕入元未特定の保留行（利益0・仮なし）を平均に混ぜると数字が誤解を招くため除外。
_scored = [
    r for r in rows
    if r.supplier_price is not None
    and r.match_status != pipeline.MATCH_SUSPECT_MISMATCH  # 別商品の疑いは集計から除外
]
if _scored:
    gem = sum(1 for r in _scored if r.verdict == "原石")
    needs_check = sum(1 for r in _scored if not r.qty_reliable)
    avg_margin = sum(r.margin_rate for r in _scored) / len(_scored)
    top = max(_scored, key=lambda r: r.net_profit)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("実仕入元あり候補", f"{len(_scored)} 件")
    c2.metric("原石（数量一致）", f"{gem} 件")
    c3.metric("数量要確認", f"{needs_check} 件")
    c4.metric("平均利益率", f"{avg_margin*100:.1f} %")
    c5.metric("トップ純利益", f"{int(top.net_profit):,} 円")

# ----- (う) 卸起点のカバレッジ正直表示（消費トークン・未処理を隠さない）-------
if is_netsea:
    cov = st.session_state.get("ss_netsea_cov")
    if cov is not None:
        _tok_txt = (
            f"約{cov.keepa_tokens_consumed}"
            if cov.keepa_tokens_consumed is not None
            else f"Keepa問い合わせ{cov.keepa_lookups}JAN相当"
        )
        st.markdown(
            '<div class="ss-live">'
            f'<b>処理状況</b>：承認済み <b>{cov.total_suppliers}社</b> 中 '
            f'<b>{cov.scanned_suppliers}社</b> を処理 ／ 取得商品 <b>{cov.fetched_items}件</b> ／ '
            f'JAN突合 <b>{cov.matched_jans}/{cov.jan_items}件</b> ／ '
            f'消費トークン <b>{_tok_txt}</b> ／ 未処理 <b>{cov.remaining_suppliers}社</b>'
            + ('（上限に達したため打ち切りました。残りは上限を上げて再実行してください）' if cov.truncated else '（全件処理済み）')
            + '</div>',
            unsafe_allow_html=True,
        )
        for n in cov.notes:
            st.caption(f"注意: {n}")

# Keepa接続状態を正直に表示する（全モード共通）。
# ★バグ修正(2026-06-05)：以前は「消費トークン」をオフライン判定の代理にしていたため、
#   突合が0件で消費=0/該当ヒット無しのとき接続中なのに『オフライン』と誤表示していた。
#   接続中(=KEEPA_API_KEY あり)なら必ず「接続中」と出す。残トークンは取得できた時だけ併記。
if keepa_live:
    _tok = st.session_state.get("ss_tokens_left")
    _con = st.session_state.get("ss_tokens_consumed")
    if is_finder:
        _src = "Finder抽出＋詳細最大15件"
    elif is_netsea:
        _src = "卸の商品取得→JAN突合（実価格取得）"
    elif is_legacy_amazon:
        _src = "売れ筋取得＋詳細最大15件"
    else:
        _src = "JAN突合（実価格取得）"
    _tok_txt = f"残 約 {_tok}" if _tok is not None else "残トークン不明"
    _con_txt = f"消費 約{_con} / " if _con is not None else ""
    st.caption(f"Keepa接続中（実データ）｜{_con_txt}{_tok_txt} （この探索で{_src}）")
else:
    st.caption("Keepaオフライン（KEEPA_API_KEY 未設定＝サンプル動作）")

# ----- 生Yahoo候補（仕入れ元=本物。Amazon未突合でも実在を見せる）-------------
if raw_yahoo and is_keyword:
    with_jan = sum(1 for it in raw_yahoo if it.jan)
    live_note = "本番（実データ）" if not raw_yahoo[0].is_sample else "サンプル"
    _srcs = sorted({getattr(it, "source", "Yahoo") for it in raw_yahoo})
    st.subheader(f"仕入れ元の候補一覧（{ '・'.join(_srcs) }・{live_note}）")
    keepa_on = bool(os.environ.get("KEEPA_API_KEY"))
    match_note = (
        "JANコードが付いている商品だけがAmazon（Keepa）と突合され、下の利益ランキングに表示されます。"
        "※トークン節約のため、JAN付きの先頭10件のみAmazonに問い合わせます。"
        if keepa_on
        else "JANコードが付いている商品だけが、今後Amazonと突合できます。"
        "※この表は仕入れ元の実在確認用。Amazon売値・利益はKEEPA_API_KEY設定後に付きます。"
    )
    st.caption(
        f"取得 {len(raw_yahoo)} 件 / うち JAN付き {with_jan} 件"
        f"（{round(with_jan/len(raw_yahoo)*100)}%）。" + match_note
    )
    raw_df = pd.DataFrame(
        [
            {
                "仕入元": getattr(it, "source", "Yahoo"),
                "商品名": it.name,
                "価格(円)": it.price,
                "JAN": it.jan or "（無し・突合不可）",
                "ポイント率(%)": it.point_rate,
                "ストア": it.store,
                "リンク": it.url,
            }
            for it in raw_yahoo
        ]
    )
    st.dataframe(
        raw_df,
        use_container_width=True,
        height=320,
        column_config={
            "リンク": st.column_config.LinkColumn("リンク", display_text="開く"),
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
                "(2) プリセットの絞り込み条件（ランキング・出品者数・利益率など）で全件が除外された、"
                "(3) この仕入値ではAmazon売値との差が小さく黒字化しない。"
                "プリセットを「広く拾う（学習用）」にすると、黒字の商品はすべて表示されます。"
            )
        else:
            st.info(
                "Amazonと突合できた利益ランキングは0件です。"
                "Amazon側がサンプルのため実在JANと一致しないのが原因で、これは正常な挙動です。"
                "KEEPA_API_KEY設定後に、上の実在候補へAmazon売値・月販が付いて利益ランキングになります。"
            )
    elif is_netsea:
        st.info(
            "卸起点の棚卸しでAmazon突合できた黒字候補は今回0件でした（正直な結果）。"
            "考えられる理由：(1) 棚卸しした商品にJANが付いていない／Amazonに存在しない、"
            "(2) この卸価格でもAmazon売値との差が小さく黒字化しない、"
            "(3) 上限（会社数・商品数・JAN数）で対象を絞り過ぎた。"
            "対策：上の上限スライダーを上げる、対象サプライヤーを増やす、プリセットを緩める、などをお試しください。"
            "上部のカバレッジで『未処理◯社』が残っている場合は、上限を上げて再実行してください。"
        )
    elif is_finder:
        st.info(
            "条件に合う原石が今回は見つかりませんでした（正直な結果）。"
            "考えられる理由：(1) Product Finder の条件（中位ランク×出品者2〜10人×価格帯）に"
            "合うASINがこのカテゴリで少ない、(2) 抽出ASINがYahooで仕入元に当たらない、"
            "(3) 仕入元が見つかっても黒字にならない。対策：別カテゴリに変える、または条件プリセットをより緩いものに変えてください。"
        )
    else:
        st.info("条件に合う候補がありませんでした。プリセットを「広く拾う」にすると候補が増えます。")
else:
    def _amazon_url(asin: str) -> str:
        # ASIN がある行だけ Amazon 商品ページへのリンクを張る（空なら "-"）。
        return f"https://www.amazon.co.jp/dp/{asin}" if asin else "-"

    def _qty_label(q):
        return "?" if q is None else q

    # ── 行を「実仕入元あり」と「仕入元未特定（参考）」に分離（honesty-first・社長FB対応）──
    # 仕入元未特定＝Amazon起点で実在の仕入元が当たらなかった行（supplier_price is None）。
    # 偽の利益（50%仮置き等）を本表に混ぜず、別セクションに利益数値抜きで隔離する。
    # 別商品の疑い（JAN誤登録）行はランキングから完全に隔離する（社長が買い間違える事故防止）。
    suspect_rows = [
        r for r in rows if r.match_status == pipeline.MATCH_SUSPECT_MISMATCH
    ]
    matched_rows = [
        r for r in rows
        if r.supplier_price is not None
        and r.match_status != pipeline.MATCH_SUSPECT_MISMATCH
    ]
    unmatched_rows = [
        r for r in rows
        if r.supplier_price is None and r.match_status == pipeline.AMAZON_ONLY
    ]

    # =====================================================================
    # ③ 絞り込み & 最終判断（Phase 3：PoiPoiの動的フィルタ＋最悪相場シミュレーション）
    # =====================================================================
    # PoiPoi同様、計算済みの結果テーブルに後段フィルタ（利益額/月販/利益率レンジ）をかける。
    # 重要：ここは「計算済み行の絞り込み」だけ。利益はすべて calc/profit.py が算出済み。
    st.markdown("## ③ 絞り込み・最終判断（Phase 3）")
    st.caption(
        "PoiPoiの『利益商品の絞り込み』にあたる工程です。下のフィルタは計算済みの結果を絞るだけで、"
        "利益額の計算は検証済みエンジンが行っています（このフィルタで数字は変わりません）。"
    )

    # 低リスク版ワンクリック（資料: 利益額≥500・上限売価≤10,000）。
    if "pf_low_risk" not in st.session_state:
        st.session_state["pf_low_risk"] = False
    if st.button("低リスク版を適用（利益額≥500円・上限売価≤10,000円）"):
        st.session_state["pf_low_risk"] = True

    fc1, fc2, fc3, fc4 = st.columns(4)
    _low = st.session_state.get("pf_low_risk", False)
    with fc1:
        f_min_profit = st.number_input(
            "利益額の下限（円）", value=(500 if _low else 0), step=100, min_value=0,
            help="この純利益額より下の行を隠します。PoiPoi標準は3,000円、低リスク版は500円。",
        )
    with fc2:
        f_min_sales = st.number_input(
            "月間販売数の下限（個）", value=0, step=1, min_value=0,
            help="推定月販がこの個数より下の行を隠します。PoiPoi標準は10個。",
        )
    with fc3:
        f_margin = st.slider(
            "利益率レンジ（%）", 0, 100, (0, 100),
            help="この利益率レンジから外れる行を隠します。PoiPoi標準は8〜30%。",
        )
    with fc4:
        f_max_price = st.number_input(
            "上限売価（円・0=無制限）", value=(10000 if _low else 0), step=1000, min_value=0,
            help="Amazon売値がこの金額より高い行を隠します。低リスク版は10,000円。",
        )

    def _passes_post_filter(r) -> bool:
        # すべて「計算済みの値の比較」だけ（再計算しない）。
        if r.net_profit < f_min_profit:
            return False
        if r.monthly_sales is not None and r.monthly_sales < f_min_sales:
            return False
        mr = r.margin_rate * 100
        if mr < f_margin[0] or mr > f_margin[1]:
            return False
        if f_max_price > 0 and r.amazon_price > f_max_price:
            return False
        return True

    _matched_before = len(matched_rows)
    matched_rows = [r for r in matched_rows if _passes_post_filter(r)]
    if _matched_before:
        st.caption(
            f"後段フィルタ適用：{_matched_before} 件中 **{len(matched_rows)} 件**を表示中"
            + ("（低リスク版ON）" if _low else "")
        )

    if matched_rows:
        df = pd.DataFrame(
            [
                {
                    "仕入先": r.supplier_source or "—",
                    "仕入元商品名": r.name,
                    "Amazon商品名": r.amazon_name or "（取得不可）",
                    "メーカー": r.maker or "—",
                    "突合信頼度": r.match_confidence or "—",
                    "数量フラグ": r.qty_flag or "—",
                    "数量(仕入元/Amazon)": f"{_qty_label(r.supplier_qty)} / {_qty_label(r.amazon_qty)}",
                    "仕入値(円)": r.supplier_price,
                    "Amazon売値(円)": int(r.amazon_price),
                    "純利益(円)": int(r.net_profit),
                    "利益率(%)": round(r.margin_rate * 100, 1),
                    "ROI(%)": round(r.roi * 100, 1),
                    "月販推定": r.monthly_sales,
                    "ランキング": r.sales_rank,
                    # 列名を偽らない: COUNT_NEW は「オファー数」であって出品者数ではない。
                    # 人が見るべきライバル数は「実セラー数」列（未検証なら空欄）。
                    "新品オファー数": r.offer_count,
                    "実セラー数": r.real_seller_count,
                    "在庫切れ率(%)": None if r.oos_rate_90d is None else round(r.oos_rate_90d * 100),
                    "判定": r.verdict,
                    "突合": r.match_status,
                    "カテゴリ": r.category_label,
                    "仕入元": r.supplier_url,
                    "Amazon": _amazon_url(r.asin),
                    # 「サンプル」列は本番（Keepa実データ）時は出さない。下で keepa_live により列ごと落とす。
                    "サンプル": "該当" if r.is_sample else "",
                }
                for r in matched_rows
            ]
        )
        # 本番（Keepa実データ）接続時は「サンプル」列ごと表示しない（矛盾表現の排除）。
        if keepa_live and "サンプル" in df.columns:
            df = df.drop(columns=["サンプル"])

        if is_netsea:
            st.subheader("卸から探した黒字候補ランキング（NETSEA卸価格・実URL）")
            st.caption(
                f"NETSEAの承認サプライヤーの商品をJANでAmazonと突合し、**黒字候補 "
                f"{len(matched_rows)} 件**を卸価格（仕入値）・仕入元URL付きで表示しています。"
                "卸価格は同じJANで最安値になりやすいため、黒字が出やすい本命のルートです。"
            )
        elif is_finder or is_legacy_amazon:
            st.subheader("実仕入元が付いた利益ランキング（実価格・実URL）")
            st.caption(
                f"Amazon候補のJANを Yahoo＋楽天で逆引きし、**実在の仕入元が見つかった "
                f"{len(matched_rows)} 件**だけを実仕入値・仕入元URL付きで表示しています。"
            )

        # 並べ替え UI（既定は純利益降順 = パイプラインの出力順）
        sort_col = st.selectbox(
            "並べ替え", ["純利益(円)", "利益率(%)", "ROI(%)", "月販推定", "ランキング"], index=0
        )
        ascending = sort_col == "ランキング"  # ランキングだけは小さいほど良い
        df = df.sort_values(sort_col, ascending=ascending, na_position="last")

        def _hl(row):
            # 数量フラグが警告（数量補正/数量要確認）の行は黄色で「要・個数目視」を強調（偽の原石の温床）。
            flag = str(row.get("数量フラグ", ""))
            conf = str(row.get("突合信頼度", ""))
            if flag in pipeline.QTY_WARN_FLAGS or conf in ("中", "低"):
                color = "#fff8e1"  # 黄: 数量要確認/補正 or 突合信頼度が高でない → 原石にしない
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
        # 原石基準は preset の実値から動的生成（表示と実装の食い違いを根絶）。
        _gem_txt = (
            active_gem_criteria_text(finder_key=finder_preset_key)
            if is_finder
            else active_gem_criteria_text(preset_key=preset_key)
        )
        st.caption(
            f"判定「原石」=**数量が一致して信頼できる**行のうち{_gem_txt}（選択中プリセットの基準）です。 "
            "「数量フラグ」に警告が付く行は、**仕入元の個数と販売先（Amazon）の個数が違う、または不明**な行です。"
            "「1個入りを仕入れて20個入りとして売る」ような誤った突合を防ぐため、これらは原石とせず"
            "「要確認」に分類しています（"
            "数量補正の仕入値は1個あたり単価×Amazon個数での**推定**＝人間の目視照合が前提）。 "
            "必ず「仕入元商品名」と「Amazon商品名」の個数を見比べ、両リンクから現物を確認してください。"
        )
        st.caption(
            "「突合信頼度」列は、仕入元名とAmazon名がどれだけ同一商品らしいかを示します。"
            "**高**＝型番またはブランドが一致し、容量・本数などの数値属性に矛盾がない（原石はこの行のみ）。"
            "**中**＝名称はある程度重複するが型番・ブランド未確認（要確認）。"
            "**低**＝共通点が乏しい、または数値属性が矛盾（別商品の疑いとして隔離）。"
        )

        # ── 最悪相場シミュレーション（PoiPoiの最終判断支援・差分4）──────────
        # 「過去相場（元相場）まで値下がりしても黒字か＝損切りにならないか」を行ごとに判定。
        # 計算はすべて pipeline.simulate_worst_case → calc/profit.py に委譲（UIは表示のみ）。
        with st.expander("▼ 最悪相場シミュレーション（過去相場まで下落しても黒字か）", expanded=False):
            st.caption(
                "PoiPoiの最終判断と同じ考え方です。Keepaの過去価格推移から「最悪のケース（過去の最安水準）」を取り、"
                "その売値でも黒字かを検証します。過去価格が取れない行は、想定下落後の売値を手入力して試せます。"
            )
            for r in matched_rows:
                _label = f"{(r.amazon_name or r.name)[:40]}（現在 {int(r.amazon_price):,}円 / 仕入 {r.supplier_price:,}円）"
                # 過去相場から最悪ケースを試す。
                sim = pipeline.simulate_worst_case(r)
                if sim is not None:
                    mark = "🟢 黒字維持" if sim.is_profitable else "🔴 損切りリスク"
                    st.markdown(
                        f"**{mark}**｜{_label}<br>"
                        f"過去相場の最安 約{int(sim.worst_price):,}円 まで下落 → "
                        f"純利益 約{int(sim.worst_net_profit):,}円（利益率 {sim.worst_margin_rate*100:.1f}%）",
                        unsafe_allow_html=True,
                    )
                    if r.price_history:
                        st.line_chart(
                            pd.DataFrame({"想定売値(円)": r.price_history}),
                            height=140,
                        )
                else:
                    # 過去価格が取れない → 手入力での簡易シミュレーション。
                    st.markdown(f"{_label}<br>過去価格が取得できないため、想定下落後の売値を入力してください。", unsafe_allow_html=True)
                    _mp = st.number_input(
                        f"想定下落後の売値（円）｜{r.asin}",
                        value=int(r.amazon_price), step=100, min_value=0,
                        key=f"wc_{r.asin}",
                    )
                    sim2 = pipeline.simulate_worst_case(r, manual_price=_mp)
                    if sim2 is not None:
                        mark = "🟢 黒字維持" if sim2.is_profitable else "🔴 損切りリスク"
                        st.markdown(
                            f"**{mark}**｜売値 {int(sim2.worst_price):,}円 → "
                            f"純利益 約{int(sim2.worst_net_profit):,}円（利益率 {sim2.worst_margin_rate*100:.1f}%）",
                            unsafe_allow_html=True,
                        )
                st.divider()
            if not keepa_live:
                st.caption(
                    "※ サンプル動作中は過去価格は擬似値（現在価格から自動生成した目安）です。"
                    "KEEPA_API_KEY 設定後に実際の過去相場へ切り替わります。"
                )
    elif is_finder or is_legacy_amazon:
        st.warning(
            "実在の仕入元が付いた行は **0件** でした。"
            "Amazon候補のJANを Yahoo＋楽天で逆引きしましたが、同じJANの出品が見つかりませんでした。"
            "下の「仕入元未特定」候補を手動でリサーチするか、別のカテゴリやプリセットをお試しください。"
        )

    # ── 仕入元未特定セクション（参考・要手動リサーチ。利益数値は一切出さない）──
    if unmatched_rows:
        st.divider()
        st.subheader("仕入元未特定（参考・要手動リサーチ）")
        st.caption(
            f"以下の {len(unmatched_rows)} 件は Amazon側で見つけた売れ筋候補ですが、"
            "**Yahoo＋楽天で同じJANの仕入元が見つかりませんでした**。"
            "実仕入値が無いため、利益率・ROI・純利益は**あえて表示していません**"
            "（仮置きの数字で誤解を招かないため）。Amazon商品名で別ルート（卸・店舗・メーカー等）を"
            "手動リサーチする出発点としてご利用ください。"
        )
        udf = pd.DataFrame(
            [
                {
                    "Amazon商品名": r.amazon_name or r.name,
                    "メーカー": r.maker or "—",
                    "Amazon売値(円)": int(r.amazon_price),
                    "月販推定": r.monthly_sales,
                    "ランキング": r.sales_rank,
                    # 列名を偽らない: COUNT_NEW は「オファー数」であって出品者数ではない。
                    # 人が見るべきライバル数は「実セラー数」列（未検証なら空欄）。
                    "新品オファー数": r.offer_count,
                    "実セラー数": r.real_seller_count,
                    "仕入元": "仕入元が見つかりませんでした",
                    "Amazon": _amazon_url(r.asin),
                }
                for r in unmatched_rows
            ]
        )
        st.dataframe(
            udf,
            use_container_width=True,
            height=300,
            column_config={
                "Amazon": st.column_config.LinkColumn("Amazon", display_text="Amazonで開く"),
            },
        )

    # ── 別商品の疑い（JAN誤登録）セクション ──────────────────────────────
    # JANは一致するが仕入元名とAmazon名がかけ離れている＝出店者のJAN誤登録の疑い。
    # 利益数値は一切出さず、両名を並べて目視確認を促す（社長の買い間違え事故防止）。
    if suspect_rows:
        st.divider()
        st.subheader("別商品の疑い（仕入元名とAmazon名が一致しません・要目視確認）")
        st.caption(
            f"以下の {len(suspect_rows)} 件は **JANは一致しましたが、仕入元の商品名と "
            "Amazonの商品名がかけ離れています**。安い輸入雑貨では出店者が誤った/使い回しの "
            "JANを登録していることがあり、同じJANでも全く別の商品を指す場合があります。"
            "誤って仕入れる事故を防ぐため、これらは利益ランキングから除外し、利益率・純利益は"
            "**あえて表示していません**。両リンクから現物を見比べ、同一商品か必ずご確認ください。"
        )
        sdf = pd.DataFrame(
            [
                {
                    "仕入先": r.supplier_source or "—",
                    "仕入元商品名": r.name,
                    "Amazon商品名": r.amazon_name or "（取得不可）",
                    "メーカー": r.maker or "—",
                    "仕入値(円)": r.supplier_price,
                    "Amazon売値(円)": int(r.amazon_price) if r.amazon_price else None,
                    "仕入元": r.supplier_url,
                    "Amazon": _amazon_url(r.asin),
                }
                for r in suspect_rows
            ]
        )
        st.dataframe(
            sdf,
            use_container_width=True,
            height=300,
            column_config={
                "仕入元": st.column_config.LinkColumn("仕入元", display_text="開く"),
                "Amazon": st.column_config.LinkColumn("Amazon", display_text="Amazonで開く"),
            },
        )
