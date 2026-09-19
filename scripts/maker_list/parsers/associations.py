"""業界団体9名簿のパーサ。団体ごとに HTML の作りが違うので1団体1関数。

入力は保存済み HTML（agent_output/T-20260915-003/sources_html/・2026-09-15 取得）。
同じ関数が、あとで取り直した HTML にもそのまま使える（引数は文字列のみ）。

返す形は全団体で共通の dict:
  社名 / 電話番号 / FAX番号 / 自社HP / 取扱品目 / 所在地 / 会員種別 / 出典URL

※ NAPAC と 日本金属ハウスウェア（燕）は、一覧ページに社名しか無く、
  電話番号・HP・品目は**各社の詳細ページ**にある。詳細ページの取得は
  業界団体サイトへの新規アクセスなので、法務判定（05）が出るまで実行しない。
  この2団体は detail_parser だけ用意して、実行は保留している。
"""

from __future__ import annotations

import re

from ..extract import phone
from ..extract.htmlutil import (clean_url, external_links, flat_text, links,
                                strip_tags, text_lines)

# 団体ID → (表示名, 一覧URL, カテゴリ, キャッシュファイル)
ASSOCIATIONS = {
    "toys":      ("日本玩具協会", "https://www.toys.or.jp/kaiin_ichiran.html", "おもちゃ", ["toys.html"]),
    "jppma":     ("日本ペット用品工業会", "https://www.jppma.or.jp/member/list.php", "ペット用品", ["jppma.html"]),
    "petfood":   ("ペットフード協会", "https://petfood.or.jp/outline-list/", "ペット用品", ["petfood.html"]),
    "jaspo":     ("日本スポーツ用品工業協会（JASPO）", "https://jaspo.org/member-list/", "スポーツ＆アウトドア", ["jaspo_list.html"]),
    "jaftma":    ("日本釣用品工業会", "https://www.jaftma.or.jp/about/member_list/", "スポーツ＆アウトドア",
                  ["jaftma.html", "jaftma_02.html", "jaftma_03.html", "jaftma_04.html",
                   "jaftma_06.html", "jaftma_07.html", "jaftma_08.html", "jaftma_09.html",
                   "jaftma_10.html", "jaftma_11.html", "jaftma_12.html"]),
    "jpm":       ("日本プラスチック日用品工業組合", "https://jpm.or.jp/kumiai/", "ホーム＆キッチン", ["jpm.html"]),
    "jaama":     ("全国自動車用品工業会（JAAMA）", "https://www.jaama.gr.jp/member-companies/member-list.html", "車＆バイク", ["jaama.html"]),
    "napac":     ("NAPAC（日本自動車用品・部品アフターマーケット振興会）", "https://www.napac.jp/cms/ja/members", "車＆バイク", ["napac.html"]),
    "houseware": ("日本金属ハウスウェア工業組合（燕）", "https://houseware.jp/company/", "ホーム＆キッチン", ["houseware.html"]),
}

# 会員企業ではないもの（協会の事務局・広告・SNS など）を落とすための除外語
_NOISE = re.compile(
    r"^(ホーム|HOME|会員一覧|このページ|ページ|>|\||検索|Google|Copyright|お問い合わせ|"
    r"プライバシー|サイトマップ|TOP|一覧|PDF|詳細|サイトを見る|会社名|賛助会員|正会員|"
    r"組合員|団体会員|[アカサタナハマヤラワあかさたなはまやらわ]行|№|\d+)$"
)


def _row(name, *, url="", tel="", fax="", items="", addr="", kind="", src=""):
    return {
        "社名": re.sub(r"\s+", " ", name).strip(),
        "電話番号": tel or "",
        "FAX番号": fax or "",
        "自社HP": clean_url(url),
        "取扱品目": items or "",
        "所在地": addr or "",
        "会員種別": kind or "",
        "出典URL": src or "",
    }


def _anchor_list(raw: str, base: str, kind: str = "") -> list[dict]:
    """「外部リンクのアンカーテキスト＝社名」型の名簿（toys / jppma / jpm / jaama）。"""
    out = []
    for url, label in external_links(raw, base):
        if not label or _NOISE.match(label) or len(label) < 2:
            continue
        out.append(_row(label, url=url, kind=kind, src=base))
    return out


# ── 団体ごと ────────────────────────────────────────────────────────

def parse_toys(raws: list[str], base: str) -> list[dict]:
    return _anchor_list(raws[0], base, "正会員")


def parse_jppma(raws: list[str], base: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<p class="list_title"><a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                         raws[0], re.S | re.I):
        name = strip_tags(m.group(2), " ").strip()
        if name and not _NOISE.match(name):
            out.append(_row(name, url=m.group(1), kind="正会員", src=base))
    return out


def parse_jpm(raws: list[str], base: str) -> list[dict]:
    return _anchor_list(raws[0], base, "組合員")


def parse_jaama(raws: list[str], base: str) -> list[dict]:
    out = []
    for url, label in links(raws[0], base):
        if not label or _NOISE.match(label) or len(label) < 2:
            continue
        if "member-companies" in url or url.startswith("http") and "jaama.gr.jp" not in url:
            out.append(_row(label, url=url if "jaama.gr.jp" not in url else "",
                            kind="正会員", src=base))
    return out


