# -*- coding: utf-8 -*-
"""住所から**部屋番号・室番号**だけを落とす。

なぜ必要か（2026-09-04 / T-20260904-004・秘書カズヨ判断）:
  本リポジトリは PUBLIC で30分ごとに自動 push される。
  法人が特定商取引法に基づく表記として自ら公表している住所なので、
  再掲載は法的には成立する。**それでも載せない。**
  理由は単純で、**打診経路は電話・フォーム・メールであり、住所は使わないから。**
  使わない情報でリスクを取る理由がない。

  きっかけは、ハナミスイ(609号室)とクリアストーン(709号室)の本店が
  「セントラルパークタワー・ラ・トゥール新宿」＝オフィスビルではなく
  **住友不動産の高級賃貸レジデンス**だったこと。

何を落とし、何を残すか:
  落とす … 号室 / 階＋号 / F-数字 / Room N / Suite・Apt・Unit・#N（住所欄のみ）
  残す  … **階・F 単体**（例「15階」「9F」）。
          フロアは建物の階であって住戸を特定しない。112社に付いていて、
          しかも「小さな雑居ビルの一室か、大手町の高層階か」は
          相手の規模を推し量る材料になる。落とすと情報だけ減って安全は増えない。
  残す  … 建物名。居住用物件を本店にしている事実そのものは
          「小規模＝本丸候補」のシグナルとして残したい（社長判断）。

注意:
  「2丁目5番1号」「1号館」を壊さないこと。`\\d+号` を単体で拾ってはいけない。
  ここを間違えると、伏せ字どころか**住所が別の場所になる**。
"""
from __future__ import annotations
import re

MARK = "【非掲載:部屋番号】"

# 自由文にも当ててよいもの。
#
# ★ここに何を置くかで事故が起きた（2026-09-04）。
# 最初 `F-\d+` と `Room \d+` もここに置いて全文に当てたところ、
#   「Arrows We2 F-52E」（スマホの型番）
#   「GIVI ZT480F-2」（バイク部品の品番）
# を住所の部屋番号と誤認して**商品名を破壊した**。
# `\d+号室` は日本語の文中で部屋番号以外にほぼ現れないが、
# `F-数字` や `#数字` は型番・品番・脚注番号として大量に現れる。
# **住所だと宣言された欄でしか当ててはいけない。**
_COMMON = [
    re.compile(r"\d+\s*階\s*\d+\s*号(?!室)"),          # 5階501号  ※号室より先に評価
    re.compile(r"\d+\s*号室"),                          # 303号室
]
# 住所欄にだけ当てるもの。
# 自由文（型番・品番・Markdown の脚注 [#42]・Python のコメント）で
# 必ず誤爆するので、address_field=True のときしか動かさない。
_ADDRESS_ONLY = [
    re.compile(r"\d+\s*[FfＦ]\s*[-‐－ー]\s*\d+"),        # 5F-501
    re.compile(r"[Rr]oom\s*\.?\s*\d+[A-Za-z]?"),        # Room 302
    re.compile(r"#\s*\d{2,}[A-Za-z]?"),                 # #2594
    re.compile(r"\b(?:Suite|Ste|Apt|Unit)\.?\s*#?\s*\d+[A-Za-z]?", re.I),
]


def strip_unit_number(text: str, address_field: bool = False) -> tuple[str, list[str]]:
    """部屋番号を落とした文字列と、落とした語の一覧を返す。

    address_field=True は「この文字列は住所そのもの」という宣言。
    自由文で誤爆する `#2594` 系の判定を有効にする。
    """
    if not text:
        return text, []
    removed: list[str] = []
    out = text
    for pat in _COMMON + (_ADDRESS_ONLY if address_field else []):
        def _sub(m):
            removed.append(m.group(0))
            return MARK
        out = pat.sub(_sub, out)
    if removed:
        # 「ビル 【非掲載】」のような余分な空白・区切りを整える
        out = re.sub(r"\s+" + re.escape(MARK), MARK, out)
        out = re.sub(r"[,、]\s*" + re.escape(MARK), MARK, out)
        # ここで out.strip().rstrip("、,") をしていたが、**入力全体を trim していた**。
        # 住所1件に当てるぶんには無害でも、CSV 全文に当てると
        # 最終行の末尾カンマと改行まで削って、無関係な行に差分が出た。
        # 伏せ字関数が入力を勝手に整形してはいけない。触るのは印の周りだけ。
    return out, removed


def has_unit_number(text: str, address_field: bool = False) -> bool:
    return bool(strip_unit_number(text, address_field)[1])
