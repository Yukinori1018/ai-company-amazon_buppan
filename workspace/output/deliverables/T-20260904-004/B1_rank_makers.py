#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""和名メーカーを「メーカー直取引が成立しうる順」に並べる（v2）。

## v1 からの変更（2026-09-04 / カズヨ承認 A案）

v1 は粗利率×商品数×回転で並べた。その結果**上位50社の48%が本・DVD・ゲーム**になった。
仕入れ値の安いコンテンツ商材は粗利率が構造的に高く出るためで、しかもこれらは
取次・販売代理店に流通が固定されており**メーカー直取引が成立しない**。

v2 は並べ替えの軸を「儲かりそうか」から**「メーカー直取引が成立しうるか」**に寄せた。

    score = 商品数係数 × 粗利率 × 回転係数 × 予算係数 × カテゴリ係数 × リスク係数
                                                      ~~~~~~~~~~~~~~ 新設
    ただし 既知の大手・コンテンツ流通の社は除外リストで落とす

**`規模フラグ` は使わない。** v14 のこの列は上位50社が全社「中小候補」で、
ディズニー・カプコン・マキタ・講談社も「中小候補」だった。**機能していない列である。**
（memory `knowledge_verify_field_semantics_not_names` と同じ型の事故）

## スコアに入れられないもの（重要・鶏と卵）

カズヨが優先を指示した4シグナル（OEM/受託/小ロット の記載・B2B専用窓口・卸が本業・従業員数が小さい）は、
**連絡先を取ってみるまで分からない**。したがって**並べ替えには使えない**。
これらは取得**後**の `取引可否シグナル` として `B1_build_batch.py` が判定し、
打診候補リストの並びに反映する。**入口（順序）と出口（優先度）を分けてある。**

## カテゴリ係数の根拠

| カテゴリ | 係数 | 理由 |
|---|---:|---|
| 本 / DVD / ミュージック / ゲーム / PCソフト | 0.25 | **取次・販売代理店に流通が固定**。個人事業者との直取引が構造的に成立しない（上位50社で実証） |
| ホーム＆キッチン / DIY・工具 / 産業・研究開発用品 / 文房具・オフィス | 1.3 | **自社工場を持つ中小メーカーが濃い**（曙産業・三輝・愛知電線がここ） |
| おもちゃ / ペット用品 / スポーツ＆アウトドア / ベビー＆マタニティ | 1.2 | 同上（山形工房・鈴木ラテックス・ブリーダーズファームがここ） |
| 車＆バイク / 家電＆カメラ / パソコン・周辺機器 | 1.0 | 中小と大手が混在 |
| その他 | 1.0 | — |

使い方:
    python3 B1_rank_makers.py --write         # B1_work_queue.csv を書き出す
    python3 B1_rank_makers.py --top 50
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DELIVERABLES = os.path.dirname(HERE)

V14 = os.path.join(DELIVERABLES, "T-20260817-005", "v14", "03_メーカー名寄せ.csv")
CONTACTS = os.path.join(DELIVERABLES, "T-20260831-001", "contacts_v1.csv")
QUEUE = os.path.join(HERE, "B1_work_queue.csv")

TARGET_CLASS = "和名法人らしき"
CONTACT_COLS = ("公式HP", "電話", "問い合わせフォームURL", "メール")
UNIT_PRICE_CEILING = 10000   # 総予算5万円 → 5〜10SKU を組むための単価上限

#: コンテンツ商材。取次・販売代理店に流通が固定されており直取引が成立しない。
CONTENT_CATEGORIES = ("本", "DVD", "ミュージック", "ゲーム", "PCソフト", "洋書")

#: 自社工場を持つ中小メーカーが濃いカテゴリ（上位50社の実測に基づく）
MAKER_DENSE_CATEGORIES = (
    "ホーム＆キッチン", "DIY・工具・ガーデン", "産業・研究開発用品", "文房具・オフィス用品",
)
MAKER_LIKELY_CATEGORIES = (
    "おもちゃ", "ペット用品", "スポーツ＆アウトドア", "ベビー＆マタニティ", "ホビー",
)

#: 調査済みだが取得ゼロだった社を再調査しないための除外は、
#: `exa_lookups.jsonl` にエントリがあるかで判定する（下の load_investigated）。
#: `contacts_v1.csv` の充填判定だけでは、**調べた結果ゼロだった社が永久にキューに残る**。

