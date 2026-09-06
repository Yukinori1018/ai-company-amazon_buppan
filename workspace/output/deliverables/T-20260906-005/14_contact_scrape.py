# -*- coding: utf-8 -*-
"""候補メーカーの公式サイトから TEL と問い合わせ導線を実測する（推測しない）。"""
import re, html, subprocess, sys, csv
from pathlib import Path
from urllib.parse import urljoin

OUT = Path("/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/agent_output/T-20260906-005")

SITES = [
    ("株式会社宇野刷毛ブラシ製作所", "https://unobrush.jp/about/"),
    ("有限会社大橋量器", "https://www.masukoubou.jp/corporate.html"),
    ("株式会社木村硝子店", "https://zizi.kimuraglass.jp/pages/company"),
    ("朝倉染布株式会社", "https://www.asakura-senpu.co.jp/company/company-profile/"),
    ("廣田硝子株式会社", "https://hirota-glass.co.jp/contact/"),
    ("河野製紙株式会社", "https://www.kawano-p.co.jp/about/profile/"),
    ("守田漆器株式会社", "https://urusi.jp/contact/"),
    ("池本刷子工業株式会社", "http://www.ikemoto-brush.co.jp/about/"),
    ("楠橋紋織株式会社", "https://www.kusubashi.jp/pages/company"),
    ("側島製罐株式会社", "https://sobajima.jp/company/"),
    ("金野タオル株式会社", "https://www.kinno.co.jp/company.html"),
    ("金野タオル株式会社(OEM)", "https://www.kinno.co.jp/oem.html"),
    ("本野はきもの工業", "https://motono-hakimono.com/about"),
    ("株式会社北尾化粧品部", "http://kitao.co.jp/company/about/"),
    ("株式会社清水硝子", "https://www.shimizuglass.com/"),
    ("木内籐材工業株式会社", "https://www.kiuchi-tohzai.co.jp/original8.html"),
    ("小野甚味噌醤油醸造株式会社", "https://onojin.co.jp/"),
    ("七福タオル株式会社", "https://oem.shichifuku-towel.co.jp/"),
    ("株式会社高柳製茶", "https://www.makinohara-cha.com/c_6/"),
    ("亀﨑染工有限会社", "https://kamesomeya.net/"),
    ("田中帽子店", "https://tanaka-hat.jp/fs/tanakahat/c/company"),
]

TEL = re.compile(r"0\d{1,4}[-(‐−（]\s?\d{1,4}\s?[-)‐−）]\s?\d{3,4}")
CONTACT = re.compile(r'href=["\']([^"\']*(contact|inquiry|toiawase|otoiawase|お問)[^"\']*)["\']', re.I)
WHOLESALE = re.compile(r"(卸|お取引|取引先|代理店|OEM|別注|業務用|法人のお客様|BtoB|小ロット)")


def raw(u):
    p = subprocess.run(["curl", "-skL", "--compressed", "--max-time", "25", "-A",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", u], capture_output=True)
    b = p.stdout
    t = b.decode("utf-8", "replace")
    low = t.lower()
    if "charset=shift_jis" in low or "charset=x-sjis" in low:
        t = b.decode("shift_jis", "replace")
    elif "charset=euc-jp" in low:
        t = b.decode("euc-jp", "replace")
    return t


w = csv.writer(open(OUT / "41_contacts.csv", "w", encoding="utf-8", newline=""))
w.writerow(["company", "url", "tel_found", "contact_urls", "wholesale_words", "ok"])
for name, u in SITES:
    try:
        t = raw(u)
    except Exception as e:
        w.writerow([name, u, "", "", "", f"ERR {e}"]); print(name, "ERR", e); continue
    body = re.sub(r"<script.*?</script>", "", t, flags=re.S | re.I)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", body))
    txt = re.sub(r"\s+", " ", txt)
    tels = sorted(set(TEL.findall(txt)))[:4]
    cs = sorted({urljoin(u, m[0]) for m in CONTACT.findall(t)})[:4]
    ws = sorted(set(WHOLESALE.findall(txt)))
    ok = "OK" if (tels or cs) else ("BLOCKED" if "Verifying your connection" in txt else "NOFIND")
    w.writerow([name, u, " / ".join(tels), " / ".join(cs), " ".join(ws), ok])
    print(f"{name}\n  tel={tels}\n  contact={cs}\n  words={ws}  {ok}", flush=True)
