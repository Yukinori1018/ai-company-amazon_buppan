# -*- coding: utf-8 -*-
"""v1.0 と v1.1 を実データ399社に当てて差分を出す（法務ハルオの検算・回帰テスト）。

実行: python3 B1L_v11_selftest_recheck399.py

optout.py（IT の判定器）をそのまま使い、未実装の match 種別 `suffix_negation` だけを
このスクリプト内で shim して補う。**判定基準は JSON 側にしかない**（コードに書かない）。
"""
import csv, io, json, os, re, sys

ROOT = "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables"
sys.path.insert(0, os.path.join(ROOT, "T-20260831-001", "pipeline"))
import optout as O  # noqa

V10 = os.path.join(ROOT, "T-20260904-004", "B1L_optout_rules_v1.0_snapshot.json")
V11 = os.path.join(ROOT, "T-20260904-004", "B1L_optout_rules.json")
CSV = os.path.join(ROOT, "T-20260904-004", "B1_打診候補_全社_優先度順.csv")


def _flat(t):
    return re.sub(r"\s+", "", t or "")


def _suffix_negation(text, rule, defaults):
    """left 語の直後 N 文字以内に negation 語 → ヒット。直前に guard 語 → 無効。"""
    flat = _flat(text)
    look = rule.get("negation_lookahead_chars", defaults.get("negation_lookahead_chars", 25))
    back = rule.get("left_context_window_chars", defaults.get("left_context_window_chars", 20))
    guards = rule.get("left_context_guard", [])
    hits = []
    for lt in rule.get("left", []):
        for m in re.finditer(re.escape(lt), flat):
            pre = flat[max(0, m.start() - back):m.start()]
            if any(g in pre for g in guards):
                continue
            tail = flat[m.end():m.end() + look]
            for ng in rule.get("negation", []):
                if ng in tail:
                    p = "%s+%s" % (lt, ng)
                    if p not in hits:
                        hits.append(p)
    return hits


def _negation_filtered_any(text, rule, defaults):
    """match=any だが negation_terms を持つ規則（A1）。否定が直後に続く出現は数えない。"""
    flat = _flat(text)
    look = rule.get("negation_lookahead_chars", defaults.get("negation_lookahead_chars", 25))
    negs = rule.get("negation_terms", [])
    hits = []
    for t in rule.get("terms", []):
        for m in re.finditer(re.escape(t), flat):
            tail = flat[m.end():m.end() + look]
            if any(ng in tail for ng in negs):
                continue
            if t not in hits:
                hits.append(t)
    return hits


_orig_rule_hits = O._rule_hits


def make_patched(rules):
    def _patched(text, rule, window):
        if rule.get("match") == "suffix_negation":
            return _suffix_negation(text, rule, rules)
        if rule.get("match") == "any" and rule.get("negation_terms"):
            return _negation_filtered_any(text, rule, rules)
        if rule.get("match") not in ("any", "cooccur", "suffix_negation"):
            raise RuntimeError("unknown match kind: %s (%s)" % (rule.get("match"), rule.get("id")))
        return _orig_rule_hits(text, rule, window)
    return _patched


def load(path):
    with io.open(path, encoding="utf-8") as fp:
        return json.load(fp)


def classify(text, rules):
    O._rule_hits = make_patched(rules)
    return O.classify_window(text, "", rules)


def main():
    r10, r11 = load(V10), load(V11)
    rows = list(csv.reader(io.open(CSV, encoding="utf-8-sig")))
    hdr = rows[1]
    data = [dict(zip(hdr, r)) for r in rows[2:]]

    ind11 = {d["company"]: d for d in r11["individual_decisions"]}

    def norm(name):
        return re.sub(r"[（(].*", "", name).replace("株式会社", "").strip()

    diffs, notice_rows = [], 0
    for d in data:
        text = d["form_optout_notice"]
        if text.strip():
            notice_rows += 1
        c10 = classify(text, r10)
        c11 = classify(text, r11)
        # 個別判断（法務が明示した社）は自動判定に優先
        final11 = c11["optout_class"]
        src11 = "rule:" + (c11["optout_rule_ids"] or "-")
        for comp, dec in ind11.items():
            keys = [comp] + list(dec.get("aliases", []))
            fields = [d["メーカー名"], d.get("正式商号", "")]
            if any(norm(k) and norm(k) in norm(f) for k in keys for f in fields):
                final11 = dec["class"]
                src11 = "individual:" + comp
        cur = d["optout_class"]
        if c10["optout_class"] != c11["optout_class"] or cur != final11:
            diffs.append((d["メーカー名"], cur, c10["optout_class"], c11["optout_class"],
                          final11, src11, c11["optout_hit_terms"], text[:90].replace("\n", " ")))
    print("行数=%d / 注記原文あり=%d" % (len(data), notice_rows))
    print("差分件数=%d" % len(diffs))
    print("| メーカー | CSV現状 | v1.0規則 | v1.1規則 | v1.1最終 | 根拠 | ヒット |")
    for x in diffs:
        print("| %s | %s | %s | %s | %s | %s | %s |" % (x[0], x[1], x[2], x[3], x[4], x[5], x[6]))
    print()
    print("--- 誤爆チェック：v1.1 で D/E に落ちたが v1.0 では A/A_PLUS だった社の原文 ---")
    for x in diffs:
        if x[3] in ("D", "E") and x[2] in ("A", "A_PLUS"):
            print("*", x[0], "|", x[6], "|", x[7])


if __name__ == "__main__":
    main()
