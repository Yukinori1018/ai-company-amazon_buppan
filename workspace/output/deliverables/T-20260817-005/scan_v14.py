"""メーカー仕入れ 候補プール継続スキャナ v14（T-20260817-005）。

## v13 と何が違うか — 社長の方針転換（2026-08-24）を実装したものです

> 「トークンが続く限り、母数を取り続けて欲しい。**ランキングが重要ではない。利益が取れる
>   商品をいかに仕入れられるかの勝負なので、利益率の高い商品を狙い撃ちするというのは愚策。
>   どんどん母数をとって、仕入れられそうな商品をリストアップしていって下さい。私はそのリストを
>   見て、片っ端から連絡していくのみです。**その為には脳死で連絡をして、利益が確保出来る金額で
>   仕入れられるのであれば、仕入れたいので、**想定仕入れ金額もリストにして欲しい**」

これを設計に落とすと、こうなります。

| | v13（厳選100件） | **v14（候補プール）** |
|---|---|---|
| ゴール | 消化月数の良い top100 | **落とせるだけ長い候補プール** |
| 消化月数 3ヶ月以内 | **GO の必須条件** | **ゲートから外して「並べ替え用の1列」に降格** |
| ランク | 30万位まで（一応の上限） | 同左。順位付けには使わない |
| `variationCount` | 1〜3（＝0 の商品 97,484件を丸ごと落としていた） | **0〜3**（D8 修正） |
| レビュー件数 5〜300 | Finder の条件 | **撤廃**（D11: offers 無しでは検証も鮮度測定も不能だった） |
| 社長が見る列 | ASIN・ランク・…（27列） | **メーカー名 → 商品名 → ASIN → 想定仕入れ金額(上限)** の順 |
| 出力 | 商品行のみ | 商品行 **＋ メーカー名寄せ行**（社長はメーカー単位で連絡するため） |
| 運転 | 一発走 | **中断・再開できる継続運転**（自動停止条件つき） |

母集団の実測差〔2026-08-24 / Finder の totalResults〕:

| | v13 条件 | **v14 条件** | 倍率 |
|---|---|---|---|
| A（1,500〜8,000円 × ドロップ10+） | 7,834 | **30,133** | 3.85倍 |
| B（8,000〜20,000円 × ドロップ4+） | 3,978 | **18,627** | 4.68倍 |
| 合計 | 11,812 | **48,760** | **4.1倍** |

## パイプライン

    Phase1 Finder  価格帯シャードごとに ASIN を集める（1シャード = 10 + ceil(件数/100) トークン）
    Phase2 詳細    100件バッチで product?stats=365（1トークン/件）
                   → **安い判定**（価格・サイズ・Amazon本体・メーカー名・黒字化可否）
    Phase3 offers  安い判定を通った行だけに product?offers=20（**約6.5トークン/件**）
                   → distinct sellerId で **実セラー数 >= 2** を確定（これが唯一の必須ゲート）
    Phase4 出力    候補CSV追記 ＋ メーカー名寄せCSV再生成 ＋ progress.json 更新

**offers が律速です。** Keepa は 20件未満のオファー要求を受け付けない（実測: `offers=10` は
`Either no or a minimum of 20 offers must be requested.` で拒否）ので、単価は下げられません。

## トークンの現実（社長へ正直に）

このアカウントの **トークン上限は 1,200・補充は 20/分（＝1,200/時）** です。貯め込めないので、
**12時間走らせても使えるのは約 14,400 トークンが上限**。1件あたりの実効コストは
`1（詳細）+ 通過率×6.5（offers）` ≒ 5〜6 トークンなので、**12時間で 2,500〜3,000件処理・
候補 1,000〜1,300件** が物理的な天井です。母数をこれ以上増やすには Keepa の上位プラン
（＝課金・CLAUDE.md §4.1）が必要で、それは社長判断の領域です。

## 使い方

    python3 scan_v14.py                     # 新規開始（v14/ を作り直さない・追記）
    python3 scan_v14.py --resume            # 取得済み ASIN を飛ばして続きから
    python3 scan_v14.py --max-hours 6       # 自動停止までの時間を変える（既定12時間）
    python3 scan_v14.py --pilot 200         # パイロット（200件処理したら止まる）
    python3 scan_v14.py --rebuild           # API を叩かずCSVからメーカー名寄せだけ作り直す
    touch v14/STOP                          # 走行中に安全停止させる

## 自動停止条件（暴走防止・社長の明示要望）

1. 通算 `--max-hours`（既定 **12時間**。`0` を渡すと時間では止まらない）を超えた
2. Keepa トークンが枯れ、**60分以上回復しない**（`--token-starve-minutes`）
3. **3ラウンド連続で新規 ASIN がゼロ**（探索空間を掘り尽くした）
4. `v14/STOP` ファイルが置かれた
5. **直近100リクエストの API エラー率が20%を超えた**（T-20260831-002 / S3）

止まった理由は必ず `v14/progress.json` の `stop_reason` とログに残ります。
**異常で止まったときは `v14/ALERT.md` も書きます。**「掘り切りました」と
書いてよいのは、Keepa が正常に0件を返したときだけです。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
from pathlib import Path

# --------------------------------------------------------------------------
# 依存: 共有ライブラリ（Keepa 正規化・料率表）と、このチケットのローカルモジュール
#   .env は ~/.config/ai-company-amazon-buppan/keepa.env → agent_output の順に探す（M3）。
# --------------------------------------------------------------------------
ROOT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan")
CODE = ROOT / "workspace/output/agent_output/T-20260521-005/code"
sys.path.insert(0, str(CODE))

# .env の探索順（M3 / T-20260831-002）。
#   ① 環境変数に既にある → 何も読まない
#   ② ~/.config/ai-company-amazon-buppan/keepa.env  ← リポ外・gitignore不要・worktree で消えない
#   ③ agent_output 側の .env                        ← 元の場所。**gitignore 対象なので消えうる**
# 常駐ジョブが ③ だけに依存していると、agent_output が消えた瞬間に
# import 時例外 → launchd が再起動を繰り返す、という「静かな死」になる。
ENV_CANDIDATES = [
    Path.home() / ".config/ai-company-amazon-buppan/keepa.env",
    CODE / ".env",
]
for _env_path in ENV_CANDIDATES:
    if not _env_path.exists():
        continue
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k, _v.strip().strip('"').strip("'"))

from adapters.amazon_data import _map_category_key  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import procure_limit  # noqa: E402  想定仕入れ金額（上限）の計算ロジック
from seller_count import seller_profile  # noqa: E402  実セラー数（distinct sellerId）

OUT = HERE / "v14"
RAW = OUT / "raw"
RAW_OFFERS = OUT / "raw_offers"
for d in (OUT, RAW, RAW_OFFERS):
    d.mkdir(parents=True, exist_ok=True)

CSV_ALL = OUT / "01_候補プール_全件.csv"        # 判定に落ちた行も含む（監査用）
CSV_GO = OUT / "02_候補リスト_社長用.csv"        # 社長が片っ端から連絡するリスト
CSV_MAKER = OUT / "03_メーカー名寄せ.csv"        # メーカー単位の連絡先リスト
PROGRESS = OUT / "progress.json"
SEEN = OUT / "seen_asins.txt"
LOG = OUT / "scan_v14.log"
STOP_FILE = OUT / "STOP"

# ==========================================================================
# 抽出条件（v1.3 ベース + 2026-08-24 の方針転換）。ここだけ直せば条件が変わる。
# ==========================================================================
KEEPA_DOMAIN_JP = 5
KEEPA_EPOCH_MIN = 21564000          # Keepa time(分) = unixtime/60 - この値

RANK_MAX = 300_000                  # 足切りには使わない。念のための上限だけ残す
COUNT_NEW_MIN, COUNT_NEW_MAX = 2, 6  # Finder の前段フィルタ。**これは出品者数ではない**
REAL_SELLERS_MIN = 2                # ★唯一の必須ゲート: distinct sellerId >= 2
OFFERS_PARAM = 20                   # Keepa は 20 未満を受け付けない（実測 2026-08-24）
OFFERS_CHUNK = 10                   # offers 付きレスポンスは重いので小さめのバッチで
# product は1リクエスト100件まで受け付けるが、**あえて小さくしている**。
# トークン補充が20/分なので、100件バッチ（詳細100 + offers 約90件×6.5 ≒ 685トークン）は
# 1周に約34分かかる。その間 CSV も progress.json も1行も動かず、
# 「無人で動いているのか死んでいるのか」が外から分からない。
# 25件なら約8分周期で行が積まれ、途中で止めても失うのは最大25件ぶんだけで済む。
# トークン単価は件数ベースなので、バッチを小さくしても**コストは1トークンも増えない**。
DETAIL_CHUNK = 25
FINDER_PER_PAGE = 1000              # 実測: perPage=1000 が通る（1000件で約20トークン）

# D8（2026-08-24 社長判断）: 下限を 0 に下げた。`variationCount=0` の商品は 97,484件あり、
# 現行が拾っていた 1〜3 の帯（93,574件）より多かった。単品商品はメーカー仕入れの主戦場。
VARIATION_MIN, VARIATION_MAX = 0, 3
# D11（2026-08-24 社長判断）: レビュー件数フィルタは撤廃。offers 無しのリクエストでは
# csv[17] も stats.current[17] も全件欠落し、効いているかすら検証できない条件だった。
TRACKING_DAYS_MIN = 180             # 追跡180日以上（データが薄すぎる商品だけ弾く）

# 価格帯2本立て（v1.3・社長裁可 2026-08-17）: (下限, 上限, ドロップ数の下限, シャード幅)
PRESETS = {
    "A": (1500, 8000, 10, 500),
    "B": (8000, 20000, 4, 1000),
}

# 除外4カテゴリ（ドラッグ／ビューティー／食品／アダルト）。ここは絞る方向を維持する。
EXCLUDE_ROOT_CATEGORIES = [160384011, 52374051, 57239051]
NG_CATEGORY_WORDS = re.compile(
    r"(ドラッグ|医薬|サプリメント|ビューティー|コスメ|化粧|食品|飲料|お酒|"
    r"アダルト|大人のおもちゃ|成人)")
NG_TITLE_WORDS = re.compile(r"(アダルト|18禁|成人向|医薬品|指定第2類|第(1|2|3)類医薬品)")

# 大手・海外ブランドの検知（**除外はしない・列に出すだけ**）。
BIG_BRAND_HINTS = re.compile(
    r"(SONY|ソニー|Panasonic|パナソニック|東芝|TOSHIBA|日立|SHARP|シャープ|"
    r"Nike|ナイキ|adidas|アディダス|Apple|Anker|アンカー|UGREEN|Baseus|"
    r"Logicool|Logitech|Canon|Nikon|BANDAI|バンダイ|TAKARA|タカラトミー|"
    r"任天堂|Nintendo|BUFFALO|バッファロー|ELECOM|エレコム|Philips|フィリップス|"
    r"SanDisk|Seagate|Xiaomi|シャオミ|EPSON|エプソン|Brother|ブラザー|"
    r"アイリスオーヤマ|IRIS|山善|YAMAZEN|KOKUYO|コクヨ|ZOJIRUSHI|象印|"
    r"TIGER|タイガー|CASIO|カシオ|SEIKO|セイコー|BURTLE|バートル)", re.I)

# リスク区分（マリエの v13 タブと同じ考え方。PSE/危険物は初回テストで避けたい論点）。
RISK_LITHIUM = re.compile(
    r"(リチウム|lithium|モバイルバッテリー|充電池|充電器|バッテリー|電源|ACアダプタ|"
    r"ポータブル電源|昇圧|インバーター)", re.I)
RISK_ELECTRIC = re.compile(r"(家電|カメラ|パソコン|周辺機器|オーディオ|照明|空調|美容家電)")

# FBA 標準サイズ（Amazon.co.jp）: 45×35×20cm 以内 かつ 9kg 以内。超えたら「大型」。
FBA_STD_DIMS_MM = (450, 350, 200)
FBA_STD_WEIGHT_G = 9000

# 想定月販 = 月間ドロップ数 ÷ (実セラー数 + 1)、消化月数 = 初回ロット ÷ 想定月販。
# **消化月数はもうゲートではない**（社長方針: 順位付けに労力を割かない）。列と並べ替えにだけ使う。
LOT_SIZE = 10                       # v1.2「制限ありは初回10点以上」に合わせた保守側の既定

# --- D1: 2026-02-23 の価格定義変更（listing price → landing price）---------
PRICE_DEF_CHANGE_KEEPA_MIN = 7966080

# ==========================================================================
# 自動停止（暴走防止）
# ==========================================================================
MAX_HOURS_DEFAULT = 12.0            # ①通算の走行時間（0 = 無制限。常時稼働はこちら）
TOKEN_STARVE_MINUTES = 60           # ②トークンが回復しないまま何分で諦めるか
# ↑ --token-starve-minutes で上書きできる（常時稼働では長めにする。
#   補充は20/分で保証されているので、ここに引っかかるのは Keepa 側の障害のときだけ）。
# raw/ raw_offers/ の合計がこれを超えたら **生レスポンスの保存だけをやめる**（削除はしない）。
# 削除は CLAUDE.md §4.1（不可逆な削除）なので、自動では絶対に踏まない。
RAW_MAX_GB_DEFAULT = 10.0
# **既定では生レスポンスを保存しない**（M8 / T-20260831-002）。
# 2026-08-31 に `grep -rn "v14/raw" --include=*.py` で確認したところ、
# raw/ raw_offers/ の .json.gz を読むコードは1本もありませんでした。
# 12時間で500MB＝1日1GB を、誰も読まないまま書いていたことになります。
# 残したいときだけ `--keep-raw` を付けてください（既存ファイルは削除しません）。
KEEP_RAW_DEFAULT = False

# ==========================================================================
# 異常の可視化（M1/M2/S3 — T-20260831-002）
# ==========================================================================
HEARTBEAT_SEC = 60          # 心拍ファイルを何秒ごとに打つか
API_WINDOW = 100            # 直近この件数のリクエスト成否を見る
API_ERROR_RATE_MAX = 0.20   # S3: エラー率がこれを超えたら停止して ALERT
EMPTY_ROUNDS_LIMIT = 3              # ③新規ゼロが何ラウンド続いたら止めるか
# これを割ったら補充待ち。DETAIL_CHUNK=25 なら1バッチ45トークンで足りるので、
# 150 を要求すると必要のない足踏みが増える。必要量ぎりぎり + 少しの余裕にする。
MIN_TOKENS = 50
CHECKPOINT_EVERY = 500              # ④何件ごとにチェックポイントを取るか
# 件数だけを条件にすると、offers 待ちで遅い時間帯に progress.json が1時間以上古いままになり、
# 「今どうなっているか」が外から分からなくなる。時間でも打つ（トークンは消費しない）。
CHECKPOINT_EVERY_SEC = 900          #   〃 何秒ごとにも取るか（15分）

# ==========================================================================
# 出力列（★社長が使う順に並べる。13列目以降は補助）
# ==========================================================================
FIELDS = [
    # ---- ここだけ見れば連絡できる ----
    "メーカー/ブランド", "商品名", "ASIN", "想定仕入れ金額(上限)", "Amazon価格",
    "実セラー数", "想定月販", "消化月数", "カテゴリ", "FBAサイズ",
    "Amazonページ", "Keepaリンク",
    # ---- 連絡先を探すための補助 ----
    "メーカー検索(Google)", "ブランド", "manufacturer", "セラー名一覧", "メーカー直販フラグ",
    # ---- 金額の内訳（1円もごまかさないための監査列）----
    "赤字ライン(これ以上は赤字)", "仕入れ掛け率上限%", "上限で仕入れた時の純利益",
    "目標純利益率%", "基準売価", "基準売価の根拠", "販売手数料率%", "手数料内訳",
    # ---- 元データ ----
    "新品最安値(送料込)", "過去最安値(2026-02-23以降)", "価格定義混在",
    "月間ドロップ数", "月間販売数", "ランク", "新品オファー数",
    "規模フラグ", "リスク区分", "preset", "価格帯", "取得日時",
    "判定", "見送り理由",
]

MAKER_FIELDS = [
    "メーカー/ブランド", "該当商品数",
    # ★鮮度（M9 / T-20260831-002）。想定仕入れ金額は**取得時点の価格**から逆算した値で、
    #   90日前の数字で交渉して合意すると、そのまま赤字仕入れになりうる。
    #   だから社長が実際に見る 03 に日付を必ず出す。
    "鮮度", "最終取得日", "最古取得日",
    "想定仕入れ金額の中央値", "Amazon価格の中央値",
    "消化月数の中央値", "代表ASIN", "代表商品名", "代表Amazonページ", "代表Keepaリンク",
    "メーカー検索(Google)", "主なカテゴリ", "規模フラグ", "リスク区分あり件数",
]
STALE_DAYS = 30             # 最終取得日がこれより古ければ「要再取得」


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
        timeout=30).json()


def _num(v):
    """Keepa の -1/-2/None は「データ無し」。数値だけ返す。"""
    if isinstance(v, (int, float)) and v >= 0:
        return v
    return None


def _series(product: dict, idx: int) -> list:
    c = product.get("csv") or []
    return c[idx] if len(c) > idx and c[idx] else []


def _min_since(series: list, since_min: int):
    """since_min 以降に**記録された**データ点の最小値。-1（オファー無し）は除外。"""
    best = None
    for i in range(0, len(series) - 1, 2):
        t, v = series[i], series[i + 1]
        if not isinstance(v, int) or v < 0 or t < since_min:
            continue
        if best is None or v < best:
            best = v
    return best


def _carry_in(series: list, since_min: int):
    """since_min 時点で有効だった値（境界より前の最後の記録）。"""
    val = None
    for i in range(0, len(series) - 1, 2):
        t, v = series[i], series[i + 1]
        if t > since_min:
            break
        if isinstance(v, int) and v >= 0:
            val = v
    return val


def lowest_consistent_price(product: dict) -> dict:
    """D1: 価格定義が一貫した窓（2026-02-23 以降）の最安値。

    Keepa の NEW 系列は 2026-02-23 を境に「出品価格」→「着地価格（＋送料）」へ定義が変わる。
    365日窓の最小値は境界をまたぐ＝**定義混在**なので、損益計算の主軸には使わない。
    """
    ser = _series(product, 1)                     # csv 1 = NEW
    post = _min_since(ser, PRICE_DEF_CHANGE_KEEPA_MIN)
    pre_exists = any(
        isinstance(ser[i + 1], int) and ser[i + 1] >= 0 and ser[i] < PRICE_DEF_CHANGE_KEEPA_MIN
        for i in range(0, len(ser) - 1, 2))
    carried = _carry_in(ser, PRICE_DEF_CHANGE_KEEPA_MIN) if post is None else None
    return {"post": post if post is not None else carried,
            "mixed": bool(pre_exists and post is not None)}


def fba_size_class(product: dict) -> tuple:
    """(size_key, 区分表示, 寸法mmタプル)。FBA標準(45x35x20cm/9kg)超は大型。

    寸法・重量が無い商品は「不明」。**除外はしない**（母数を減らさない。判断は人に渡す）。
    """
    raw = (product.get("packageLength"), product.get("packageWidth"),
           product.get("packageHeight"))
    dims = sorted([d for d in raw if isinstance(d, (int, float)) and d > 0], reverse=True)
    dims_tuple = tuple(raw) if len(dims) == 3 else None
    weight = product.get("packageWeight")
    weight = weight if isinstance(weight, (int, float)) and weight > 0 else None
    if len(dims) < 3 and weight is None:
        return "unknown", "不明", None
    if len(dims) == 3 and any(d > lim for d, lim in zip(dims, FBA_STD_DIMS_MM)):
        return "large", "大型", dims_tuple
    if weight is not None and weight > FBA_STD_WEIGHT_G:
        return "large", "大型", dims_tuple
    if weight is None:
        return "unknown", "不明(重量欠落)", dims_tuple
    if weight <= 250 and (not dims or dims[0] <= 250):
        return "small", "標準(小型)", dims_tuple
    if weight <= 1000:
        return "standard_1", "標準1", dims_tuple
    return "standard_2", "標準2", dims_tuple


def risk_label(title: str, cat: str) -> str:
    """リスク区分。PSE/リチウムは初回テストで避けたい論点なので必ず見えるようにする。"""
    blob = f"{title} {cat}"
    if RISK_LITHIUM.search(blob):
        return "リチウム/電源系(PSE・FBA危険物)"
    if RISK_ELECTRIC.search(cat):
        return "電気製品(PSE要確認)"
    return ""


def google_search_url(maker: str) -> str:
    """メーカー名から連絡先を探すための検索URL。社長はここから電話番号に辿り着く。"""
    if not maker:
        return ""
    q = urllib.parse.quote(f"{maker} 会社概要 問い合わせ 卸")
    return f"https://www.google.com/search?q={q}"


# ==========================================================================
# 判定（Phase2 の安い判定 → Phase3 の実セラー確定）
# ==========================================================================
def evaluate(product: dict, preset: str, band: str, seller: dict = None) -> dict:
    """1商品を CSV 1行に落とす。seller が None なら「実セラー未検証」。

    **落とすのは「明らかに無理なもの」だけ**（社長方針: フィルタは絞る方向で設計しない）。
    v1.3 の段1（消化月数3ヶ月以内）はゲートから外し、並べ替え用の列に降格している。
    """
    stats = product.get("stats") or {}
    cur = stats.get("current") or []
    asin = product.get("asin") or ""
    title = product.get("title") or ""
    brand = (product.get("brand") or "").strip()
    manufacturer = (product.get("manufacturer") or "").strip()
    maker = brand or manufacturer          # 表示は brand 優先（サトルの _brand_of と同順）
    cat_names = [c.get("name", "") for c in (product.get("categoryTree") or [])
                 if isinstance(c, dict)]
    cat_label = " > ".join(cat_names[:3])

    rank = _num(cur[3]) if len(cur) > 3 else None
    count_new = _num(cur[11]) if len(cur) > 11 else None     # COUNT_NEW（≠出品者数）
    drops30 = _num(stats.get("salesRankDrops30"))
    monthly_sold = product.get("monthlySold")
    monthly_sold = (int(monthly_sold)
                    if isinstance(monthly_sold, (int, float)) and monthly_sold > 0 else "")
    # D2: この列は Buy Box 価格ではない。offers/buybox を付けない限り current[1]=NEW が入る。
    lowest_new = _num(cur[1]) if len(cur) > 1 else None
    lp = lowest_consistent_price(product)
    floor_price = lp["post"]

    size_key, size_label, dims_mm = fba_size_class(product)

    # ---- 実セラー数（Phase3 を通っていれば入る）----
    real = seller["real_sellers"] if seller else None
    est_monthly = (drops30 / (real + 1)) if (drops30 and real is not None) else (
        drops30 / (count_new + 1) if (drops30 and count_new is not None) else None)
    months = (LOT_SIZE / est_monthly) if est_monthly else None

    # ---- 想定仕入れ金額（上限）----
    pl = procure_limit.compute(
        current_price=lowest_new, floor_price=floor_price,
        category_key=_map_category_key(product), size_key=size_key,
        dims_mm=dims_mm, turnover_months=months)

    row = {
        "メーカー/ブランド": maker,
        "商品名": title[:90],
        "ASIN": asin,
        "想定仕入れ金額(上限)": pl["limit"] if pl["limit"] is not None else "",
        "Amazon価格": int(lowest_new) if lowest_new else "",
        "実セラー数": real if real is not None else "",
        "想定月販": round(est_monthly, 2) if est_monthly else "",
        "消化月数": round(months, 2) if months else "",
        "カテゴリ": cat_label,
        "FBAサイズ": size_label,
        "Amazonページ": f"https://www.amazon.co.jp/dp/{asin}",
        "Keepaリンク": f"https://keepa.com/#!product/5-{asin}",
        "メーカー検索(Google)": google_search_url(maker),
        "ブランド": brand,
        "manufacturer": manufacturer,
        "セラー名一覧": seller["names_label"] if seller else "",
        "メーカー直販フラグ": ("メーカー直販" if seller and seller["maker_direct"] else ""),
        "赤字ライン(これ以上は赤字)": pl["breakeven"] if pl["breakeven"] is not None else "",
        "仕入れ掛け率上限%": pl["buy_rate_pct"] if pl["buy_rate_pct"] is not None else "",
        "上限で仕入れた時の純利益": pl["net_at_limit"] if pl["net_at_limit"] is not None else "",
        "目標純利益率%": round(procure_limit.TARGET_NET_MARGIN * 100),
        "基準売価": pl["base_price"] if pl["base_price"] is not None else "",
        "基準売価の根拠": pl["basis"],
        "販売手数料率%": pl["referral_rate"] if pl["referral_rate"] is not None else "",
        "手数料内訳": pl["cost_breakdown"],
        "新品最安値(送料込)": int(lowest_new) if lowest_new else "",
        "過去最安値(2026-02-23以降)": int(floor_price) if floor_price else "",
        "価格定義混在": "はい" if lp["mixed"] else "いいえ",
        "月間ドロップ数": int(drops30) if drops30 else "",
        "月間販売数": monthly_sold,
        "ランク": int(rank) if rank else "",
        "新品オファー数": int(count_new) if count_new is not None else "",
        "規模フラグ": ("大手/海外疑い" if BIG_BRAND_HINTS.search(f"{maker} {title}")
                  else "中小候補"),
        "リスク区分": risk_label(title, cat_label),
        "preset": preset,
        "価格帯": band,
        "取得日時": time.strftime("%Y-%m-%d %H:%M"),
    }

    # ---- 「明らかに無理なもの」だけを落とす ----
    ng = []
    if NG_CATEGORY_WORDS.search(cat_label) or NG_TITLE_WORDS.search(title):
        ng.append("除外カテゴリ")
    if size_label == "大型":
        ng.append("FBA大型サイズ")
    if not maker:
        ng.append("メーカー名なし（連絡先に辿り着けない）")
    if not lowest_new:
        ng.append("価格取得不可")
    elif pl["limit"] is None:
        ng.append("この売値では黒字にできない")
    # D3: current[0] == -1 は「今この瞬間 Amazon 価格が無い」だけ。
    # 「Amazon のオファーがそもそも存在しない」は availabilityAmazon == -1 だけが表す。
    avail = product.get("availabilityAmazon")
    if isinstance(avail, int):
        if avail != -1:
            ng.append(f"Amazon本体あり(availabilityAmazon={avail})")
    elif _num(cur[0]) is not None:
        ng.append("Amazon本体あり")

    row["判定"] = "候補" if not ng else "見送り"
    row["見送り理由"] = " / ".join(ng)
    # 実セラー確定後の最終ゲート。未検証の行は "候補(実セラー未検証)" のまま置く。
    if row["判定"] == "候補":
        if real is None:
            row["判定"] = "候補(実セラー未検証)"
        elif real < REAL_SELLERS_MIN:
            row["判定"] = "見送り"
            row["見送り理由"] = f"実セラー数{real}（卸している証拠なし＝メーカー独占の疑い）"
    return row


# ==========================================================================
# Keepa API
# ==========================================================================
ALERT_FILE = OUT / "ALERT.md"
HEARTBEAT = OUT / "heartbeat.json"


def write_alert(title: str, detail: str) -> None:
    """異常を1つのファイルに書き出す。SessionStart フックがこれを拾って社長に見せる。

    **「掘り切りました」と書いてよいのは、Keepa が正常に 0件 を返したときだけ。**
    API エラー・通信断・キー失効を「掘り切り」と記録すると、
    誰も壊れたことに気づけません（night-shift が14日間 exit 127 で死んでいたのと同じ構図）。
    """
    ALERT_FILE.write_text(
        f"""# ALERT — 候補リスト常時稼働ジョブ

