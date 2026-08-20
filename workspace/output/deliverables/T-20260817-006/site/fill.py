# -*- coding: utf-8 -*-
"""
Satoy Select サイト 情報うめこみスクリプト
============================================
使い方（ターミナルで1行）:

    python3 fill.py

質問に順に答えるだけで、隣に「公開用」フォルダができます。
そのフォルダの中身をまるごとサーバーへアップロードすれば公開完了です。

※ 何度でもやり直せます（元のファイルは書き換えません）。
※ 途中でやめたいときは Ctrl+C を押してください。
"""

import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "公開用")

TARGET_EXT = (".html", ".xml", ".txt")

QUESTIONS = [
    ("DOMAIN", "独自ドメイン（例: satoyselect.com）※ https:// や www. は不要", "satoyselect.com", True),
    ("OWNER_NAME", "代表者のお名前（例: 佐藤 幸則）", "", True),
    ("ADDRESS", "所在地（郵便番号から番地まで／例: 〒000-0000 東京都〇〇区〇〇1-2-3）", "", True),
    ("EMAIL", "メールアドレス ※サイトには載りません。メーカー様へお渡しする会社概要PDFにのみ使います", "", True),
    ("TEL", "電話番号（050番号で構いません／未取得なら空エンターでスキップ）", "", False),
    ("FAX", "FAX番号（未取得なら空エンターでスキップ）", "", False),
    ("OPEN_DATE", "開業年月（例: 2026年8月）", "", True),
    ("STORE_URL", "AmazonストアのURL（未開設なら空エンターでスキップ）",
     "https://www.amazon.co.jp/shops/...", False),
    ("FORM_URL", "GoogleフォームのURL（お問い合わせフォーム用／未作成なら空エンター）",
     "https://docs.google.com/forms/d/e/.../viewform", False),
]


def ask(key, label, example, required):
    hint = f"（例: {example}）" if example else ""
    while True:
        try:
            v = input(f"\n■ {label}{hint}\n  → ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n中断しました。")
            sys.exit(1)
        if v:
            return v
        if not required:
            return ""
        print("  ※ この項目は必須です。もう一度入力してください。")


def show_only(html, name, keep):
    """<!--NAME_START-->〜<!--NAME_END--> を、keep が真なら残し、偽なら中身ごと削除する"""
    if keep:
        return html.replace("<!--%s_START-->" % name, "").replace("<!--%s_END-->" % name, "")
    return re.sub(r"<!--%s_START-->.*?<!--%s_END-->" % (name, name), "", html, flags=re.S)


def strip_empty_blocks(html, values):
    """空欄になった項目の行・ブロックをまるごと消す"""
    open_ = bool(values.get("STORE_URL"))          # ストアURLの有無＝開店済みかどうか
    form_ok = bool(values.get("_FORM_READY"))      # フォームの送信先が確定しているか

    html = show_only(html, "STORE", open_)         # 開店後だけ「ストアで見る」を出す
    html = show_only(html, "PREOPEN", not open_)   # 開店前だけ「準備中」を出す
    embed = bool(values.get("_FORM_EMBED"))        # 項目IDを読めなかったときの埋め込み表示
    html = show_only(html, "FORM", form_ok)             # 自前デザインのフォーム
    html = show_only(html, "FORM_EMBED", embed)         # Googleフォームをそのまま埋め込み
    html = show_only(html, "FORM_UNSET", not (form_ok or embed))  # どちらも無ければ案内文
    # contact.html の .contact-row（電話 / FAX）
    for key in ("TEL", "FAX"):
        if values.get(key):
            continue
        html = re.sub(
            r'\s*<div class="contact-row">(?:(?!</div>\s*</div>).)*?\{\{' + key + r'\}\}.*?</div>\s*</div>',
            "",
            html,
            flags=re.S,
        )
    # about.html の会社概要テーブル行
    for key in ("TEL", "FAX"):
        if values.get(key):
            continue
        html = re.sub(r"\s*<tr><th>[^<]*</th><td>\{\{" + key + r"\}\}.*?</tr>", "", html, flags=re.S)
    # フッターの TEL 表記
    if not values.get("TEL"):
        html = html.replace("TEL: {{TEL}}／Email: {{EMAIL}}", "Email: {{EMAIL}}")
    return html



