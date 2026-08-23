# -*- coding: utf-8 -*-
"""GoogleフォームのURLを渡すと、fill.py が項目を正しく読めるか事前に検証する。

    python3 check_form.py "https://docs.google.com/forms/d/e/XXXX/viewform"

fill.py 本体を import して同じ resolve_form() を呼ぶので、
ここで OK なら fill.py でも必ず同じ結果になる。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "site"))
from fill import resolve_form, FORM_FIELDS  # noqa: E402

LABELS = {"ENTRY_NAME": "お名前", "ENTRY_EMAIL": "メールアドレス", "ENTRY_TYPE": "ご用件",
          "ENTRY_MESSAGE": "お問い合わせ内容", "ENTRY_NOTIFY": "お知らせ希望"}

if len(sys.argv) < 2:
    print("使い方: python3 check_form.py <GoogleフォームのURL>")
    sys.exit(1)

action, entries, err = resolve_form(sys.argv[1])

print("=" * 54)
print(" Googleフォーム 事前チェック")
print("=" * 54)
if not action:
    print("\n  ✗ 自動読み取りに失敗しました")
    print("    理由:", err)
    print("\n  → このままでも fill.py は「フォームを丸ごと埋め込む」方式に")
    print("    自動で切り替わるので、送信自体は必ず届きます。")
    print("    ただし見た目がGoogleフォームのままになります。")
    sys.exit(1)

print("\n  ✓ 5項目すべて読み取れました。自前デザインのフォームが使えます。\n")
print("  送信先:", action)
for key, _ in FORM_FIELDS:
    print(f"    {LABELS[key]:<12} → {entries[key]}")
print("\n  このURLを fill.py の9問目に貼ってください。")