発生: {time.strftime('%Y-%m-%d %H:%M:%S')}

## {title}

{detail}

## 対応

1. `v14/scan_v14.log` の末尾を見る
2. 直せたら、このファイルを消してから常駐ジョブを起こし直す
   （`launchctl kickstart -k gui/$(id -u)/com.aicompany.amazon-buppan.list-builder`）
3. 直せない・課金や契約の話なら、秘書カズヨへ差し戻す（CLAUDE.md §4.1）
""", encoding="utf-8")
    log(f"!! ALERT を書きました: {title}")


def beat(extra: dict = None) -> None:
    """心拍。**PID の生死ではなくこのファイルの mtime で「生きているか」を判定する。**

    PID は再利用されるので `os.kill(pid, 0)` は死んだプロセスを「走行中」と誤表示します。
    """
    data = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": os.getpid(),
            "epoch": int(time.time())}
    data.update(extra or {})
    try:
        HEARTBEAT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


class ApiHealth:
    """直近 API_WINDOW 件のリクエストが成功したかを覚えておく（S3 の材料）。"""

    def __init__(self):
        self.window = []            # True=成功 / False=失敗
        self.last_failed = False
        self.last_error = ""
        self.total_errors = 0

    def ok(self) -> None:
        self.window.append(True)
        del self.window[:-API_WINDOW]
        self.last_failed = False

    def fail(self, why: str) -> None:
        self.window.append(False)
        del self.window[:-API_WINDOW]
        self.last_failed = True
        self.last_error = why
        self.total_errors += 1

    def error_rate(self) -> float:
        if len(self.window) < 20:       # サンプルが少ないうちは判断しない
            return 0.0
        return 1 - sum(self.window) / len(self.window)

    def unhealthy(self) -> bool:
        return self.error_rate() > API_ERROR_RATE_MAX


API = ApiHealth()


class Budget:
    """トークンの出入りを1か所で管理する。消費量の集計と補充待ちの両方をここでやる。"""

    def __init__(self):
        self.consumed = 0
        self.left = None
        self.starving_since = None

    def note(self, payload: dict) -> None:
        c = payload.get("tokensConsumed")
        if isinstance(c, (int, float)) and c > 0:
            self.consumed += int(c)
        left = payload.get("tokensLeft")
        if isinstance(left, (int, float)):
            self.left = int(left)

    def wait(self, need: int, deadline: "StopWatch") -> bool:
        """need に届くまで待つ。回復しないまま TOKEN_STARVE_MINUTES 経ったら False。

        ★M7: 以前は `token_status()` が例外を投げ続ける経路（ネットワーク断・DNS障害）で
        `starving_since` が一度も立たず、**永久に10秒スリープを繰り返していました**。
        「時間で止めない」は「無限に待ってよい」ではありません。ここに絶対上限を置きます。
        """
        if self.starving_since is None:
            self.starving_since = time.time()
        while True:
            beat({"state": "token_wait", "need": need, "left": self.left})
            if deadline.should_stop():
                return False
            if time.time() - self.starving_since > TOKEN_STARVE_MINUTES * 60:
                deadline.stop(f"トークンが{TOKEN_STARVE_MINUTES}分以上回復しませんでした"
                              f"（left={self.left} need={need}）")
                write_alert("トークンが回復しません",
                            f"{TOKEN_STARVE_MINUTES}分待っても need={need} に届きませんでした"
                            f"（最後に見えた残り: {self.left}）。\n"
                            "Keepa 側の障害・契約の失効・ネットワーク断のいずれかです。")
                return False
            try:
                d = token_status()
                API.ok()
            except Exception as e:
                API.fail(f"token: {e}")
                if API.unhealthy():
                    deadline.stop(f"API エラー率が{API.error_rate():.0%}を超えました")
                    write_alert("Keepa API がエラーを返し続けています",
                                f"直近{len(API.window)}件のうち"
                                f"{API.error_rate():.0%}が失敗。最後の理由: {e}\n"
                                "**これは母数の枯渇ではありません。** "
                                "キー失効・プラン切れ・Keepa 障害を疑ってください。")
                    return False
                time.sleep(10)
                continue
            self.left = int(d.get("tokensLeft", 0))
            if self.left >= need:
                self.starving_since = None
                return True
            rate = d.get("refillRate") or 20
            wait = min(max((need - self.left) / rate * 60, 15), 300)
            log(f"  トークン補充待ち: left={self.left} need={need} → {wait:.0f}秒")
            time.sleep(wait)


class StopWatch:
    """自動停止条件を1か所に集める。走行中はここだけ見れば止まるべきか分かる。"""

    def __init__(self, max_hours: float, pilot: int = 0):
        self.t0 = time.time()
        # 0 以下は「時間では止めない」。常時稼働（always_on.py）はこれを使う。
        self.max_sec = float("inf") if max_hours <= 0 else max_hours * 3600
        self.pilot = pilot
        self.processed = 0
        self.empty_rounds = 0
        self.reason = None

    def stop(self, reason: str) -> None:
        if self.reason is None:
            self.reason = reason
            log(f"!! 自動停止: {reason}")

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def should_stop(self) -> bool:
        if self.reason:
            return True
        if STOP_FILE.exists():                      # ④ STOP ファイル
            self.stop("STOP ファイルを検知しました（手動停止）")
        elif API.unhealthy():                       # ⑤ S3: API エラー率
            self.stop(f"API エラー率が{API.error_rate():.0%}に達しました"
                      f"（最後の理由: {API.last_error}）")
            write_alert("Keepa API がエラーを返し続けています",
                        f"直近{len(API.window)}件のうち{API.error_rate():.0%}が失敗。"
                        f"最後の理由: {API.last_error}\n"
                        "**これは母数の枯渇ではありません。**")
        elif self.elapsed > self.max_sec:           # ① 時間切れ（max_sec=inf なら発火しない）
            self.stop(f"通算 {self.max_sec / 3600:.1f} 時間に達しました")
        elif self.empty_rounds >= EMPTY_ROUNDS_LIMIT:  # ③ 新規ゼロ
            self.stop(f"新規 ASIN がゼロのラウンドが {EMPTY_ROUNDS_LIMIT} 回続きました")
        elif self.pilot and self.processed >= self.pilot:
            self.stop(f"パイロット {self.pilot} 件に到達しました")
        return self.reason is not None


RAW_MAX_BYTES = int(RAW_MAX_GB_DEFAULT * 1024 ** 3)
KEEP_RAW = [KEEP_RAW_DEFAULT]      # --keep-raw で True。既定は「書かない」
_RAW_FULL = [False]        # 一度いっぱいになったら以降は測らない（毎回 du すると遅い）
_RAW_CHECK = [0.0]


def raw_has_room() -> bool:
    """raw/ raw_offers/ の合計が上限内かどうか。上限に達したら保存だけをやめる。

    **古いファイルの削除はしない。** 削除は CLAUDE.md §4.1 に該当するため、
    無人ジョブが自分で踏んではいけない。README に手動での掃除手順を書いてある。
    """
    if _RAW_FULL[0]:
        return False
    now = time.time()
    if now - _RAW_CHECK[0] < 300:      # 5分に1回だけ測る
        return True
    _RAW_CHECK[0] = now
    total = 0
    for d in (RAW, RAW_OFFERS):
        for f in d.glob("*.gz"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    if total >= RAW_MAX_BYTES:
        _RAW_FULL[0] = True
        log(f"!! raw の合計が上限 {RAW_MAX_BYTES / 1024 ** 3:.1f}GB に達しました "
            f"（実測 {total / 1024 ** 3:.1f}GB）。以後は生レスポンスを保存しません"
            f"（CSV への追記は続きます。古いファイルは削除しません）")
        return False
    return True


def keepa_get(path: str, params: dict, budget: Budget, label: str) -> dict:
    """Keepa を1回叩く。429 は待って再試行（無人運転で落とさない）。失敗は {} を返す。"""
    import requests
    params = dict(params, key=api_key(), domain=KEEPA_DOMAIN_JP)
    for attempt in range(5):
        try:
            resp = requests.get(f"https://api.keepa.com/{path}", params=params, timeout=300)
        except Exception as e:
            API.fail(f"{label} 通信エラー: {e}")
            log(f"    {label} 通信エラー: {e}")
            time.sleep(15)
            continue
        if resp.status_code == 402:
            # W4: Keepa が「このキーではアクセスできない」と言っている＝契約・制限の問題。
            # 生命線なので例外なく即停止する。リトライしても状況は変わらない。
            API.fail(f"{label} HTTP 402 契約が無効です")
            for _ in range(API_WINDOW):        # 直ちに unhealthy にする
                API.fail("HTTP 402")
            write_alert("Keepa から「アクセス権がない」と返ってきました（HTTP 402）",
                        "契約の失効・支払いの失敗・キーの無効化のいずれかです。\n"
                        "**母数の枯渇ではありません。** リトライしても直りません。\n"
                        "課金・契約に関わるので、自分で判断せず秘書カズヨへ差し戻してください"
                        "（CLAUDE.md §4.1）。")
            return {}
        if resp.status_code not in (200, 429):
            # 402=契約が無効 / 400=クエリ不正 / 5xx=Keepa 側の障害。
            # ★どれも「母数の枯渇」ではない。ここを {} で返して呼び出し側に
            #   「0件だった」と解釈させたのが F2（失敗を成功と記録する）の正体。
            API.fail(f"{label} HTTP {resp.status_code}")
            log(f"    {label} HTTP {resp.status_code}（{resp.text[:150]}）")
            time.sleep(min(30 * (attempt + 1), 180))
            continue
        if resp.status_code == 429:
            # 429 は「トークン切れ」＝正常なレート制御。**障害ではないので数えない。**
            wait = min(30 * (attempt + 1), 180)
            log(f"    {label} 429（トークン上限）→ {wait}秒待機")
            time.sleep(wait)
            continue
        try:
            payload = resp.json()
        except Exception as e:
            API.fail(f"{label} JSON 解釈失敗: {e}")
            log(f"    {label} JSON 解釈失敗: {e}")
            time.sleep(10)
            continue
        budget.note(payload)
        if payload.get("error"):
            API.fail(f"{label} API エラー: {payload['error']}")
            log(f"    {label} API エラー: {payload['error']}")
            return {}
        API.ok()
        return payload
    API.fail(f"{label} 5回試して駄目でした")
    log(f"    {label} 5回試して駄目でした。このバッチは飛ばします")
    return {}


# ==========================================================================
# Phase1: Finder（価格帯シャードで探索空間を分割する）
# ==========================================================================
def shards() -> list:
    """(preset, 価格下限, 価格上限, ドロップ下限, ラベル) のリスト。

    Finder は1クエリあたりの取得上限があるので、価格帯で刻んで**別々のクエリ**にする。
    こうすると 48,760件の母集団を端から掘り続けられる（＝「母数を取り続ける」の実装）。
    """
    out = []
    for preset, (lo, hi, drops, step) in PRESETS.items():
        p = lo
        while p < hi:
            top = min(p + step, hi)
            out.append((preset, p, top - 1, drops, f"{p}-{top - 1}円"))
            p = top
    return out


def build_selection(price_lo: int, price_hi: int, drops_min: int, page: int) -> dict:
    tracking_before = int(time.time() / 60) - KEEPA_EPOCH_MIN - TRACKING_DAYS_MIN * 24 * 60
    return {
        "current_AMAZON_gte": -1, "current_AMAZON_lte": -1,
        "availabilityAmazon": -1,                      # D3: 本体オファーが存在しない
        "current_COUNT_NEW_gte": COUNT_NEW_MIN, "current_COUNT_NEW_lte": COUNT_NEW_MAX,
        "current_NEW_gte": price_lo, "current_NEW_lte": price_hi,
        "current_SALES_gte": 1, "current_SALES_lte": RANK_MAX,
        "variationCount_gte": VARIATION_MIN, "variationCount_lte": VARIATION_MAX,  # D8
        # D11: current_COUNT_REVIEWS の条件はここに**入れない**（撤廃）
        "trackingSince_lte": tracking_before,
        "isAdultProduct": False,
        "categories_exclude": EXCLUDE_ROOT_CATEGORIES,
        "salesRankDrops30_gte": drops_min,
        "perPage": FINDER_PER_PAGE, "page": page,
        "sort": [["salesRankDrops30", "desc"]],
    }


# ==========================================================================
# CSV 入出力（**取得のたびに追記**＝途中で止めても成果が残る）
# ==========================================================================
def append_rows(path: Path, fields: list, rows: list) -> None:
    if not rows:
        return
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


def load_seen() -> set:
    """取得済み ASIN の台帳。**無ければ CSV から作り直す。**

    台帳（gitignore 対象）だけが消えると、全 ASIN を取り直したうえで
    `append_rows` が重複排除しないため CSV に同じ ASIN が2行入ります。
    すると `03_メーカー名寄せ.csv` の「該当商品数」が水増しされ、
    **社長が上から連絡する順番が静かに壊れます**（件数は増え、見た目では分からない）。
    CSV には ASIN 列があるので、台帳は完全に再構築できます。
    """
    if SEEN.exists():
        return {line.strip() for line in SEEN.read_text(encoding="utf-8").splitlines()
                if line.strip()}
    if not CSV_ALL.exists():
        return set()
    log("台帳 seen_asins.txt がありません。CSV から作り直します（重複行の防止）")
    seen = set()
    with open(CSV_ALL, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            a = (row.get("ASIN") or "").strip()
            if a:
                seen.add(a)
    if seen:
        SEEN.write_text("\n".join(sorted(seen)) + "\n", encoding="utf-8")
    log(f"    {len(seen)}件の ASIN を台帳に復元しました")
    return seen


def remember(asins: list) -> None:
    with open(SEEN, "a", encoding="utf-8") as f:
        for a in asins:
            f.write(a + "\n")


CURSORS = OUT / "shard_cursors.json"


def load_cursors() -> dict:
    """シャードごとの Finder ページ位置。これが無いと再開時に毎回1ページ目から掘り直す。

    ページ再取得そのものは20トークンで済むが、25シャードぶんで500トークン＝25分の無駄になる。
    """
    if CURSORS.exists():
        try:
            return json.loads(CURSORS.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cursors(cursors: dict) -> None:
    CURSORS.write_text(json.dumps(cursors, ensure_ascii=False, indent=1), encoding="utf-8")


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rebuild_maker_csv() -> int:
    """候補CSVを **メーカー/ブランド単位で名寄せ**して 03_メーカー名寄せ.csv を作り直す。

    社長は商品単位ではなく **メーカー単位で連絡する**ので、この1枚が実務の入口になる。
    冪等（何度呼んでも同じ）。チェックポイントのたびに丸ごと作り直す。
    """
    if not CSV_GO.exists():
        return 0
    with open(CSV_GO, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # ★同じ ASIN が複数行あっても1件として数える（F8: 該当商品数の水増し防止）。
    #   後勝ち＝新しく取得した行を採用する。
    unique = {}
    for r in rows:
        asin = (r.get("ASIN") or "").strip()
        unique[asin or f"__row{len(unique)}"] = r
    rows = list(unique.values())

    by_maker = {}
    for r in rows:
        m = (r.get("メーカー/ブランド") or "").strip()
        if m:
            by_maker.setdefault(m, []).append(r)

    def med(items, key):
        vals = [v for v in (_f(x.get(key)) for x in items) if v is not None]
        return round(statistics.median(vals)) if vals else ""

    def fetched_days(items):
        """取得日時（`YYYY-MM-DD HH:MM:SS`）から (最終, 最古, 経過日数) を出す。"""
        days = sorted(d for d in ((r.get("取得日時") or "")[:10] for r in items) if d)
        if not days:
            return "", "", None
        try:
            age = (dt.date.today() - dt.date(*map(int, days[-1].split("-")))).days
        except (ValueError, TypeError):
            age = None
        return days[-1], days[0], age

    out = []
    for maker, items in by_maker.items():
        newest, oldest, age = fetched_days(items)
        # 代表商品＝消化月数が最も短い行（＝一番売れている商品を看板にする）
        rep = min(items, key=lambda r: _f(r.get("消化月数"), 9999))
        cats = {}
        for r in items:
            c = (r.get("カテゴリ") or "").split(" > ")[0]
            if c:
                cats[c] = cats.get(c, 0) + 1
        out.append({
            "メーカー/ブランド": maker,
            "該当商品数": len(items),
            # 想定仕入れ金額は「取得時点の価格」から逆算した値。古いまま交渉すると赤字になる。
            "鮮度": ("要再取得" if (age is not None and age > STALE_DAYS)
                     else ("" if age is None else "OK")),
            "最終取得日": newest,
            "最古取得日": oldest,
            "想定仕入れ金額の中央値": med(items, "想定仕入れ金額(上限)"),
            "Amazon価格の中央値": med(items, "Amazon価格"),
            "消化月数の中央値": med(items, "消化月数"),
            "代表ASIN": rep.get("ASIN", ""),
            "代表商品名": rep.get("商品名", ""),
            "代表Amazonページ": rep.get("Amazonページ", ""),
            "代表Keepaリンク": rep.get("Keepaリンク", ""),
            "メーカー検索(Google)": rep.get("メーカー検索(Google)", ""),
            "主なカテゴリ": max(cats, key=cats.get) if cats else "",
            "規模フラグ": rep.get("規模フラグ", ""),
            "リスク区分あり件数": sum(1 for r in items if r.get("リスク区分")),
        })
    # 該当商品数の多い順＝1社に連絡して複数SKU取れる可能性が高い順
    out.sort(key=lambda r: (-r["該当商品数"], _f(r["消化月数の中央値"], 9999)))
    tmp = CSV_MAKER.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=MAKER_FIELDS)
        w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in MAKER_FIELDS})
    tmp.replace(CSV_MAKER)
    return len(out)


def checkpoint(watch: StopWatch, budget: Budget, state: dict, stat: dict) -> None:
    """通算件数・消費トークン・経過時間を progress.json に書く。ここで再開情報も確定する。"""
    makers = rebuild_maker_csv()
    data = {
        "ticket": "T-20260817-005",
        "scanner": "scan_v14",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(watch.t0)),
        "elapsed_sec": int(watch.elapsed),
        "elapsed_hhmm": time.strftime("%H:%M:%S", time.gmtime(watch.elapsed)),
        "stop_reason": watch.reason,
        "auto_stop": {
            "max_hours": (0 if watch.max_sec == float("inf") else watch.max_sec / 3600),
            "token_starve_minutes": TOKEN_STARVE_MINUTES,
            "empty_rounds_limit": EMPTY_ROUNDS_LIMIT,
            "stop_file": str(STOP_FILE),
        },
        "keepa": {
            "tokens_consumed": budget.consumed,
            "tokens_left": budget.left,
            "refill_per_min": 20,
            "note": "トークン上限1200・補充20/分。貯め込めないので12時間で約14,400が天井",
        },
        "counts": dict(stat),
        "makers_listed": makers,
        "cursor": state,
        "outputs": {
            "all": str(CSV_ALL), "go": str(CSV_GO), "makers": str(CSV_MAKER),
            "log": str(LOG),
        },
    }
    PROGRESS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    beat({"state": "checkpoint", "processed": stat["processed"], "go": stat["go"],
          "makers": makers, "stop_reason": watch.reason})
    log(f"[checkpoint] 処理{stat['processed']}件 / 候補{stat['go']}件 / メーカー{makers}社 "
        f"/ 消費{budget.consumed}トークン / 経過{data['elapsed_hhmm']}")


# ==========================================================================
# Phase3: 実セラー数の確定
# ==========================================================================
def _norm(text: str) -> str:
    """ブランド名とセラー名の突き合わせ用の粗い正規化（全角→半角・記号除去・小文字化）。"""
    if not text:
        return ""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            ch = chr(code - 0xFEE0)
        elif code == 0x3000:
            ch = " "
        out.append(ch)
    return re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]", "", "".join(out).lower())


def load_seller_names() -> dict:
    p = RAW_OFFERS / "seller_names.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_seller_names(names: dict) -> None:
    (RAW_OFFERS / "seller_names.json").write_text(
        json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_seller_names(ids: list, budget: Budget, watch: StopWatch) -> dict:
    """sellerId → 店舗名。/seller は 1トークン/ID。一度引いたらローカルに貯めて二度引かない。"""
    names = load_seller_names()
    missing = [s for s in dict.fromkeys(ids) if s and s not in names]
    for i in range(0, len(missing), 100):
        batch = missing[i:i + 100]
        if not budget.wait(len(batch) + 20, watch):
            break
        d = keepa_get("seller", {"seller": ",".join(batch)}, budget, "seller")
        for sid, info in (d.get("sellers") or {}).items():
            names[sid] = (info or {}).get("sellerName") or ""
        time.sleep(0.3)
    if missing:
        save_seller_names(names)
    return names


def verify_sellers(asins: list, budget: Budget, watch: StopWatch, raw_idx: list) -> dict:
    """ASIN リストに offers を掛けて実セラー情報を返す（約6.5トークン/件）。"""
    got = {}
    for i in range(0, len(asins), OFFERS_CHUNK):
        if watch.should_stop():
            break
        chunk = asins[i:i + OFFERS_CHUNK]
        if not budget.wait(OFFERS_CHUNK * 8 + 20, watch):
            break
        payload = keepa_get("product", {"offers": OFFERS_PARAM, "asin": ",".join(chunk)},
                            budget, "offers")
        products = payload.get("products") or []
        if products:
            path = RAW_OFFERS / f"offers_{raw_idx[0]:05d}.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            raw_idx[0] += 1
        for p in products:
            if p.get("asin"):
                got[p["asin"]] = p
        time.sleep(0.3)

    # セラー名の解決（メーカー直販かどうかの判定に要る）
    all_ids = []
    for p in got.values():
        all_ids.extend(seller_profile(p)["seller_ids"])
    names = fetch_seller_names(all_ids, budget, watch)

    out = {}
    for asin, p in got.items():
        sp = seller_profile(p)
        ids = sp["seller_ids"]
        brand = _norm(p.get("brand") or "") or _norm(p.get("manufacturer") or "")
        direct = bool(brand and any(
            _norm(names.get(sid, "")) and
            (brand in _norm(names.get(sid, "")) or _norm(names.get(sid, "")) in brand)
            for sid in ids))
        out[asin] = {"real_sellers": sp["real_sellers"], "seller_ids": ids,
                     "names_label": " / ".join(names.get(sid, sid) for sid in ids),
                     "maker_direct": direct}
    return out


# ==========================================================================
# main
# ==========================================================================
def run(args) -> None:
    watch = StopWatch(args.max_hours, pilot=args.pilot)
    budget = Budget()
    # 再開は常時有効。同じ ASIN に二度トークンを払わないための台帳。
    seen = load_seen()
    stat = {"processed": 0, "rows": 0, "go": 0, "offers_verified": 0,
            "rejected_seller": 0, "rejected_cheap": 0}
    raw_idx = [len(list(RAW.glob("*.json.gz")))]
    offers_idx = [len(list(RAW_OFFERS.glob("*.json.gz")))]

    if STOP_FILE.exists():
        # 勝手に消さない。「止めたい」という意思表示を、次回起動時に握りつぶさないため。
        # 再開するときは操作した人が明示的に消す（`rm v14/STOP`）。
        log(f"STOP ファイルがあるので起動しません: {STOP_FILE}")
        log("    再開するには先にこれを消してください: rm '%s'" % STOP_FILE)
        watch.stop("STOP ファイルが残っていたため起動しませんでした")
        checkpoint(watch, budget, {"not_started": True}, stat)
        return

    t = token_status()
    budget.left = t.get("tokensLeft")
    log("=" * 78)
    log(f"=== scan_v14 開始 tokensLeft={budget.left} refill={t.get('refillRate')}/分 "
        f"自動停止={args.max_hours}時間 既取得={len(seen)}件 ===")
    log(f"    停止させたいときは: touch {STOP_FILE}")

    plan = shards()
    # getattr にしてあるのは、run() をライブラリとして呼ぶテストが
    # 古い引数セットのままでも動くようにするため（Namespace に無くても落ちない）。
    skip = {b.strip() for b in (getattr(args, "skip_bands", "") or "").split(",") if b.strip()}
    if skip:
        plan = [s for s in plan if s[4] not in skip]
        log(f"    掘り切り済みとして {len(skip)}シャードを飛ばします（周回管理は always_on.py）")
    log(f"    探索シャード {len(plan)}本（価格帯で刻んで母集団を端から掘る）")
    if not plan:
        # 全シャードが掘り切り済み。ここで即終了して、上位（always_on.py）に
        # 「一周終わった」と伝える。空の for を回してもトークンを1つも生まないため。
        watch.stop("全シャードを掘り切りました（skip-bands で全件除外）")
        checkpoint(watch, budget, {"finished": True, "exhausted": sorted(skip)}, stat)
        log("=== 終了: 全シャード掘り切り済み ===")
        return
    # 起動直後に1回打つ。これが無いと、最初のチェックポイントまで progress.json が
    # **前回の走行の内容**のままで、見張りが「もう止まっています」と誤って表示する。
    checkpoint(watch, budget, {"starting": True}, stat)

    # --- シャードを **ラウンドロビン**で回す理由 ------------------------------
    # 1シャードを掘り切ってから次へ行くと、12時間で処理できる 2,000件前後が
    # 「1,500〜1,999円の帯」だけで埋まり、候補プールがカテゴリごと偏る（実測: 家電が9割）。
    # 社長は幅広く連絡先を集めたいので、**全価格帯から均等に**積む。
    # 各シャードの ASIN キューはメモリに持ち、1巡につき DETAIL_CHUNK 件だけ食べて次へ回す。
    cursors = load_cursors()
    queues = {s[4]: [] for s in plan}
    exhausted = set()
    since_checkpoint = 0
    last_checkpoint_at = time.time()
    round_no = 0

    while not watch.should_stop():
        round_no += 1
        new_this_round = 0
        for preset, lo, hi, drops, band in plan:
            if watch.should_stop():
                break
            if band in exhausted:
                continue

            # ---- Phase1: Finder（キューが空になったら1ページ補充する）----
            if not queues[band]:
                page = cursors.get(band, 0)
                if not budget.wait(40, watch):
                    break
                sel = build_selection(lo, hi, drops, page)
                payload = keepa_get("query",
                                    {"selection": json.dumps(sel, separators=(",", ":"))},
                                    budget, f"Finder {preset} {band} p{page}")
                total = payload.get("totalResults")
                asins = payload.get("asinList") or []
                log(f"[Finder {preset} {band}] page={page} 取得={len(asins)} "
                    f"該当総数={total} tokensLeft={budget.left}")
                if not asins:
                    # ★M2: 空の理由は2つある。混ぜてはいけない。
                    #   ・totalResults が整数で返っている → **本当に掘り切った**
                    #   ・レスポンスが壊れている/エラーだった → **障害**。掘り切りではない
                    if API.last_failed or not isinstance(total, int):
                        write_alert(
                            "Finder が空を返しましたが、掘り切りではありません",
                            f"シャード {band} / page={page} / totalResults={total!r}\n"
                            f"直近の API 失敗: {API.last_error or '(不明)'}\n"
                            "**このシャードを「掘り切り済み」として記録していません。**")
                        watch.stop("Finder が異常応答を返しました（掘り切りではありません）")
                        break
                    exhausted.add(band)     # このシャードは掘り切った（正常な0件）
                    cursors[band] = page + 1
                    continue
                queues[band] = [a for a in asins if a not in seen]
                if not queues[band]:
                    # このページは全部取得済み。次のページへ進めないと無限に同じページを引く。
                    cursors[band] = page + 1
                    continue
                # ★ここで cursor を進めてはいけない。1ページ=1000件を DETAIL_CHUNK ずつ
                #   食べる途中で落ちると、残りが二度と拾えなくなる。進めるのは食べ切ってから。

            chunk = queues[band][:DETAIL_CHUNK]
            queues[band] = queues[band][DETAIL_CHUNK:]
            if not queues[band]:
                # このページを食べ切った。次回はこのシャードの次ページから。
                cursors[band] = cursors.get(band, 0) + 1

            # ---- Phase2: 詳細（1トークン/件）----
            if not budget.wait(max(MIN_TOKENS, len(chunk) + 20), watch):
                break
            payload = keepa_get("product", {"stats": 365, "asin": ",".join(chunk)},
                                budget, f"detail {preset} {band}")
            products = payload.get("products") or []
            if not products:
                continue
            if KEEP_RAW[0] and raw_has_room():
                with gzip.open(RAW / f"{preset}_{raw_idx[0]:05d}.json.gz", "wt",
                               encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                raw_idx[0] += 1
            rows = [evaluate(p, preset, band) for p in products]
            by_asin = {p["asin"]: p for p in products if p.get("asin")}
            survivors = [r["ASIN"] for r in rows if r["判定"] == "候補(実セラー未検証)"]
            stat["rejected_cheap"] += len(rows) - len(survivors)

            # ---- Phase3: offers（約6.5トークン/件。ここが律速）----
            sellers = verify_sellers(survivors, budget, watch, offers_idx) if survivors else {}
            stat["offers_verified"] += len(sellers)
            final = []
            for r in rows:
                if r["判定"] != "候補(実セラー未検証)":
                    final.append(r)
                    continue
                p = by_asin.get(r["ASIN"])
                s = sellers.get(r["ASIN"])
                final.append(evaluate(p, preset, band, s) if (p and s) else r)

            append_rows(CSV_ALL, FIELDS, final)
            go_rows = [r for r in final if r["判定"] == "候補"]
            append_rows(CSV_GO, FIELDS, go_rows)
            # ★CSV に書き切ってから「取得済み」に入れる。逆にすると、途中で落ちたとき
            #   行が残らないまま ASIN だけスキップ対象になり、二度と拾えなくなる。
            fetched = [p["asin"] for p in products if p.get("asin")]
            seen.update(fetched)
            remember(fetched)
            stat["rejected_seller"] += sum(
                1 for r in final if "実セラー数" in (r.get("見送り理由") or ""))
            stat["processed"] += len(products)
            stat["rows"] += len(final)
            stat["go"] += len(go_rows)
            watch.processed = stat["processed"]
            beat({"state": "scanning", "processed": stat["processed"], "go": stat["go"],
                  "tokens_left": budget.left, "band": band})
            new_this_round += len(products)
            since_checkpoint += len(products)
            log(f"  [{preset} {band}] 処理{stat['processed']} 候補{stat['go']} "
                f"消費{budget.consumed}tok 残{budget.left} 経過"
                f"{time.strftime('%H:%M:%S', time.gmtime(watch.elapsed))}")

            if (since_checkpoint >= CHECKPOINT_EVERY
                    or time.time() - last_checkpoint_at >= CHECKPOINT_EVERY_SEC):
                checkpoint(watch, budget, {"round": round_no, "cursors": cursors,
                                           "exhausted": sorted(exhausted)}, stat)
                save_cursors(cursors)
                since_checkpoint = 0
                last_checkpoint_at = time.time()

        # ---- 停止条件③: 1巡まるごと新規ゼロが続いたら掘り尽くしたとみなす ----
        if new_this_round == 0:
            watch.empty_rounds += 1
            log(f"  ラウンド{round_no}: 新規ゼロ "
                f"（{watch.empty_rounds}/{EMPTY_ROUNDS_LIMIT}）")
        else:
            watch.empty_rounds = 0
        if len(exhausted) == len(plan):
            watch.stop("全シャードを掘り切りました")
    save_cursors(cursors)

    if watch.reason is None:
        watch.stop("探索シャードを最後まで掘り切りました")
    checkpoint(watch, budget,
               {"finished": True, "round": round_no, "cursors": cursors,
                "exhausted": sorted(exhausted | skip)}, stat)
    log(f"=== 終了: {watch.reason} ===")
    log(f"    処理 {stat['processed']}件 / 候補 {stat['go']}件 / "
        f"実セラー確定 {stat['offers_verified']}件 / 消費 {budget.consumed}トークン")
    log(f"    社長用リスト: {CSV_GO}")
    log(f"    メーカー名寄せ: {CSV_MAKER}")


def main() -> None:
    # 上書きするモジュール変数（argparse の help 文で読む前に宣言しておく必要がある）
    global RAW_MAX_BYTES, TOKEN_STARVE_MINUTES
    starve_default = TOKEN_STARVE_MINUTES
    raw_gb_default = RAW_MAX_GB_DEFAULT
    ap = argparse.ArgumentParser(description="メーカー仕入れ 候補プール継続スキャナ v14")
    ap.add_argument("--max-hours", type=float, default=MAX_HOURS_DEFAULT,
                    help=f"自動停止までの通算時間。**0 なら時間では止めない**（既定 {MAX_HOURS_DEFAULT}）")
    ap.add_argument("--pilot", type=int, default=0,
                    help="この件数を処理したら止まる（動作確認用）")
    ap.add_argument("--resume", action="store_true",
                    help="取得済み ASIN を飛ばして続きから（既定でも同じ挙動）")
    ap.add_argument("--rebuild", action="store_true",
                    help="API を叩かず、既存CSVからメーカー名寄せだけ作り直す（0トークン）")
    ap.add_argument("--keep-raw", action="store_true",
                    help="Keepa の生レスポンスを保存する（既定は保存しない。どのコードも読んでいないため）")
    ap.add_argument("--skip-bands", default="",
                    help="掘り切り済みシャードのラベルをカンマ区切りで（always_on.py が渡す）")
    ap.add_argument("--raw-max-gb", type=float, default=raw_gb_default,
                    help=f"raw/ raw_offers/ の合計上限GB。超えたら保存だけやめる（既定 {raw_gb_default}）")
    ap.add_argument("--token-starve-minutes", type=int, default=starve_default,
                    help=f"トークンが回復しないまま何分で諦めるか（既定 {starve_default}）")
    args = ap.parse_args()

    KEEP_RAW[0] = bool(args.keep_raw)
    RAW_MAX_BYTES = int(args.raw_max_gb * 1024 ** 3)
    TOKEN_STARVE_MINUTES = args.token_starve_minutes

    if args.rebuild:
        n = rebuild_maker_csv()
        log(f"メーカー名寄せを再生成: {n}社 → {CSV_MAKER}")
        return
    run(args)


if __name__ == "__main__":
    main()