#: 直取引が成立しないと判明／自明な社。**順序ではなく除外で落とす。**
#: `規模フラグ` が使えないため（上位50社が全社「中小候補」だった）、ここを名指しで積み上げる。
#: 判断の根拠を2つに分けて明示しておく:
#:   (a) 上位50社の調査で実際に確認したもの
#:   (b) 上場企業・全国的な著名ブランドであることが公知のもの
#: (b) は私（タカシ）の判断が入る。恣意性を隠さないために別リストにしてある。
#: **除外は「連絡先を取らない」だけで、商品として扱わない意味ではない**（卸経由なら仕入れられる）。
EXCLUDE_CONFIRMED = {   # (a) 実際に調べて確認した
    "ウォルト・ディズニー・ジャパン株式会社", "Disney(ディズニー)", "ポニーキャニオン",
    "コナミデジタルエンタテインメント(Konami Digital Entertainment)", "カプコン(CAPCOM)",
    "ジェイストーム", "講談社", "宝島社", "ワーナーホームビデオ", "ワーナーミュージック・ジャパン",
    "東映", "ビクターエンタテインメント", "アニプレックス", "マイクロソフト", "Makita(マキタ)",
    "エレコム(ELECOM)", "本間ゴルフ", "ロイヤルカナン", "すごろくや", "扶桑社",
    "駿台文庫", "中央法規出版", "技術評論社", "マイナビ出版", "経営科学出版", "オーム社",
    "DVDBOX5枚組",
}
EXCLUDE_MAJOR_BRAND = {  # (b) 上場・全国的著名ブランドで初回小ロット直取引の相手にならない
    "BANDAI SPIRITS(バンダイ スピリッツ)", "CASIO(カシオ)", "Casio", "パナソニック(Panasonic)",
    "NIKE(ナイキ)", "ナイキ(NIKE)", "タカラトミー(TAKARA TOMY)", "サンリオ(SANRIO)",
    "コールマン(Coleman)", "アイリスオーヤマ(IRIS OHYAMA)", "ホンダ(Honda)", "Honda",
    "‎バーベイタム(Verbatim)", "バーベイタム(Verbatim)", "BIALETTI(ビアレッティ)",
    "OOFOS(ウーフォス)", "アルインコ(Alinco)", "ホーチキ(Hochiki)", "三ツ星ベルト(MITSUBOSHI)",
    "クイックル", "四国化成工業", "ニチアス", "ハイポネックス", "TIGORA(ティゴラ)",
    "どうぶつの森", "ワンナイト人狼", "ホビージャパン(HobbyJAPAN)", "Yamazaki(山崎実業)",
    "和平フレイズ(Wahei freiz)",
    "マテル(MATTEL)", "バッファロー", "TOYOTA(トヨタ)", "LEICA(ライカ)",
    "Eufy (ユーフィ)", "Logicool G(ロジクール G)", "金鳥", "東京マルイ(TOKYO MARUI)",
    "phiten(ファイテン)", "マイヤー(Meyer)", "SAPHIR(サフィール)", "デビフ",
    "コーナン",   # ホームセンターのプライベートブランド。メーカーではない
    "ピュアクリスタル",  # ジェックス(GEX)のブランド。同社は東証上場
}
KNOWN_EXCLUDE = EXCLUDE_CONFIRMED | EXCLUDE_MAJOR_BRAND


def load_investigated():
    """`exa_lookups.jsonl` に載っている社＝調査済み。取得ゼロでも再調査しない。"""
    import json
    path = os.path.join(DELIVERABLES, "T-20260831-001", "pipeline", "data", "exa_lookups.jsonl")
    names = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    names.add(json.loads(line)["メーカー名"])
                except (ValueError, KeyError):
                    continue
    return names


