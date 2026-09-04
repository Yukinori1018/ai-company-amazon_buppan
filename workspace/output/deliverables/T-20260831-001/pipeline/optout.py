# -*- coding: utf-8 -*-
"""「営業お断り」表示の A〜E 判定（法務ハルオのルールに従う実装）。

ルールは**このコードに書かない**。法務が管理する機械可読ファイルを読む。

    workspace/output/deliverables/T-20260904-004/B1L_optout_rules.json

法務が判定を変えたら JSON を差し替えるだけで挙動が変わる。コードは判定器であって
判定基準ではない。（2026-09-04 / T-20260904-004 の法務判定 v1.0 に対応）

## 判定の骨格（法務判定より）

仕入れ打診は特定電子メールに当たらないので、「営業お断り」表示があっても**法律上は送れる**。
判定軸は法の可否ではなく **「通報誘発確率」**。送信ドメインのレピュテーションは
451社すべてへの到達を支える共有資産で、1社の通報が残り450社を巻き添えにする。

| class | action | priority | 意味 |
|---|---|---:|---|
| A_PLUS | contact | 1 | 取引窓口が明示されている |
| A | contact | 2 | 表示なし |
| B | contact_restricted | 3 | 経路指定あり（書面のみ 等） |
| C | hold | 9 | 売り込み・提案お断り。A/B消化後・1回限り |
| D | exclude | 99 | NO-GO |
| E | exclude | 99 | 取引条件を構造的に満たさない |

## 実装上の3つの注意（法務からの申し送り。この実装で守っていること）

1. **「営業」の誤爆を防ぐ** — `営業部` `営業時間` `営業日` `営業所` `営業担当` は
   `false_positive_guard` で除外し、**拒絶語との近接（同一文、または±30文字以内）でのみ**
   ヒットさせる。単純な部分一致はしない。→ `_cooccur()`
2. **抽出範囲をフォーム周辺の注記ブロックに限定する** — **これはコードでは強制できない。**
   `classify_window()` に渡すのは1つの窓口の注記ブロックだけにすること。
   ページ全文を渡すと会社概要や採用ページの「営業」に引っかかる。呼び出し側の責任。
3. **窓口単位で判定し、最も緩い有効な窓口を採用する** — → `pick_company_class()`

## E を会社単位で扱っている件（法務に確認したい点・下記 E_IS_COMPANY_WIDE）

法務の scope_note は「最も緩い有効な窓口を採用する」だが、E（実店舗必須・モール出品禁止）は
**窓口の話ではなく会社の取引条件**である。純粋に「最も緩い窓口」を採ると、
すごろくや（卸ページに実店舗必須、一般問い合わせフォームには表示なし）が A になってしまい、
明らかに誤る。よって **E だけは会社単位で固定**する実装にした。
勝手に変えたのではなく、**判断が要る点として明示してある**。法務の確認が取れるまでこの挙動。
"""
from __future__ import annotations

import io
import json
import os
import re
from typing import Dict, List, Optional, Sequence

DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "T-20260904-004", "B1L_optout_rules.json",
)

#: E（構造的な取引条件）だけは窓口ではなく会社に付く。上のドキュメント参照。
E_IS_COMPANY_WIDE = True

_SENTENCE_SPLIT = re.compile(r"[。．！？!?\n\r]+")


# --- ルールの読み込み -------------------------------------------------------
_CACHE = {}  # type: Dict[str, dict]


def load_rules(path: str = None) -> dict:
    path = path or DEFAULT_RULES_PATH
    if path not in _CACHE:
        with io.open(path, encoding="utf-8") as fp:
            _CACHE[path] = json.load(fp)
    return _CACHE[path]


# --- マッチャ ---------------------------------------------------------------
class UnknownMatchKind(Exception):
    """法務ルールに、実装が知らない match 種別があった。

    **黙って読み飛ばさない。** 読み飛ばすと法務が塞いだ穴が実装側で開いたまま
    になり、しかも「0件ヒット」は「該当なし」と見分けがつかないので誰も気づかない。
    v1.0 で A1 の否定右辺が落ちていた事故が、まさにこれだった（法務 v1.1 の要求）。
    """


KNOWN_MATCH_KINDS = frozenset(("cooccur", "any", "suffix_negation"))


