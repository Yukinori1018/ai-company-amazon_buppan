#!/usr/bin/env python3
"""CLAUDE.md §3.3 の**5番目**「メーカー直販・ブランド公式がカートを持つ棚も避ける」の判定。

なぜ別ファイルか
----------------
成果物24 の `verdict.py` は「Amazon 本体かどうか」の3点チェックです。
2026-09-30、B0FN3NWKYZ（サンワダイレクト LED作業灯）は**その3点をすべて PASS**しました
（本体不在・オファー1本）。しかし実画面のカート保持者は
「サンワサプライ直営【サンワダイレクト】」＝**メーカー本人**で、見送りになりました。

つまり必要なのは「本体か否か」ではなく「**原価を持っている相手か否か**」です。
本体チェックと独立した4番目のチェックとして足します。

このモジュールはネットワークにも環境変数にも触りません（純関数）。
入力はセラー名の文字列だけなので、`test_pipeline.py` で全分岐をテストできます。

判定の方針（社長への提案を1件も汚さないため）
--------------------------------------------
- **一致したら FAIL（NO-GO）。** セラー名がブランド名／メーカー名を含む。
- **匂うだけなら UNKNOWN。** 「公式」「直営」を名乗るがブランド名と一致しない、
  オファーが1社しかないがセラー名では確かめられない ── これは人（カズヨ）が実画面で見ます。
  **確信が持てないものを NO-GO にすると、落とした理由が後から検算できません。**
- **セラー名が取れなければ UNKNOWN。** 「名前が無いから直販ではない」は 9/30 の事故と同型です。
"""

from __future__ import annotations

import re
import unicodedata

# verdict.py と同じ3値を使う（判定語彙を1つに保つ）。
PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

# 「公式ストア」を名乗る語。これ単体では FAIL にしない（UNKNOWN に落とす）。
OFFICIAL_WORDS = ("直営", "公式", "オフィシャル", "official", "直販", "メーカー直送", "本店")

# 法人格・販路名など、ブランド一致の判定から取り除く語。
# これを残すと「株式会社」同士で一致してしまいます。
NOISE_WORDS = (
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社", "一般社団法人",
    "(株)", "（株）", "㈱", "(有)", "（有）", "㈲",
    "co.,ltd", "co.ltd", "coltd", "ltd", "inc", "corp", "corporation", "company",
    "store", "shop", "ストア", "ショップ", "店", "直営", "公式", "オフィシャル",
    "official", "amazon", "楽天", "yahoo",
)

# 日本語は2文字でもブランドが成立する（例「グンゼ」は3文字だが「明治」は2文字）。
MIN_KEY_LEN_JA = 2
# ASCII は短い語が偶然一致しやすいので長めに取る（"ism" が "prism" に当たる等を防ぐ）。
MIN_KEY_LEN_ASCII = 4