def _num(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def category_factor(category: str) -> float:
    """カテゴリからメーカー直取引の成立しやすさを係数にする。

    >>> category_factor("本")
    0.25
    >>> category_factor("ホーム＆キッチン")
    1.3
    >>> category_factor("車＆バイク")
    1.0
    """
    c = (category or "").strip()
    if c in CONTENT_CATEGORIES:
        return 0.25
    if c in MAKER_DENSE_CATEGORIES:
        return 1.3
    if c in MAKER_LIKELY_CATEGORIES:
        return 1.2
    return 1.0


def score_row(v14_row) -> float:
    """1社ぶんのスコア。**利益予測ではなく「先に調べる価値」の順序付け。**

    `想定仕入れ金額の中央値` は推定値であって実測ではない
    （memory `feedback_research_accuracy_blocker`）。金額として読まないこと。
    """
    n = _num(v14_row.get("該当商品数"), 0.0)
    if n <= 0:
        return 0.0
    buy = _num(v14_row.get("想定仕入れ金額の中央値"), 0.0)
    sell = _num(v14_row.get("Amazon価格の中央値"), 0.0)
    months = _num(v14_row.get("消化月数の中央値"), 1.0)
    risk = _num(v14_row.get("リスク区分あり件数"), 0.0)

    if sell <= 0 or buy <= 0:
        return 0.0
    margin = (sell - buy) / sell
    if margin <= 0:
        return 0.0                                   # 赤字は不可（チケットの制約）

    return (
        math.sqrt(n)                                  # 1社から複数SKU取れる方が交渉の価値が高い
        * margin                                      # ※推定値
        * (1.0 / max(months, 1.0))                    # 消化が速いほど資金が回る
        * (1.0 if buy <= UNIT_PRICE_CEILING else 0.3) # 予算5万円で5〜10SKU 組めるか
        * category_factor(v14_row.get("主なカテゴリ"))  # ★v2 で新設
        * (1.0 / (1.0 + risk / n))                    # 出品制限・知財リスクが多い社は後回し
    )


def build_queue():
    """未充填の和名メーカーをスコア降順で返す。既知の大手・処理済みは除く。"""
    with open(V14, encoding="utf-8-sig") as fp:
        v14 = {r["メーカー/ブランド"]: r for r in csv.DictReader(fp)}
    with open(CONTACTS, encoding="utf-8-sig") as fp:
        contacts = list(csv.DictReader(fp))

    investigated = load_investigated()
    out = []
    for c in contacts:
        if (c.get("分類") or "") != TARGET_CLASS:
            continue
        if any((c.get(k) or "").strip() for k in CONTACT_COLS):
            continue                                  # 処理済み（冪等）
        name = c["メーカー名"]
        if name in KNOWN_EXCLUDE or name in investigated:
            continue
        v = v14.get(name)
        if v is None:
            continue
        out.append({
            "順位": 0,
            "メーカー名": name,
            "スコア": round(score_row(v), 4),
            "カテゴリ係数": category_factor(v.get("主なカテゴリ")),
            "該当商品数": v.get("該当商品数", ""),
            "想定仕入れ金額の中央値": v.get("想定仕入れ金額の中央値", ""),
            "Amazon価格の中央値": v.get("Amazon価格の中央値", ""),
            "消化月数の中央値": v.get("消化月数の中央値", ""),
            "主なカテゴリ": v.get("主なカテゴリ", ""),
            "リスク区分あり件数": v.get("リスク区分あり件数", ""),
            "代表商品名": v.get("代表商品名", ""),
            "代表ASIN": v.get("代表ASIN", ""),
        })
    out.sort(key=lambda r: (-r["スコア"], r["メーカー名"]))
    for i, r in enumerate(out, 1):
        r["順位"] = i
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    rows = build_queue()
    print("和名・未充填・大手除外後: %d社" % len(rows), file=sys.stderr)
    import collections
    print("上位50のカテゴリ: %s" % collections.Counter(
        r["主なカテゴリ"] for r in rows[:50]).most_common(), file=sys.stderr)
    if args.write:
        with open(QUEUE, "w", encoding="utf-8-sig", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print("wrote %s" % QUEUE, file=sys.stderr)
    for r in rows[: args.top]:
        print("%4d %7.3f %-26s %2s件 %-14s 仕入%5s→売%5s %s"
              % (r["順位"], r["スコア"], r["メーカー名"][:26], r["該当商品数"],
                 r["主なカテゴリ"][:14], r["想定仕入れ金額の中央値"],
                 r["Amazon価格の中央値"], r["代表商品名"][:30]))


if __name__ == "__main__":
    main()
