# -*- coding: utf-8 -*-
"""「営業メールお断り」の検知（特定電子メール法 施行規則3条ただし書）。

法務ハルオの判定 B §9-3 が実装を要求している機能です。

    自己の電子メールアドレスと併せて特定電子メールの送信をしないように求める旨の
    文言を…公衆が閲覧することができる状態に置いたときは、この限りではない。

つまり **「メールアドレスが載っているページに『営業お断り』と書いてあったら、
そのアドレスへ営業メールを送ってはいけない」**。判定は収集時点で行い、結果を
`email_optout_notice` として保存します（後から探し直せない設計は不可）。

ハルオの指示どおり **単純 OR 検索ではなく近接判定** にしてあります。
「営業」と「お断り」が同じページのどこかにあるだけでは true にしません
（例: 「営業時間」と「品切れの節はお断り」が別ブロックにある誤検知を避ける）。

このモジュールは純粋関数だけです。ネットワークにも出ませんし、状態も持ちません。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

#: 「営業・勧誘のたぐい」を指す語
SUBJECT_WORDS = (
    "営業メール", "営業目的", "営業のご連絡", "営業に関する", "勧誘", "セールス",
    "売り込み", "売込み", "広告メール", "宣伝メール", "ＤＭ", "DM",
    "ダイレクトメール", "特定電子メール", "営業活動",
)

#: 「拒否」を指す語
REFUSAL_WORDS = (
    "お断り", "固くお断り", "堅くお断り", "ご遠慮", "遠慮", "受け付けておりません",
    "受付けておりません", "受け付けません", "お控え", "禁止", "しないでください",
    "ご容赦",
)

#: この文字数以内に両方が現れたら「同一ブロック内の共起」とみなす。
#: 日本語の1文（読点込み）はおおむね60字前後。前後の言い回しを見込んで広めに取る。
DEFAULT_WINDOW = 80


def _positions(text: str, words) -> List[Tuple[int, str]]:
    found = []
    for w in words:
        for m in re.finditer(re.escape(w), text):
            found.append((m.start(), w))
    return sorted(found)


def detect_optout(text: str, window: int = DEFAULT_WINDOW) -> Optional[str]:
    """営業お断りの意思表示を検出したら、根拠になった箇所の抜粋を返す。

    見つからなければ None。呼び出し側は `detect_optout(...) is not None` を
    `email_optout_notice` に入れ、抜粋を備考に残してください。

    >>> detect_optout("営業目的のメールは固くお断りいたします。") is not None
    True
    >>> detect_optout("営業時間は9:00〜17:00です。") is None
    True
    """
    if not text:
        return None
    # 空白・改行を潰してから距離を測る（HTML 由来の大量の空白で距離が伸びるのを防ぐ）
    flat = re.sub(r"\s+", "", text)
    subjects = _positions(flat, SUBJECT_WORDS)
    refusals = _positions(flat, REFUSAL_WORDS)
    if not subjects or not refusals:
        return None
    for s_pos, s_word in subjects:
        for r_pos, r_word in refusals:
            if abs(r_pos - s_pos) <= window:
                lo = max(0, min(s_pos, r_pos) - 20)
                hi = min(len(flat), max(s_pos + len(s_word), r_pos + len(r_word)) + 20)
                return flat[lo:hi]
    return None


def is_personal_local_part(email: str) -> bool:
    """メールのローカル部が姓名らしいか（法務 B §9-3 の personal_suspect）。

    法的には送信可でも、個人宛と受け取られた瞬間に取引の芽が消えるので実務上は外す。
    組織アドレス（info / support / sales / contact ...）は false。

    >>> is_personal_local_part("t.suzuki@example.co.jp")
    True
    >>> is_personal_local_part("info@example.co.jp")
    False
    """
    if "@" not in email:
        return False
    local = email.split("@", 1)[0].lower()
    ORG = (
        "info", "support", "sales", "contact", "inquiry", "otoiawase", "toiawase",
        "office", "mail", "shop", "order", "service", "customer", "cs", "help",
        "admin", "press", "recruit", "webmaster", "post", "master", "hello",
        "ask", "desk", "team", "staff", "center", "centre", "reception", "box",
    )
    # 組織を示す語を含んでいたら人名ではない。
    # 例: askfender.jp / customerservice.japan / infobox — いずれも姓名ではなく窓口名。
    if any(w in local for w in ORG):
        return False
    # 国・言語コードが混じるのは窓口の地域指定（例: xxx.jp / xxx-japan）
    if any(seg in ("jp", "japan", "jpn", "en", "us", "global") for seg in re.split(r"[._-]", local)):
        return False
    # first.last / f.last / first_last / firstlast の形。数字が主体なら人名ではない
    if re.fullmatch(r"[a-z]{2,}[._-][a-z]{2,}", local):
        return True
    if re.fullmatch(r"[a-z]\.[a-z]{2,}", local):
        return True
    return False