def parse_petfood(raws: list[str], base: str) -> list[dict]:
    """1社 = 1 <table>。会社名 / 郵便番号 / 住所 / 取扱品目 / URL / PR / 問合せ先。"""
    out = []
    for block in re.findall(r"<table>(.*?)</table>", raws[0], re.S | re.I):
        fields = {}
        for th, td in re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", block, re.S | re.I):
            fields[strip_tags(th, " ").strip()] = td
        name = strip_tags(fields.get("会社名", ""), " ").strip()
        if not name:
            continue
        url = ""
        u = links(fields.get("URL", ""), base)
        if u:
            url = u[0][0]
        contact = flat_text(fields.get("問合せ先", ""))
        tel, _kind, fax = phone.pick_tel_and_fax(contact)
        out.append(_row(name, url=url, tel=tel or "", fax=fax or "",
                        items=flat_text(fields.get("取扱品目", "")).strip(),
                        addr=flat_text(fields.get("住所", "")).strip(),
                        kind="正会員", src=base))
    return out


def parse_jaspo(raws: list[str], base: str) -> list[dict]:
    """tablepress の行: № / 会社名(a) / 〒 / 住所 / TEL・FAX。

    サトルの S-B は TEL を 2 件しか数えていないが、それは `(011)-826-3533` 形式が
    正規表現に掛からなかっただけで、実際は全行に TEL/FAX が載っている。
    """
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", raws[0], re.S | re.I):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        if len(tds) < 5:
            continue
        name = strip_tags(tds[1], " ").strip()
        if not name or _NOISE.match(name):
            continue
        url = ""
        u = links(tds[1], base)
        if u and u[0][0].startswith("http") and "jaspo.org" not in u[0][0]:
            url = u[0][0]
        nums = phone.find_all(flat_text(tds[4]))
        tel = nums[0]["番号"] if nums else ""
        fax = nums[1]["番号"] if len(nums) > 1 else ""
        out.append(_row(name, url=url, tel=tel, fax=fax,
                        addr=flat_text(tds[3]).strip(), kind="会員", src=base))
    return out


def parse_jaftma(raws: list[str], base: str) -> list[dict]:
    """<li> ごとに <h2>社名</h2> + dl（業種・取扱品名 / 所在地 / TEL / FAX）。"""
    out = []
    for raw in raws:
        for li in re.findall(r"<li>(.*?)</li>", raw, re.S | re.I):
            m = re.search(r"<h2>(.*?)</h2>", li, re.S | re.I)
            if not m:
                continue
            name = re.sub(r"<span>.*?</span>", "", m.group(1), flags=re.S)
            name = strip_tags(name, " ").strip()
            if not name:
                continue
            dl = dict(zip(
                [strip_tags(d, " ").strip() for d in re.findall(r"<dt>(.*?)</dt>", li, re.S)],
                [strip_tags(d, " ").strip() for d in re.findall(r"<dd>(.*?)</dd>", li, re.S)]))
            url = ""
            for u, _lb in links(li, base):
                if u.startswith("http") and "jaftma.or.jp" not in u:
                    url = u
                    break
            out.append(_row(name, url=url,
                            tel=dl.get("TEL", ""), fax=dl.get("FAX", ""),
                            items=dl.get("業種・取扱品名", ""),
                            addr=dl.get("所在地", ""), kind="会員", src=base))
    return out


def parse_napac(raws: list[str], base: str) -> list[dict]:
    """一覧には社名しかない。TEL/FAX/URL は各社の詳細ページ（要ネットアクセス）。"""
    L = text_lines(raws[0])
    try:
        j = L.index("ＡＰ８２プレゼントキャンペーン")
        i = [k for k, l in enumerate(L) if l == "会員一覧" and k < j][-1]
    except (ValueError, IndexError):
        return []
    return [_row(n, kind="会員", src=base)
            for n in L[i + 1:j] if not _NOISE.match(n) and len(n) > 1]


def parse_houseware(raws: list[str], base: str) -> list[dict]:
    """同上。詳細ページ /company/<id>/ に TEL/FAX/HP/主な製品がある。"""
    L = text_lines(raws[0])
    try:
        i = L.index("企業⼀覧")
        j = L.index("取扱製品種別で探す")
    except ValueError:
        return []
    return [_row(n, kind="組合員", src=base)
            for n in L[i + 1:j] if not _NOISE.match(n) and len(n) > 1]


PARSERS = {
    "toys": parse_toys, "jppma": parse_jppma, "petfood": parse_petfood,
    "jaspo": parse_jaspo, "jaftma": parse_jaftma, "jpm": parse_jpm,
    "jaama": parse_jaama, "napac": parse_napac, "houseware": parse_houseware,
}

# 一覧ページだけでは4項目が埋まらない団体（詳細ページの取得＝05 の判定待ち）
NEEDS_DETAIL_PAGES = ("napac", "houseware")
