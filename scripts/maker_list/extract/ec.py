"""EC（ネット直販）をやっているかの信号を、**そのメーカー自身のHPだけ**から読む。

これは法務が指定した第一選択の実装です（05_リスト拡充の法務判定 §4-0）。

  楽天 / Yahoo!ショッピング / Amazon の**サーバには1リクエストも送らない**。
  メーカー自身のページに「楽天市場店はこちら」と貼ってあるのを読んでいるだけなので、
  各モールの規約の名宛人にならない。0円・0リスク。
  - 楽天は機械取得が規約7条1項(7)で NG（人の目視のみ可）
  - Yahoo! は条件付き（9条件）だが、今回は実装しない
  - Amazon は当社の出品アカウントを賭けるので閲覧もしない

値は2つだけ（05 §4-4）:
  「有（要確認）」… リンクやカート語を見つけた。人が最終確認する前提
  「未確認」      … 見つからなかった。**「無」とは書かない**
リンクが無い＝出店していない、ではない（HPに貼っていないだけかもしれない）。
「ネット販売に疎い＝本丸」という戦略判断を直接歪めるので、ここを断定しない。
"""

from __future__ import annotations

import re
import unicodedata

# 自社EC のカート／ショップ導線を示す語。アンカーテキストと href の両方を見る。
_SHOP_TEXT = (
    "オンラインショップ", "オンラインストア", "公式ショップ", "公式ストア",
    "通信販売", "通販", "ネットショップ", "webショップ", "ウェブショップ",
    "ショッピング", "カートに入れる", "買い物かご", "ご購入はこちら",
    "online shop", "online store", "web shop", "e-shop", "shopping cart",
)
_SHOP_URL = (
    "/shop", "/store", "/ec/", "/cart", "/onlineshop", "/online-shop",
    "/onlinestore", "/online-store", "shop.", "store.", "ec.", "shopping.",
)
# ASP カート（これが出たら自社ECはほぼ確定）
_CART_PLATFORM = {
    "thebase.in": "BASE", "base.shop": "BASE",
    "stores.jp": "STORES", ".stores.jp": "STORES",
    "shopify": "Shopify", "myshopify.com": "Shopify",
    "shop-pro.jp": "カラーミー", "colorme": "カラーミー",
    "makeshop.jp": "MakeShop", "futureshop": "FutureShop",
    "ocnk.net": "おちゃのこネット", "cart.": "汎用カート",
}
# モール（メーカー自身のHPに貼られたリンクのホスト名から読む）。05 §4-0 の判定ロジックそのもの。
_MALL = {
    "rakuten.co.jp": "楽天",
    "rakuten.ne.jp": "楽天",
    "shopping.yahoo.co.jp": "Yahoo",
    "store.yahoo.co.jp": "Yahoo",
    "paypaymall.yahoo.co.jp": "Yahoo",
    "amazon.co.jp": "Amazon",
    "amzn.to": "Amazon",
    "amzn.asia": "Amazon",
}
# 「卸売・OEM を受けている」痕跡（平井氏の観点。優先度づけの材料）
_WHOLESALE_WORDS = ("oem", "odm", "卸売", "卸し", "お取引", "代理店募集", "業務用", "特注", "別注")


def _n(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "").lower()