# ---------------------------------------------------------------
# Googleフォームの項目ID（entry.xxxxx）を、公開URLから自動で読み取る
# ---------------------------------------------------------------
FORM_FIELDS = [
    ("ENTRY_NAME",    ("お名前", "名前", "氏名")),
    ("ENTRY_EMAIL",   ("メール",)),
    ("ENTRY_TYPE",    ("ご用件", "用件", "種別")),
    ("ENTRY_MESSAGE", ("内容", "本文", "ご相談")),
    ("ENTRY_NOTIFY",  ("お知らせ", "新着", "入荷")),
]


def resolve_form(form_url):
    """GoogleフォームのURL → (送信先URL, {ENTRY_*: entry.123456})

    見つからない項目があれば、その旨のメッセージを添えて返す。
    """
    import json
    import urllib.request

    url = form_url.strip()
    if "/viewform" not in url and "/formResponse" not in url:
        url = url.rstrip("/") + "/viewform"
    view = url.split("?")[0].replace("/formResponse", "/viewform")
    action = view.replace("/viewform", "/formResponse")

    try:
        req = urllib.request.Request(view, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, {}, "フォームのページを開けませんでした（%s）。URLと公開設定をご確認ください。" % e

    m = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\]);", page, re.S)
    if not m:
        return None, {}, "フォームの項目を読み取れませんでした。URLが「回答用のリンク」か確認してください。"

    try:
        data = json.loads(m.group(1))
        items = data[1][1]
    except Exception:
        return None, {}, "フォームの項目を読み取れませんでした（形式が想定と異なります）。"

    found = {}
    for it in items:
        try:
            title = (it[1] or "")
            entry_id = it[4][0][0]
        except Exception:
            continue
        for key, words in FORM_FIELDS:
            if key in found:
                continue
            if any(w in title for w in words):
                found[key] = "entry.%s" % entry_id
                break

    missing = [k for k, _ in FORM_FIELDS if k not in found]
    if missing:
        labels = {"ENTRY_NAME": "お名前", "ENTRY_EMAIL": "メールアドレス", "ENTRY_TYPE": "ご用件",
                  "ENTRY_MESSAGE": "お問い合わせ内容", "ENTRY_NOTIFY": "お知らせ希望"}
        return None, {}, "フォームに次の項目が見つかりませんでした: " + "、".join(labels[k] for k in missing)

    return action, found, ""


CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def make_pdf():
    """会社概要 profile.html を PDF に変換（Chrome があれば自動、無ければ手動手順を案内）"""
    src = os.path.join(OUT, "profile.html")
    dst = os.path.join(OUT, "Satoy-Select_会社概要.pdf")
    if not os.path.exists(src):
        return "（会社概要 profile.html が見つかりませんでした）"

    chrome = next((p for p in CHROME_PATHS if os.path.exists(p)), None)
    if chrome:
        import subprocess
        import tempfile

        tmp = tempfile.mkdtemp(prefix="satoy-pdf-")
        try:
            subprocess.run(
                [chrome, "--headless", "--disable-gpu", "--no-sandbox",
                 f"--user-data-dir={tmp}",
                 "--no-pdf-header-footer",
                 f"--print-to-pdf={dst}",
                 "file://" + src],
                capture_output=True, timeout=120,
            )
        except Exception:
            pass
        finally:
            # Chrome が書き込み中のファイルを残すことがあるため、失敗しても無視する
            shutil.rmtree(tmp, ignore_errors=True)

        # Chrome の終了コードに関わらず、出力ファイルの実体で判定する
        if os.path.exists(dst) and os.path.getsize(dst) > 1000:
            kb = os.path.getsize(dst) // 1024
            return (f"📄 会社概要PDFを作成しました: Satoy-Select_会社概要.pdf（{kb} KB）\n"
                    "   → メーカー様へのメールに添付してお使いください。")

    return ("📄 会社概要PDFは自動作成できませんでした。\n"
            "   公開用フォルダの profile.html をブラウザで開き、\n"
            "   ⌘P →「PDFとして保存」で書き出してください（同じ体裁で出ます）。")


