"""取得ポリシーを1ファイルに集約する。

法務（ハルオ）の判定が変わったら、**ここだけ**を書き換えれば全スクリプトに効く。
コードのあちこちに sleep(2) を散らさないための置き場です。

現在の根拠:
  - T-20260831-001 Phase B（ハルオ 2026-08-31）
    「メーカー公式サイトの低速クロールは可。robots.txt 尊重・同一ホスト3秒間隔・
      UA明示・会社概要/問い合わせ系ページ限定」
  - T-20260920-002 S-E（`05_リスト拡充の法務判定.md`・ハルオ 2026-09-20）
    §2-4 の表が、この下の定数名と1対1で対応している。数値を変えるときは 05 を先に読むこと。
    NG 判定はゼロ。業界団体9本とも取得できる（条件は ASSOCIATION_RULES を参照）。
"""

from __future__ import annotations

import datetime
import os

# ── 誰として名乗るか ────────────────────────────────────────────────
# 05 §2-4。個人のメールアドレスは載せない（PUBLIC リポかつ不特定多数のサーバに送られる）。
# 連絡先は URL で足りる。ブラウザUAの詐称は個情法20条1項「偽りその他不正の手段」に寄るので禁止。
# ※ https://satoy-select.com/bot のページはまだ存在しない。UA が 404 を指している状態なので、
#   本格運用の前に1ページ作ること（06_リスト拡充の実装.md の残課題に記載）。
USER_AGENT = (
    "SatoySelect-MakerListBot/1.0 "
    "(business partner research; 1 req/3s; respects robots.txt; "
    "+https://satoy-select.com/bot)"
)

# ── 同一ホストへの最小間隔（秒）────────────────────────────────────
# 05 §2-4 / §3-1。どちらも 3.0。2.5 に緩めた根拠は既判定に無かったので差し戻した。
# robots.txt に Crawl-delay があれば、その値と比べて**大きい方**を採る（fetcher 側で実装）。
ASSOCIATION_MIN_INTERVAL = 3.0
MAKER_MIN_INTERVAL = 3.0

# ── 1社あたり何ページまで追うか ────────────────────────────────────
# トップ + 会社概要 + 問い合わせ = 3ページ。依頼文の上限そのもの。
MAKER_MAX_PAGES_PER_COMPANY = 3

# ── 1日あたりのリクエスト上限（05 §2-4）────────────────────────────
# 全体 1,500/日。業界団体分はそのうち 400/日。プロセスをまたいで数えるため、
# 実際のカウンタは WORK_DIR/quota_<日付>.json に置く（fetcher.py）。
DAILY_REQUEST_LIMIT = 1500
ASSOCIATION_DAILY_LIMIT = 400

# ── 実行してよい時間帯（JST・両端含む）────────────────────────────
# 05 §2-4：平日・祝日を問わず 09:00〜21:00。深夜の無人アクセスは、
# 先方が異常に気づいても連絡できず心証が最悪、という理由。
# ALLOW_ANYTIME=1 はテスト専用（ネットに出ない再抽出の実行に使う）。
DAYTIME_START_HOUR = 9
DAYTIME_END_HOUR = 21

# ── HTTP ────────────────────────────────────────────────────────────
TIMEOUT_SEC = 15
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
# 05 §2-4：同一ホストはもちろん、**異なるホストへの並列も1で開始**。
# プロセスを分けて速くしたくなるが、それは 05 の条件を外れる。増やさないこと。
CONCURRENCY = 1

# ── 打ち切り条件（05 §2-4）──────────────────────────────────────────
# 403 / 429 / 5xx が1回でも出たら、そのホストは即時・永久に打ち切る。
# CAPTCHA・WAF は回避しない。岡崎市立中央図書館事件（刑法233条・234条の2）。
ABORT_HOST_STATUSES = (401, 403, 429, 500, 502, 503, 504)

# ── 自社HP側の利用規約スキャン（05 §6）────────────────────────────
# この語が本文に出たドメインは即ブラックリストにして、法務が読むまで止める。
TOS_KEYWORD_SCAN = ("クローリング", "クロール", "スクレイピング", "自動収集",
                    "無断転載", "自動取得", "ロボットによる")

# ── 会社情報系とみなすパス（メーカー公式サイトで追ってよいページ）──
# ハルオの「会社概要/問い合わせ系ページ限定」に対応。
COMPANY_PAGE_HINTS = (
    "company", "about", "corporate", "profile", "outline", "gaiyo", "gaiyou",
    "contact", "inquiry", "toiawase", "otoiawase", "support",
    "会社概要", "会社案内", "企業情報", "会社情報", "お問い合わせ", "問い合わせ",
)

# ── 置き場 ──────────────────────────────────────────────────────────
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TICKET = "T-20260920-002"
WORK_DIR = os.path.join(REPO, "workspace", "output", "agent_output", TICKET, "S-F")
CACHE_DIR = os.path.join(WORK_DIR, "cache")
OUT_DIR = os.path.join(REPO, "workspace", "output", "deliverables", TICKET, "out")
# 2026-09-15 に取得済みの業界団体名簿 HTML（サトル/T-20260915-003）
SOURCES_HTML = os.path.join(
    REPO, "workspace", "output", "agent_output", "T-20260915-003", "sources_html"
)
BASE_CSV = os.path.join(
    REPO, "workspace", "output", "deliverables", "T-20260915-003",
    "01_メーカー一覧_業界団体名簿.csv",
)


# ── 団体ごとの個別条件（05 §2-1 の表をそのまま写したもの）──────────
# 条件はホストごとに違う。共通条件（間隔・UA・robots）に上乗せする差分だけを書く。
ASSOCIATION_RULES = {
    # 会員限定領域の明示拒否。リンクを見つけても絶対に辿らない。
    "toys":      {"judgment": "条件付きOK", "forbidden_paths": ("/pdf/kaiin/", "/jtamember/")},
    # 明示の不許諾宣言あり（/cms/ja/copyright）。抽出は5項目のみ・本文は保存しない・再公開不可。
    "napac":     {"judgment": "条件付きOK（最狭）", "fields_only":
                  ("社名", "所在地", "電話番号", "FAX番号", "自社HP"),
                  "keep_body_text": False, "detail_once": True},
    "jppma":     {"judgment": "条件付きOK"},
    # 五十音別10ページも1ページずつ3秒空ける（共通条件どおり）。
    "jaftma":    {"judgment": "条件付きOK"},
    "jaspo":     {"judgment": "条件付きOK"},
    "petfood":   {"judgment": "条件付きOK"},
    "jpm":       {"judgment": "条件付きOK"},
    # 詳細67ページも同条件。
    "houseware": {"judgment": "条件付きOK"},
    # robots.txt が User-agent:* / Allow:/ で明示の全面許可。
    "jaama":     {"judgment": "取得OK"},
}

JST = datetime.timezone(datetime.timedelta(hours=9))


def today() -> str:
    return datetime.datetime.now(JST).date().isoformat()


def fetched_at() -> str:
    """全レコードに必須の取得時刻（JST）。05 §2-4。"""
    return datetime.datetime.now(JST).isoformat(timespec="seconds")


def in_daytime(now: datetime.datetime | None = None) -> bool:
    if os.environ.get("ALLOW_ANYTIME") == "1":
        return True
    now = now or datetime.datetime.now(JST)
    return DAYTIME_START_HOUR <= now.hour <= DAYTIME_END_HOUR
