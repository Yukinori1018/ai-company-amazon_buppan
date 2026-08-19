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
    ("EMAIL", "メールアドレス（例: info@satoyselect.com）", "", True),
    ("TEL", "電話番号（050番号で構いません／未取得なら空エンターでスキップ）", "", False),
    ("FAX", "FAX番号（未取得なら空エンターでスキップ）", "", False),
    ("OPEN_DATE", "開業年月（例: 2026年8月）", "", True),
    ("STORE_URL", "AmazonストアのURL（未開設なら空エンターでスキップ）",
     "https://www.amazon.co.jp/shops/...", False),
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


def strip_empty_blocks(html, values):
    """空欄になった項目の行・ブロックをまるごと消す"""
    # Amazonストア未開設なら、ストアへの導線をまるごと削除
    if not values.get("STORE_URL"):
        html = re.sub(r"<!--STORE_START-->.*?<!--STORE_END-->", "", html, flags=re.S)
    else:
        html = html.replace("<!--STORE_START-->", "").replace("<!--STORE_END-->", "")
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
    print("\n8つの質問に答えるだけで、公開できる状態のファイル一式ができます。")
    print("あとから何度でもやり直せますので、気軽に進めてください。")

    values = {}
    for key, label, example, required in QUESTIONS:
        values[key] = ask(key, label, example, required)

    # 確認
    print("\n" + "-" * 62)
    print(" 入力内容の確認")
    print("-" * 62)
    for key, label, _, _ in QUESTIONS:
        print(f"  {label.split('（')[0]:<12}: {values[key] or '（なし）'}")
    try:
        ok = input("\nこの内容で作成しますか？ [y/n] → ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n中断しました。")
        sys.exit(1)
    if ok not in ("y", "yes", ""):
        print("中断しました。もう一度 python3 fill.py を実行してください。")
        sys.exit(0)

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