def _guarded_positions(text: str, term: str, guards: Sequence[str]) -> List[int]:
    """`term` の出現位置のうち、`guards`（営業部・営業時間 等）の一部でないものを返す。

    >>> _guarded_positions("営業部までご連絡ください", "営業", ["営業部"])
    []
    >>> _guarded_positions("営業のご連絡はお断り", "営業", ["営業部"])
    [0]
    """
    out = []
    for m in re.finditer(re.escape(term), text):
        start = m.start()
        blocked = False
        for g in guards or ():
            # guard 語が term の出現位置を覆っているか
            for gm in re.finditer(re.escape(g), text):
                if gm.start() <= start < gm.end():
                    blocked = True
                    break
            if blocked:
                break
        if not blocked:
            out.append(start)
    return out


def _same_sentence(text: str, i: int, j: int) -> bool:
    """2つの位置が同一文に属するか。"""
    lo, hi = (i, j) if i <= j else (j, i)
    return not _SENTENCE_SPLIT.search(text[lo:hi])


def _cooccur(text: str, left: Sequence[str], right: Sequence[str],
             window: int, guards: Sequence[str] = ()) -> List[str]:
    """left と right が「同一文」または「±window文字以内」で共起したらヒット語を返す。"""
    hits = []
    for lt in left or ():
        for li in _guarded_positions(text, lt, guards):
            for rt in right or ():
                for rm in re.finditer(re.escape(rt), text):
                    ri = rm.start()
                    if abs(ri - li) <= window or _same_sentence(text, li, ri):
                        pair = "%s+%s" % (lt, rt)
                        if pair not in hits:
                            hits.append(pair)
    return hits


def _any_term(text: str, terms: Sequence[str]) -> List[str]:
    return [t for t in (terms or ()) if t in text]


def _left_guarded(text: str, li: int, guards: Sequence[str], win: int) -> bool:
    """left 語の出現位置の**直前** win 文字以内にガード語があるか。

    『一般のお客様との直接のお取引は行っておりません』は、
    卸専業の会社が消費者向けに書いている文であって、当社への拒絶ではない。
    むしろ本命に近い。ここを D にすると本丸を捨てる。
    """
    head = text[max(0, li - win):li]
    return any(g in head for g in guards or ())


def _sentence_re(rules: dict):
    """文の区切り。**実装で決め打ちしない。** ルールファイルが持つ。

    収集した注記原文は複数の窓口ブロックを『／』で連結しているため、
    そこをまたぐ判定は**別窓口の文言を混ぜる**ことになる（法務 v1.2）。
    逆に『、』『・』は区切りに含めない。含めると
    『企業・店舗様との新規お取引は行っておりません』という正当な D を落とす。
    """
    delims = rules.get("sentence_delimiters") or ["。", "．", "！", "？", "!", "?", "\n", "\r"]
    return re.compile("[" + re.escape("".join(delims)) + "]+")


def _first_sentence(text: str, sent_re) -> str:
    return sent_re.split(text)[0] if sent_re else text


def _suffix_negation(text: str, rule: dict, sent_re=None) -> List[str]:
    """left 語の**直後** lookahead 文字以内に否定語があるときだけヒット。

    ★方向を持つこと自体が要求である。無方向の共起で代用してはならない。
      代用すると『新規お取引はこちらから。なお電話はお受けしておりません』が
      D になり、**打てる相手を捨てる。**（法務 v1.1 engine_requirements）
    """
    look = rule.get("negation_lookahead_chars", 25)
    gwin = rule.get("left_context_window_chars", 20)
    guards = rule.get("left_context_guard", ())
    hits: List[str] = []
    for lt in rule.get("left", ()):
        for m in re.finditer(re.escape(lt), text):
            li = m.start()
            if _left_guarded(text, li, guards, gwin):
                continue
            # ★(a) lookahead 文字数 かつ (b) 同一文内 の**両方**が要る（法務 v1.2）。
            #   法務の要求文は lookahead を「直後25文字以内」としか書いていないが、
            #   同じ engine_requirements が
            #   『新規お取引はこちらから。なお電話はお受けしておりません』を
            #   **D にしてはならない例として名指ししている。**
            #   この文では否定語が17文字先＝25文字以内にあるため、
            #   文字数だけで判定すると要求文と実装が矛盾する。
            #   要求（この文を D にしない）が上位なので、句点をまたがせない。
            #   ※文字数だけで足りないことは法務ルール側にも書かれていないので、
            #     v1.2 で明文化してもらうよう差し戻す。ここでクラスは変えていない。
            tail = _first_sentence(text[m.end():m.end() + look], sent_re)
            for ng in rule.get("negation", ()):
                if ng in tail:
                    pair = "%s+%s" % (lt, ng)
                    if pair not in hits:
                        hits.append(pair)
                    break
    return hits