def main():
    print("=" * 62)
    print(" Satoy Select ホームページ — 情報うめこみ")
    print("=" * 62)
    print("\n9つの質問に答えるだけで、公開できる状態のファイル一式ができます。")
    print("あとから何度でもやり直せますので、気軽に進めてください。")

    values = {}
    for key, label, example, required in QUESTIONS:
        values[key] = ask(key, label, example, required)

    # 確認
    print("\n" + "-" * 62)
    print(" 入力内容の確認")
    print("-" * 62)
    for key, label, _, _ in QUESTIONS:
        print(f"  {label.split('（')[0].split(' ※')[0]:<14}: {values[key] or '（なし）'}")
    try:
        ok = input("\nこの内容で作成しますか？ [y/n] → ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n中断しました。")
        sys.exit(1)
    if ok not in ("y", "yes", ""):
        print("中断しました。もう一度 python3 fill.py を実行してください。")
        sys.exit(0)

    # --- お問い合わせフォームの送信先を解決する ---
    form_msg = "お問い合わせフォーム: 未設定（サイトには「準備中」と表示されます）"
    if values.get("FORM_URL"):
        print("\nフォームの項目を読み取っています…")
        action, entries, err = resolve_form(values["FORM_URL"])
        if action:
            values["FORM_ACTION"] = action
            values.update(entries)
            values["_FORM_READY"] = "1"
            form_msg = "✉️ お問い合わせフォーム: 設定できました（送信内容はフォームの回答先へ届きます）"
        else:
            # 項目IDを読み取れなくても、フォームごと埋め込めば必ず動く
            view = values["FORM_URL"].split("?")[0].rstrip("/")
            if "/viewform" not in view:
                view += "/viewform"
            values["FORM_EMBED_URL"] = view + "?embedded=true"
            values["_FORM_EMBED"] = "1"
            form_msg = ("✉️ お問い合わせフォーム: Googleフォームを埋め込む方式で設定しました。\n"
                        "   （項目の自動読み取りには失敗: " + err + "）\n"
                        "   見た目はGoogleフォームのままですが、送信は問題なく届きます。")
    for key, _ in FORM_FIELDS:
        values.setdefault(key, "")
    values.setdefault("FORM_ACTION", "")
    values.setdefault("FORM_EMBED_URL", "")

    # 出力先を作り直す
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(HERE, OUT, ignore=shutil.ignore_patterns("fill.py", "__pycache__", ".DS_Store"))

    count = 0
    for root, _dirs, files in os.walk(OUT):
        for name in files:
            if not name.endswith(TARGET_EXT):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as f:
                s = f.read()
            s = strip_empty_blocks(s, values)
            for key, val in values.items():
                if key.startswith("_"):
                    continue
                s = s.replace("{{" + key + "}}", val)
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)
            count += 1

    # 埋め残しチェック
    leftovers = []
    for root, _dirs, files in os.walk(OUT):
        for name in files:
            if not name.endswith(TARGET_EXT):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as f:
                for m in set(re.findall(r"\{\{([A-Z_]+)\}\}", f.read())):
                    leftovers.append(f"{name}: {{{{{m}}}}}")

    pdf_msg = make_pdf()

    print("\n" + "=" * 62)
    print(f" 完成しました（{count} ファイルを書き出し）")
    print("=" * 62)
    print(f"\n出力先:\n  {OUT}\n")
    print(pdf_msg + "\n")
    print(form_msg + "\n")
    if leftovers:
        print("⚠️ 未置換が残っています（カズヨに連絡してください）:")
        for l in sorted(set(leftovers)):
            print("   -", l)
    else:
        print("✅ 未置換の項目はありません。")
    print("\n次の手順:")
    print("  1. 上の「公開用」フォルダの中身を、まるごとサーバーへアップロード")
    print("  2. ブラウザで https://" + values["DOMAIN"] + "/ を開いて表示を確認")
    print("  3. Google Search Console にドメインを登録し、サイトマップを送信")
    print("     （詳しい手順は 公開手順書.html をご覧ください）\n")


if __name__ == "__main__":
    main()