def normalize(name: str | None) -> str:
    """比較用にセラー名・ブランド名を畳む。

    NFKC で全角英数と半角を揃え、記号・空白・法人格を落として小文字にする。
    「サンワサプライ直営【サンワダイレクト】」→「サンワサプライサンワダイレクト」
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name)).lower()
    s = re.sub(r"[\s　]+", "", s)
    s = re.sub(r"[【】\[\]()（）{}<>《》「」『』・,.\-_/\\|&+*'\"!?:;~=@#%^]", "", s)
    for w in NOISE_WORDS:
        s = s.replace(unicodedata.normalize("NFKC", w).lower(), "")
    return s


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def brand_keys(*names: str | None) -> list[str]:
    """ブランド名・メーカー名から、一致判定に使う鍵を作る。

    「不二貿易(Fujiboeki)」のような併記は、括弧・空白で割って**両方**を鍵にします
    （カタカナとローマ字はプログラムでは変換できないので、書いてある分だけ使う）。
    """
    keys: list[str] = []
    for name in names:
        if not name:
            continue
        raw = unicodedata.normalize("NFKC", str(name))
        for part in re.split(r"[\s　()（）【】\[\]/|,、・]+", raw):
            k = normalize(part)
            if k and k not in keys:
                keys.append(k)
        whole = normalize(raw)
        if whole and whole not in keys:
            keys.append(whole)
    return keys


def _floor(key: str) -> int:
    return MIN_KEY_LEN_ASCII if _is_ascii(key) else MIN_KEY_LEN_JA


def matched_brand_key(seller_name: str | None, keys: list[str]) -> str | None:
    """セラー名の中にブランドの鍵が入っていれば、その鍵を返す。"""
    s = normalize(seller_name)
    if not s:
        return None
    for k in keys:
        if not k:
            continue
        # 短い鍵（"ISM" など）は部分一致だと "PRISM" に当たってしまうので、完全一致だけ。
        if len(k) < _floor(k):
            if s == k:
                return k
            continue
        if k in s or (len(s) >= MIN_KEY_LEN_JA and s in k):
            return k
    return None


def found_official_word(seller_name: str | None) -> str | None:
    s = unicodedata.normalize("NFKC", str(seller_name or "")).lower()
    for w in OFFICIAL_WORDS:
        if unicodedata.normalize("NFKC", w).lower() in s:
            return w
    return None


def detect_maker_direct(
    brand: str | None,
    manufacturer: str | None,
    cart_seller_name: str | None,
    live_offer_count: int | None,
    other_seller_names: list[str] | None = None,
) -> tuple[str, str, dict]:
    """(status, reason, evidence) を返す。status は PASS / FAIL / UNKNOWN。

    引数
      brand / manufacturer : Keepa の brand・manufacturer
      cart_seller_name     : いまカートを持っているセラーの表示名（Keepa /seller）
      live_offer_count     : ライブの新品オファー数
      other_seller_names   : カート保持者以外の出品者名（1社しかいない棚の裏取りに使う）
    """
    keys = brand_keys(brand, manufacturer)
    names = [n for n in ([cart_seller_name] + list(other_seller_names or [])) if n]
    evidence = {
        "brand_keys": keys,
        "cart_seller_name": cart_seller_name,
        "live_offer_count": live_offer_count,
        "other_seller_names": list(other_seller_names or []),
    }

    if not cart_seller_name:
        if live_offer_count == 1:
            return (UNKNOWN,
                    "新品オファーが1社だけですが、そのセラー名が取れませんでした。"
                    "「オファーが少ない」はメーカー1社販売のサインのことがあります。実画面で確認を。",
                    evidence)
        return (UNKNOWN,
                "カート保持者のセラー名が取得できず、メーカー直販かを判定できません。",
                evidence)

    hit = matched_brand_key(cart_seller_name, keys)
    if hit:
        evidence["matched_key"] = hit
        return (FAIL,
                f"カート保持者『{cart_seller_name}』がブランド／メーカー名（{hit}）を含みます。"
                "メーカー本人・ブランド公式が相手では値下げ合戦に勝てず、"
                "販売者限定化や知財申立てで排除される側に回ります。",
                evidence)

    word = found_official_word(cart_seller_name)
    if word:
        evidence["official_word"] = word
        return (UNKNOWN,
                f"カート保持者『{cart_seller_name}』が「{word}」を名乗っています。"
                "ブランド名との一致は取れませんでした。実画面で誰の店かを確認してください。",
                evidence)

    if live_offer_count == 1:
        other_hit = next((k for n in names if (k := matched_brand_key(n, keys))), None)
        if other_hit:
            evidence["matched_key"] = other_hit
            return (FAIL,
                    f"新品オファーは1社のみで、その出品者がブランド名（{other_hit}）を含みます。"
                    "メーカーが1社で売っている棚です。",
                    evidence)
        return (UNKNOWN,
                f"新品オファーが1社（『{cart_seller_name}』）だけです。"
                "ブランド名とは一致しませんが、卸を1社に限定している棚の可能性があります。実画面で確認を。",
                evidence)

    return (PASS,
            f"カート保持者『{cart_seller_name}』はブランド／メーカー名と一致せず、"
            f"新品オファーも{live_offer_count}社あります（メーカー直販の兆候なし）。",
            evidence)