def _drop_negated(text: str, terms: List[str], rule: dict, sent_re=None) -> List[str]:
    """`any` のヒットのうち、直後が否定のものを落とす。

    A1（取引窓口＝A_PLUS）用。『新規お取引は行っておりません』を
    最優先の打診先にしてしまう、**誤りの向きが最悪**の欠陥を塞ぐ。
    """
    ngs = rule.get("negation_terms")
    if not ngs:
        return terms
    look = rule.get("negation_lookahead_chars", 25)
    kept = []
    for t in terms:
        alive = False
        for m in re.finditer(re.escape(t), text):
            # ★D6 と同一条件（文字数かつ同一文内）。
            #   v1.1 は文字数だけで、句点をまたぐ否定で
            #   **正当な A_PLUS を A に降格**させていた（母数を減らす方向の誤り）。
            tail = _first_sentence(text[m.end():m.end() + look], sent_re)
            if not any(ng in tail for ng in ngs):
                alive = True
                break
        if alive:
            kept.append(t)
    return kept


def _rule_hits(text: str, rule: dict, window: int, sent_re=None) -> List[str]:
    kind = rule.get("match")
    hits = []
    if kind == "cooccur":
        hits = _cooccur(text, rule.get("left"), rule.get("right"), window,
                        rule.get("false_positive_guard", ()))
        if not hits and rule.get("alt_terms"):
            hits = _any_term(text, rule["alt_terms"])
    elif kind == "any":
        hits = _drop_negated(text, _any_term(text, rule.get("terms")), rule, sent_re)
        alt = rule.get("cooccur_alt")
        if not hits and alt:
            hits = _cooccur(text, alt.get("left"), alt.get("right"), window)
    elif kind == "suffix_negation":
        hits = _suffix_negation(text, rule, sent_re)
    else:
        raise UnknownMatchKind(
            "規則 %s の match 種別 %r を実装が知らない。"
            "黙って読み飛ばすと法務が塞いだ穴が開いたままになる。"
            % (rule.get("id"), kind))
    return hits


