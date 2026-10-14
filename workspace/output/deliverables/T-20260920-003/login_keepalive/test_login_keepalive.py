"""login_keepalive.py の純ロジックのテスト（Chrome を触らない）。 python3 -m pytest -q でも、直接実行でも動く。"""
from datetime import datetime

import login_keepalive as lk

SITES = {s.id: s for s in lk.load_sites()}


def test_logout_urls_are_detected_for_every_enabled_site():
    # 2026-10-12 に curl（非ログイン）で実測した飛び先
    cases = {
        "sellercentral": "https://sellercentral-japan.amazon.com:443/ap/signin?openid.pape.max_auth_age=0",
        "amazon_jp": "https://www.amazon.co.jp/ap/signin?openid.return_to=x",
        "gmail_satoyselect": "https://accounts.google.com/v3/signin/identifier?continue=x",
        "superdelivery": "https://www.superdelivery.com/p/do/clickMemberLogin",
        "oroshi_uri": "https://oroshi-uri.com/login.php",
        "orosidonya": "https://www.orosidonya.com/users/sessionMessage.asp",
    }
    for sid, url in cases.items():
        assert lk.classify(SITES[sid], url, "x") == "logged_out", sid


def test_logged_in_pages_are_ok():
    assert lk.classify(SITES["sellercentral"], "https://sellercentral-japan.amazon.com/home", "Seller Central") == "ok"
    sd_ok = "https://www.superdelivery.com/p/do/memberManage/purchase/orderHistory/list"
    assert lk.classify(SITES["superdelivery"], sd_ok, "購入履歴｜卸・仕入れサイト【スーパーデリバリー】") == "ok"


def test_sd_title_guard():
    # 2026-10-14：旧 URL /i/r/msgbox はログイン中でも login へ飛び、10/12〜14 の「切れ」は誤判定だった。
    # 購入履歴ページでタイトルを見る。読み込み途中（タイトル＝URL）では判定しない。
    sd = SITES["superdelivery"]
    url = "https://www.superdelivery.com/p/do/memberManage/purchase/orderHistory/list"
    assert lk.classify(sd, url, "事業者専用の卸・仕入れサイト【スーパーデリバリー】") == "logged_out"
    assert lk.classify(sd, url, url) == "ok"
    assert "msgbox" not in sd.url


def test_gmail_wrong_account_and_ok():
    g = SITES["gmail_satoyselect"]
    assert lk.classify(g, "https://mail.google.com/mail/u/1/#inbox", "受信トレイ - someone@gmail.com - Gmail") == "wrong_account"
    assert lk.classify(g, "https://mail.google.com/mail/u/1/#inbox", "受信トレイ - satoyselect@gmail.com - Gmail") == "ok"
    assert lk.classify(g, "https://mail.google.com/mail/u/1/", "Gmail") == "ok"  # 読み込み途中のタイトルで誤報しない


def test_error_and_backoff():
    sd = SITES["superdelivery"]
    assert lk.classify(sd, "https://www.superdelivery.com/p/do/memberManage/purchase/orderHistory/list", "429 Too Many Requests") == "error"
    assert lk.classify(SITES["gmail_satoyselect"], "https://mail.google.com/mail/u/1/", "受信トレイ (503) - satoyselect@gmail.com - Gmail") == "ok"  # 未読数で誤報しない
    b = 1
    for _ in range(10):
        b = lk.next_backoff("error", b)
    assert b == lk.MAX_BACKOFF
    assert lk.next_backoff("ok", b) == 1


def test_query_string_never_logged():
    assert lk.host_path("https://a.example.com/p?token=SECRET#x") == "a.example.com/p"


def test_due_and_hours():
    sd = SITES["superdelivery"]  # 60分・7〜24時
    assert not lk.is_due(sd, None, 1, datetime(2026, 10, 12, 3, 0))      # 夜中は触らない
    assert lk.is_due(sd, None, 1, datetime(2026, 10, 12, 9, 0))
    assert not lk.is_due(sd, "2026-10-12T09:00:00", 1, datetime(2026, 10, 12, 9, 59))
    assert lk.is_due(sd, "2026-10-12T09:00:00", 1, datetime(2026, 10, 12, 10, 0))
    assert not lk.is_due(sd, "2026-10-12T09:00:00", 2, datetime(2026, 10, 12, 10, 30))  # 2倍に広げ中


def test_sd_daily_reloads_within_legal_line():
    sd = SITES["superdelivery"]
    per_day = (sd.hours[1] - sd.hours[0]) * 60 // sd.every_min
    assert per_day <= 30  # CLAUDE.md §3.3-18：SD は1日30回まで





def test_sellercentral_landing_page_means_logged_out():
    # 非ログインの Chrome で /home を開くと出品案内に飛ぶ（2026-10-12 実測）
    assert lk.classify(SITES["sellercentral"], "https://sellercentral-japan.amazon.com/amazonsell/business", "Amazonの新しい出品サービス") == "logged_out"


def test_outage_title_is_error_not_ok():
    assert lk.classify(SITES["netsea"], "https://www.netsea.jp/mypage", "サイト障害発生に関するお知らせ - NETSEA") == "error"


def test_kokubu_is_never_reported_ok():
    assert lk.classify(SITES["kokubu"], "https://netton.kokubu.jp/shop/customer/menu.aspx", "お客様ページ") == "unknown"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