def _registrable(host: str) -> str:
    """example.co.jp / shop.example.co.jp → example.co.jp 相当の比較キー。"""
    parts = [p for p in host.lower().split(".") if p]
    if len(parts) >= 3 and parts[-2] in ("co", "ne", "or", "ac", "go", "com"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_own_site(href: str, own_host: str) -> bool:
    """相対URL、または自社ドメイン配下のURLなら True（＝自社ECの導線とみなす）。

    own_host が空なら判定しようがないので True（拾って人が確認する側に倒す）。
    """
    if not href.startswith("http"):
        return True          # 相対パス = 自社サイト内
    if not own_host:
        return True
    try:
        host = href.split("/")[2]
    except IndexError:
        return True
    return _registrable(host) == _registrable(own_host)


def detect(links: list[tuple[str, str]], text: str, own_host: str = "") -> dict:
    """links = [(href, アンカーテキスト), ...] / text = ページ本文。

    戻り値の例:
      {"自社EC": "有", "自社EC根拠": "オンラインショップ / BASE",
       "モール": "楽天, Amazon", "卸OEM記載": "有"}
    """
    text_n = _n(text)
    hits: list[str] = []
    malls: set[str] = set()

    for href, label in links:
        h, lb = _n(href), _n(label)
        for key, name in _CART_PLATFORM.items():
            if key in h:
                hits.append(name)
        for key, name in _MALL.items():
            if key in h:
                malls.add(name)
        if any(w in lb for w in _SHOP_TEXT):
            hits.append(label.strip()[:20] or "ショップ導線")
        elif any(w in h for w in _SHOP_URL) and _is_own_site(h, own_host):
            hits.append(href.strip()[:40])

    if not hits:
        for w in _SHOP_TEXT:
            if w in text_n:
                hits.append(w)
                break

    seen: list[str] = []
    for h in hits:
        if h not in seen:
            seen.append(h)

    return {
        # 05 §4-4：機械判定は候補まで。2値で出し、「無」とは書かない。
        "自社EC": "有（要確認）" if seen else "未確認",
        "自社EC根拠": " / ".join(seen[:3]),
        "モール": ", ".join(sorted(malls)) if malls else "未確認",
        "卸OEM記載": "有（要確認）" if any(w in text_n for w in _WHOLESALE_WORDS) else "未確認",
    }


def site_description(raw_html: str, limit: int = 90) -> str:
    """トップページの <title> と meta description から「何の会社か」を1行で取る。

    要約はしない。サイト運営者が自分で書いた文をそのまま渡す。
    『株式会社◯◯｜ステンレス製厨房用品の製造販売』のような文が
    社長の「何を作っているか」に一番よく効く（本文の抽出より歩留まりが良い）。
    """
    out = []
    m = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.S | re.I)
    if m:
        out.append(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip())
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']{4,300})["\']',
        raw_html, re.I) or re.search(
        r'<meta[^>]+content=["\']([^"\']{4,300})["\'][^>]*name=["\']description["\']',
        raw_html, re.I)
    if m:
        out.append(re.sub(r"\s+", " ", m.group(1)).strip())
    joined = " / ".join(x for x in out if x)
    return "" if _is_boilerplate(joined) else joined[:limit]


# ナビゲーションの見出しだけのページ（中身が無いと確実に言えるもの）
_NAV_ONLY = re.compile(
    r"^(会社案内|会社情報|会社概要|企業情報|お問い合わせ|問い合わせ|"
    r"アクセス|採用情報|プライバシーポリシー|サイトマップ|home|top)"
    r"[\s|｜/／-]*$", re.I)


def _is_boilerplate(s: str) -> bool:
    return not s or bool(_NAV_ONLY.match(s.strip()))


# 「何を作っているか」が本当に書かれているかの判定に使う語。
# 社名の繰り返しと定型文だけの説明を、製品情報と取り違えないため。
# ここに当たらない説明は捨てずに残すが、**確定ではなく「要確認」として扱う**。
_PRODUCT_WORDS = (
    "製造", "製作", "生産", "加工", "販売", "メーカー", "製品", "商品", "用品",
    "器具", "機器", "用具", "部品", "材料", "素材", "雑貨", "工業", "食品",
    "玩具", "おもちゃ", "釣", "ペット", "スポーツ", "キッチン", "調理", "厨房",
    "包装", "容器", "金属", "樹脂", "プラスチック", "繊維", "化学", "塗料",
    "自動車", "バイク", "家具", "寝具", "日用品", "衛生", "化粧", "医療",
)


def has_product_signal(text: str) -> bool:
    """その文字列が「何を作っているか」を実際に語っているか。"""
    t = _n(text)
    return bool(t) and any(w in t for w in (_n(w) for w in _PRODUCT_WORDS))


def guess_products(text: str, limit: int = 60) -> str:
    """「何を作っているか」の手がかりを本文から1行だけ拾う。

    要約はしない（AI要約は人の確認が要るので、ここでは原文のまま渡す）。
    事業内容／取扱品目／製品 の見出しの直後の文を優先する。
    """
    t = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or ""))
    for key in ("事業内容", "取扱品目", "主な製品", "取扱商品", "製品案内", "営業品目", "業務内容"):
        m = re.search(re.escape(key) + r"[：:\s]*(.{6,%d})" % limit, t)
        if m:
            return m.group(1).strip(" ：:・|/")
    return ""