# --- 窓口1つの判定 ----------------------------------------------------------
def classify_window(text: str, source_url: str = "", rules: dict = None) -> dict:
    """**1つの窓口の注記ブロック**を判定する。ページ全文を渡さないこと（注意②）。

    戻り値は法務の output_schema に対応する dict。
    """
    rules = rules or load_rules()
    window = rules.get("proximity_window_chars", 30)
    classes = rules["classes"]
    text = text or ""

    sent_re = _sentence_re(rules)

    # ★まず**全クラス・全規則**を評価する。勝者を決めるのはその後。
    #
    #   v1.1 は apply_order の先頭から回して、最初に当たったクラスで break していた。
    #   そのため「勝たなかったクラスの規則」が一度も見られず、
    #   **判定と無関係な理由でフラグと証跡が静かに消えた。**
    #   実例: 適用順を E→D にしたら、ハイメスが E4（needs_review なし）で確定し、
    #   同時に発火していた D6（needs_review あり）のフラグを落とした。
    #   結論は E で変わらないのに、レビュー対象から外れた（法務 v1.2）。
    fired = []                       # [(class, rule, hits)]
    for rule in rules["rules"]:
        hits = _rule_hits(text, rule, window, sent_re)
        if hits:
            fired.append((rule["class"], rule, hits))

    order = list(rules["apply_order"])
    matched_class = next((c for c in order if any(fc == c for fc, _r, _h in fired)), None)

    matched_ids = []
    hit_terms = []
    allowed = None
    remove = []
    rechecks = []
    e_subclass = ""
    needs_review = False
    review_reasons = []
    other_hits = []

    # 走査順は rules の並び順そのまま。JSON の並びが D → A_PLUS になっており、
    # apply_order で並べ替えても結果が変わらないことを確認したので、
    # **並べ替えは持たない。**テストで守れない処理は置かない。
    for cls, rule, hits in fired:
        # needs_review は**発火した全規則**から立てる（勝敗と無関係）。
        if rule.get("needs_review"):
            needs_review = True
            if rule.get("reason"):
                review_reasons.append(rule["reason"])
        if cls != matched_class:
            # 勝たなかった規則は証跡として残す。
            # E が勝った社に D3（通報明示）も当たっていた、という事実を失わない。
            # 判定が正しくても**なぜ除外したのかが分からなくなる**のを防ぐ。
            other_hits.append(rule["id"])
            continue
        matched_ids.append(rule["id"])
        hit_terms.extend(hits)
        if rule.get("set_allowed_channels"):
            allowed = list(rule["set_allowed_channels"])
        remove.extend(rule.get("remove_channels", []))
        if rule.get("recheck_condition"):
            rechecks.append(rule["recheck_condition"])
        if rule.get("e_subclass") and not e_subclass:
            e_subclass = rule["e_subclass"]

    if matched_class is None:
        matched_class = "A"

    spec = classes[matched_class]
    if allowed is None:
        ch = spec.get("channels")
        allowed = list(ch) if isinstance(ch, list) else ["form"]
    allowed = [c for c in allowed if c not in remove]

    # review_triggers は**判定を変えない**。フラグだけ立てる（法務 v1.1 の明示要求）。
    # 『〜のみ』は文脈で正反対になる（『卸売のみ』は当社に有利、
    # 『既存取引先のみ』は実質的な新規拒否）。機械で断定してはならない。
    trig = rules.get("review_triggers") or {}
    fired = [t for k, v in trig.items()
             if k not in ("$comment", "reason") and isinstance(v, list)
             for t in v if t in text]
    if fired:
        needs_review = True
        review_reasons.append("%s（該当語: %s）"
                              % (trig.get("reason", "人の確認が必要"),
                                 "、".join(dict.fromkeys(fired))))
    # ★ recheck_condition は**実際にヒットした規則のもの**だけを使う。
    #   クラス単位でフォールバックすると、D2（営業お断り）に当たった社に
    #   D5（採用専用）の再評価条件『取引窓口の新設』が付いてしまう。実際に踏んだ。

    return {
        "optout_class": matched_class,
        "optout_hit_terms": ";".join(dict.fromkeys(hit_terms)),
        "optout_rule_ids": ";".join(matched_ids),
        "allowed_channels": allowed,
        "contact_priority": spec["priority"],
        "action": spec["action"],
        "optout_source_url": source_url,
        "recheck_condition": " ／ ".join(dict.fromkeys(rechecks)),
        "optout_e_subclass": e_subclass,
        "optout_needs_review": needs_review,
        "optout_other_rule_hits": ";".join(dict.fromkeys(other_hits)),
        "optout_review_reason": " ／ ".join(dict.fromkeys(review_reasons)),
    }


# --- 会社としての採用（窓口が複数あるとき） ---------------------------------
def pick_company_class(window_results: List[dict]) -> Optional[dict]:
    """窓口ごとの判定から、会社として採用する1件を選ぶ。

    法務 scope_note: **最も緩い有効な窓口を採用する**（priority が小さいほど緩い）。
    ただし E は会社の取引条件なので窓口をまたいで固定する（E_IS_COMPANY_WIDE 参照）。

    >>> pick_company_class([{"optout_class":"E","contact_priority":99},
    ...                     {"optout_class":"A","contact_priority":2}])["optout_class"]
    'E'
    >>> pick_company_class([{"optout_class":"D","contact_priority":99},
    ...                     {"optout_class":"A","contact_priority":2}])["optout_class"]
    'A'
    """
    if not window_results:
        return None
    if E_IS_COMPANY_WIDE:
        for r in window_results:
            if r.get("optout_class") == "E":
                return r
    return min(window_results, key=lambda r: r.get("contact_priority", 99))


# --- 送信フェーズの必須ルール（後工程へ渡すため機械可読で公開する） ---------
def message_rules(rules: dict = None) -> List[str]:
    """打診文の必須ルール。**ヒデアキの文案作成の入力になる。**

    最重要は1行目：**本文・署名にURLを一切貼らない。**貼った瞬間に
    特定電子メール法2条2号の『広告宣伝ウェブサイトへの誘導』に当たり、
    相手の「営業お断り」表示が法的効力を持つ。白が黒に転ぶ唯一の分岐点。
    """
    return list((rules or load_rules()).get("mandatory_message_rules", []))


