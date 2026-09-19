"""HTML を触る最低限の道具。外部ライブラリを足さないための小物置き場。

BeautifulSoup を入れなかった理由: 対象が9サイトの固定テンプレートで、
標準ライブラリの HTMLParser と re で足りるため（YAGNI）。
壊れた HTML に当たったら、そのときに lxml を入れる。
"""

from __future__ import annotations

import html as _html
import re
import unicodedata
from urllib.parse import urljoin, urlparse

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_A = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)


def strip_tags(raw: str, sep: str = "\n") -> str:
    raw = _SCRIPT.sub(" ", raw)
    return _html.unescape(_TAG.sub(sep, raw))


def text_lines(raw: str) -> list[str]:
    return [l.strip() for l in strip_tags(raw).split("\n") if l.strip()]


def flat_text(raw: str) -> str:
    return re.sub(r"[ \t]+", " ", strip_tags(raw, sep=" "))


def links(raw: str, base_url: str = "") -> list[tuple[str, str]]:
    """[(絶対URL, アンカーテキスト)] を返す。"""
    out = []
    for href, inner in _A.findall(raw):
        label = re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", inner))).strip()
        url = urljoin(base_url, _html.unescape(href.strip())) if base_url else _html.unescape(href.strip())
        out.append((url, label))
    return out


def external_links(raw: str, base_url: str) -> list[tuple[str, str]]:
    """base_url とは別ドメインのリンクだけ返す（＝会員の自社HP候補）。"""
    host = urlparse(base_url).netloc.lower()
    key = ".".join(host.split(".")[-2:])
    out = []
    for url, label in links(raw, base_url):
        if not url.startswith("http"):
            continue
        h = urlparse(url).netloc.lower()
        if key and key in h:
            continue
        out.append((url, label))
    return out


def norm_name(s: str) -> str:
    """社名の名寄せキー。法人格・記号・空白を落とす。"""
    s = unicodedata.normalize("NFKC", s or "")
    s = re.sub(r"株式会社|有限会社|合同会社|合名会社|合資会社|\(株\)|\(有\)|\(名\)|\(資\)", "", s)
    s = re.sub(r"[\s・,，.。\-ー－_（）()\[\]「」　]", "", s)
    return s.lower()


def clean_url(u: str) -> str:
    u = (u or "").strip().strip("　")
    if u and not u.startswith("http"):
        u = "http://" + u
    return u