def individual_decisions(rules: dict = None) -> Dict[str, dict]:
    """法務が個社について明示した判定（自動判定より優先する）。"""
    # ★company だけで引くと、表記ゆれの重複行に個別判断が乗らず、
    #   **除外したはずの会社が別表記で打診キューに残る。**
    #   ストームレーベルズが3表記で登録され、D が付いたのは1行だけだった
    #   （2026-09-04 検出。法務 v1.1 engine_requirements）。
    out: Dict[str, dict] = {}
    for d in (rules or load_rules()).get("individual_decisions", []):
        for key in [d["company"]] + list(d.get("aliases", ())):
            out.setdefault(key, d)
    return out


# --- 個人名らしいローカル部（従来からの機能。法務B §9-3 personal_suspect） ---
def is_personal_local_part(email: str) -> bool:
    """メールのローカル部が姓名らしいか。組織アドレスは False。

    >>> is_personal_local_part("t.suzuki@example.co.jp")
    True
    >>> is_personal_local_part("info@example.co.jp")
    False
    """
    if "@" not in (email or ""):
        return False
    local = email.split("@", 1)[0].lower()
    ORG = (
        "info", "support", "sales", "contact", "inquiry", "otoiawase", "toiawase",
        "office", "mail", "shop", "order", "service", "customer", "cs", "help",
        "admin", "press", "recruit", "webmaster", "post", "master", "hello",
        "ask", "desk", "team", "staff", "center", "centre", "reception", "box",
    )
    if any(w in local for w in ORG):
        return False
    if any(seg in ("jp", "japan", "jpn", "en", "us", "global")
           for seg in re.split(r"[._-]", local)):
        return False
    if re.fullmatch(r"[a-z]{2,}[._-][a-z]{2,}", local):
        return True
    if re.fullmatch(r"[a-z]\.[a-z]{2,}", local):
        return True
    return False


#: A1_trade_window の否定形誤爆を検知するための表現。
#: **これは判定基準ではなく、判定基準の穴を見つけるための検査器。**
#: 法務ルール（B1L_optout_rules.json）は法務ハルオの所有物なので触らない。
NEGATION_SUFFIXES = (
    "行っておりません", "行っていません", "お受けしておりません",
    "受け付けておりません", "しておりません", "お断り", "できません",
    "ご遠慮", "対象外", "限らせて", "のみ",
)

#: ヒット語の直後どれだけを否定表現の探索範囲にするか（文字数）。
#: 前方は別の文である可能性が高いので見ない。
NEGATION_LOOKAHEAD = 25


def detect_negated_trade_window(notice: str, hit_terms: str,
                                lookahead: int = NEGATION_LOOKAHEAD):
    """「取引窓口あり」と読めた語の直後が否定だったら、その事実を返す。

    A1_trade_window は「新規お取引」「卸売」「代理店」等を**肯定のシグナル**として拾うが、
    規則に右辺（否定語）が無い。そのため次のように**意味が正反対に転ぶ**。

        「新規お取引は行っておりません」        → A_PLUS（最優先で打診）
        「海外代理店への販売のみ」（＝直販しない）→ A_PLUS

    どちらも「打診してはいけない相手が、最優先で打診すべき相手に化ける」方向の誤りで、
    間違った相手に連絡してしまう。**取れなかったより悪い。**

    返り値は (ヒット語, 否定語, 原文の該当箇所) のタプル。該当なしなら None。
    **クラスを決めない。**呼び出し側が needs_review を立てて人に回すこと。

    >>> detect_negated_trade_window("新規お取引は行っておりません", "新規お取引")[1]
    '行っておりません'
    >>> detect_negated_trade_window("新規お取引はこちらのフォームから", "新規お取引") is None
    True
    """
    if not notice or not hit_terms:
        return None
    flat = re.sub(r"\s+", "", notice)
    for term in [t.strip() for t in hit_terms.split(";") if t.strip()]:
        for m in re.finditer(re.escape(term), flat):
            tail = flat[m.end():m.end() + lookahead]
            for ng in NEGATION_SUFFIXES:
                if ng in tail:
                    return (term, ng, flat[m.start():m.end() + lookahead])
    return None
