#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-1 本走行：上位50社の結果を「連絡先 × 利益が取れそう」の1枚にまとめる。

カズヨ発注（2026-09-04）の指示③「社長が次に見るのは連絡先が分かった × 利益が取れそうの交差点」への回答。
B1_work_queue.csv（利益ヒューリスティック順）と exa_lookups.jsonl（実取得）を結合する。
"""
from __future__ import annotations
import csv, io, json, os, re, sys
sys.path.insert(0, os.path.join(HERE_PIPE, "pipeline") if False else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "T-20260831-001", "pipeline"))
from redact import strip_unit_number  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DELIV = os.path.dirname(HERE)
QUEUE = os.path.join(HERE, "B1_work_queue.csv")
V14 = os.path.join(DELIV, "T-20260817-005", "v14", "03_メーカー名寄せ.csv")
JSONL = os.path.join(DELIV, "T-20260831-001", "pipeline", "data", "exa_lookups.jsonl")
OUT = os.path.join(HERE, "B1_contacts_top50.csv")

CONTACT = ("電話", "問い合わせフォームURL", "メール")

COLS = ["順位","スコア","メーカー名", "宛名の注意",
        # --- 法務ハルオの A〜E 判定（B1L_optout_rules.json v1.0）---
        "optout_class","optout_notice_status","contact_priority","action","allowed_channels",
        "optout_hit_terms","optout_rule_ids","form_optout_notice","optout_source_url",
        "optout_checked_at","recheck_condition","optout_e_subclass","optout_decided_by","optout_needs_review","optout_review_reason","optout_other_rule_hits",
        # --- 連絡先 ---
        "正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール","確度",
        "取引可否シグナル","備考","出典URL",
        # --- Amazon 実績（利益が取れそうか）---
        "該当商品数","主なカテゴリ","想定仕入れ金額の中央値","Amazon価格の中央値","代表商品名"]

#: CSV の先頭に置く注記。**打診文を書くヒデアキへの申し送りを、CSV自体に載せる。**
#: 法務判定：本文・署名にURLを貼った瞬間に特定電子メール法2条2号の
#: 「広告宣伝ウェブサイトへの誘導」に当たり、相手の「営業お断り」表示が法的効力を持つ。
HEADER_NOTE = (
    "# 【打診文の絶対条件・法務判定 v1.1】メール本文・署名にURLを一切貼らないこと"
    "（AmazonストアURL・自社サイト satoy-select.com・SNS すべて）。"
    "貼った瞬間に特定電子メール法2条2号の『広告宣伝ウェブサイトへの誘導』に該当し、"
    "相手の『営業お断り』表示が法的効力を持つ。白が黒に転ぶ唯一の分岐点。"
    " ／ 1社1通・追送しない・断られたら即終了・一斉送信ツール禁止・実績ゼロを正直に書く。"
    " ／ optout_class が D・E の社には打診しない。C は A/A_PLUS/B を全件消化した後・フォームのみ・1回限り。"
    " ／ 【optout_notice_status を必ず併せて読むこと】この列が『未取得』の社は、"
    "お断り表示が無いことを確認できていない（窓口ページを検分した記録が無い）だけで、"
    "**表示が無いと確認した社ではない**。399社中『注記あり』66・『確認済み_表示なし』34・"
    "『未取得』299。したがって『打診可能◯◯社』という数字を単独で読まないこと。"
    "打診前にその社の窓口ページを一度開いて表示を確認する。")


def load_lookups():
    idx = {}
    with io.open(JSONL, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            idx[e["メーカー名"]] = e   # 後勝ち
    return idx


def signal(entry, note):
    """備考から取引可否のシグナルを1語に落とす。**判定材料であって結論ではない。**"""
    if not entry:
        return "未処理"
    if "名寄せの取りこぼし" in note:
        return "重複(同一法人の別行)"
    if entry.get("form_optout_notice") == "true":
        return "要注意(拒否表示あり)"
    if not any((entry.get(k) or "").strip() for k in CONTACT):
        return "連絡不可"
    if "本丸" in note or "OEM" in note or "少量" in note or "B2B" in note or "卸取引" in note:
        return "有望(小ロット/OEM/B2Bの明示あり)"
    for w in ("大手", "直取引の相手ではない", "取次", "仕入れ先ではない",
              "上場", "ライセンス管理", "配給", "レコード会社", "直販は行わない",
              "直販窓口ではない", "消費者向け窓口"):
        if w in note:
            return "対象外(大手/流通構造)"
    return "連絡可"


def build_all_rows(lookups, v14, contacts_cls):
    """**両バッチ合計の全社**を、法務の打診優先度順に並べる。B-2（サトル）の入力。"""
    rows = []
    for name, e in lookups.items():
        v = v14.get(name, {})
        row = {c: "" for c in COLS}
        row["メーカー名"] = name
        for k in ("正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール",
                  "確度","備考","出典URL","optout_class","optout_notice_status",
                  "contact_priority","action",
                  "allowed_channels","optout_hit_terms","optout_rule_ids","form_optout_notice",
                  "optout_source_url","optout_checked_at","recheck_condition",
                  "optout_e_subclass","optout_decided_by",
                  "optout_needs_review","optout_review_reason","optout_other_rule_hits"):
            row[k] = e.get(k, "")
        for k, src in (("該当商品数","該当商品数"), ("主なカテゴリ","主なカテゴリ"),
                       ("想定仕入れ金額の中央値","想定仕入れ金額の中央値"),
                       ("Amazon価格の中央値","Amazon価格の中央値"), ("代表商品名","代表商品名")):
            row[k] = v.get(src, "")
        row["取引可否シグナル"] = signal(e, e.get("備考", ""))
        rows.append(row)
    rows.sort(key=lambda r: (int(r["contact_priority"] or 99), -_int(r["該当商品数"]), r["メーカー名"]))
    for i, r in enumerate(rows, 1):
        r["順位"] = i
    return rows


#: PUBLIC リポに実データを出さない列。個人事業主の疑いがある社に適用する。
REDACTED_COLS = ("正式商号", "所在地", "公式HP", "電話", "問い合わせフォームURL", "メール", "出典URL")

#: 伏せた旨の表示。空欄だと「調べたが取れなかった」と区別がつかないので必ず書く。
REDACTED_MARK = "【非掲載】個人事業主の疑いのため PUBLIC リポには掲載しない（実データは agent_output 側）"

#: 伏せた実データの退避先（.gitignore 配下＝Git 追跡外）
HELD_BACK = os.path.join(DELIV, "..", "agent_output", "T-20260904-004", "B1",
                         "HELD_BACK_個人事業主疑い.jsonl")


def redact_sole_proprietors(rows, lookups):
    """個人事業主の疑いがある社の連絡先を、成果物CSVから外す。

    **このリポジトリは PUBLIC で30分ごとに自動 push される。**
    法人の代表電話は事業者情報だが、個人事業主の電話・住所は個人情報になりうる。
    法務B §8-5 に従い、掲載可否の判断が出るまで実データを出さない。

    **手作業で消さないこと。** CSV を手で編集しても次のビルドで復活する。
    ここで落とすから再現性がある。伏せた実データは agent_output 側の JSONL に退避し、
    社長の掲載可否判断が出たら復活させられるようにしておく。
    """
    held = []
    for r in rows:
        e = lookups.get(r.get("メーカー名", "")) or {}
        if not (e.get("entity_type") or "").startswith("個人事業主"):
            continue
        held.append({k: e.get(k, "") for k in
                     ("メーカー名", "entity_type", "正式商号", "所在地", "公式HP",
                      "電話", "問い合わせフォームURL", "メール", "出典URL", "備考")})
        for c in REDACTED_COLS:
            if r.get(c):
                r[c] = REDACTED_MARK
        r["取引可否シグナル"] = "保留(個人事業主の疑い・掲載可否は社長判断)"
    if held:
        os.makedirs(os.path.dirname(os.path.abspath(HELD_BACK)), exist_ok=True)
        existing = {}
        if os.path.exists(HELD_BACK):
            for line in io.open(HELD_BACK, encoding="utf-8"):
                if line.strip():
                    h = json.loads(line)
                    existing[h.get("メーカー名", "")] = h
        for h in held:                      # 後勝ちで上書き（冪等）
            existing[h["メーカー名"]] = h
        with io.open(HELD_BACK, "w", encoding="utf-8") as fp:
            for h in existing.values():
                fp.write(json.dumps(h, ensure_ascii=False) + "\n")
    return held


def _int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return 0



# --- 出力直前に全行へかける後処理 -------------------------------------
# 手で消しても次のビルドで復活する、を繰り返さないためにコードに置く。

def _addressee_warning(r):
    """**キューの名称をそのまま宛名に使うと届かない行**にだけ警告を立てる。

    情報自体は 正式商号 と 備考 に書いてあるが、どちらも長文で、
    社長がリストを上から流すときに読み飛ばす。1列に切り出して目に入れる。

    ★何を立てないかの方が大事。
      最初「備考に『商号変更』とあるか」で拾って19件、うち多くが
      「矢崎エナジーシステム㈱ → 矢崎エナジーシステム株式会社」の表記違いだけ。
      次に「メーカー名が正式商号に含まれるか」で拾ったら113件になり、
      その大半が `BUNDOK → 株式会社カワセ` のような**ブランド名と法人名の違い**だった。
      それは異常ではなく普通のことで、しかも隣の 正式商号 列を見れば分かる。
      **狼少年になった警告は読まれない。** 立てるのは次の3つだけにする。

        1. その名前の法人が存在しない  … 出しても届かない
        2. 旧商号                     … 出しても届かない
        3. そもそもメーカー名ではない   … 出す先が無い

      重複は危険ではないので、警告ではなく事実として添える。
    """
    formal = r.get("正式商号") or ""
    blob = " ".join((formal, r.get("備考") or "", r.get("entity_type") or ""))
    if (r.get("確度") or "") == "抽出ノイズ":
        return "⚠ メーカー名ではない（抽出ノイズ）。打診先なし"
    if ("現存しない法人" in blob or "法人格が存在しない" in blob
            or "吸収合併により消滅" in blob):
        return "⚠ この名称の法人は存在しない。宛名は正式商号を使うこと"
    if "旧商号" in formal:
        return "⚠ 旧商号。宛名は正式商号を使うこと"
    if "【重複" in blob:
        return "重複。別エントリと同じ打診先"
    return ""


def finalize(rows):
    """PUBLIC リポに出す直前の共通処理。伏せ字 → 宛名の注意 の順。"""
    for r in rows:
        # 部屋番号は落とす。建物名は残す（規模のシグナルになるため）。
        # 打診経路は電話・フォーム・メールで、住所は使わない。
        # 使わない情報でリスクを取らない（2026-09-04 秘書カズヨ判断）。
        r["所在地"], _ = strip_unit_number(r.get("所在地") or "", address_field=True)
        r["備考"], _ = strip_unit_number(r.get("備考") or "", address_field=False)
        r["宛名の注意"] = _addressee_warning(r)
    return rows


def main():
    lookups = load_lookups()
    with io.open(QUEUE, encoding="utf-8-sig") as fp:
        queue = list(csv.DictReader(fp))

    rows = []
    for q in queue:
        e = lookups.get(q["メーカー名"]) or {}
        note = e.get("備考", "")
        row = {c: "" for c in COLS}
        row.update({k: q.get(k, "") for k in
                    ("順位","スコア","メーカー名","該当商品数","主なカテゴリ",
                     "想定仕入れ金額の中央値","Amazon価格の中央値","代表商品名")})
        for k in ("正式商号","法人番号","所在地","公式HP","電話",
                  "問い合わせフォームURL","メール","確度","備考","出典URL",
                  "optout_class","optout_notice_status","contact_priority","action","allowed_channels",
                  "optout_hit_terms","optout_rule_ids","form_optout_notice",
                  "optout_source_url","optout_checked_at","recheck_condition",
                  "optout_e_subclass","optout_decided_by",
                  "optout_needs_review","optout_review_reason","optout_other_rule_hits"):
            row[k] = e.get(k, "")
        row["取引可否シグナル"] = signal(e if e else None, note)
        rows.append(row)

    # ★D/E を top50 から外してから50社を切る。
    #
    # **以前は queue の先頭50社をそのまま top50 にしていた。**
    # その結果、法務判定が D（営業お断りの明示）や E（当社を名指しで取引対象外）の社が
    # 「打診候補 上位50社」に3社混ざっていた（岩手県木炭協会・エリエール・ハイメス）。
    # ヘッダ注記に「D・E には打診しない」と書いてはあるが、
    # **社長はこのファイルを上から順に手を動かすためのリストとして使う。**
    # 打ってはいけない相手を上位50に載せておいて注記で止める設計は、
    # 「間違った連絡先は取れなかったより悪い」という本件の原則に反する。
    # 除外したぶんは後続の社で埋める（50社という枠は維持する）。
    excluded = [r for r in rows if r["optout_class"] in ("D", "E")]
    rows = [r for r in rows if r["optout_class"] not in ("D", "E")][:50]

    # ★PUBLIC リポに出す前に、個人事業主の疑いがある社の連絡先を落とす
    finalize(rows)
    held = redact_sole_proprietors(rows, lookups)

    # 打診優先度順（法務の contact_priority 昇順）にも並べ替えた版を作る
    # ★一時ファイルに書いて、検算に通ってから所定の名前に置く。
    #
    # **このリポジトリは PUBLIC で30分ごとに自動 push される。**
    # 「先に書いて、後から検算して落ちる」順序だと、落ちた瞬間から
    # 次の自動 push までの間、不正なCSVがディスクに残る。
    # 検算が仕事をするほど危険、という逆立ちした設計になるので、
    # 所定の名前に置くのは検算を通ってからにする。
    OUT_TMP = OUT + ".tmp"
    with io.open(OUT_TMP, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(rows)

    # ※ここで B1_打診候補_全社_優先度順.csv を書いていたが、
    #   直後の全社版が同じパスを上書きしていて**書き捨てになっていた**ので削除した。

    # --- 数字 ---
    n = len(rows)
    def cnt(pred): return sum(1 for r in rows if pred(r))
    print("処理: %d社" % n)
    for k in ("正式商号","法人番号","所在地","公式HP","電話","問い合わせフォームURL","メール"):
        c = cnt(lambda r, k=k: r[k].strip())
        print("  %-18s %2d/%d (%3.0f%%)" % (k, c, n, 100.0*c/n))
    reach = cnt(lambda r: any(r[k].strip() for k in CONTACT))
    print("  %-18s %2d/%d (%3.0f%%)" % ("連絡手段1つ以上", reach, n, 100.0*reach/n))
    print()
    import collections
    for k, v in collections.Counter(r["取引可否シグナル"] for r in rows).most_common():
        print("  %-30s %d" % (k, v))
    print()
    print("--- 法務 A〜E 判定 ---")
    for c in ("A_PLUS", "A", "B", "C", "D", "E"):
        n = sum(1 for r in rows if r["optout_class"] == c)
        if n:
            print("  %-7s %2d" % (c, n))
    print("  → top50 から除外した D/E: %d社（%s）"
          % (len(excluded), "、".join(r["メーカー名"] for r in excluded) or "なし"))
    print()
    print("--- 有望・連絡可の社 ---")
    for r in rows:
        if r["取引可否シグナル"].startswith(("有望", "連絡可")):
            print("  %3s %-24s %-14s %s / %s" % (r["順位"], r["メーカー名"][:24],
                  r["主なカテゴリ"][:14], r["電話"] or "-", r["メール"] or "-"))
    # --- 全社版（両バッチ 115社）---
    with io.open(V14, encoding="utf-8-sig") as fp:
        v14 = {r["メーカー/ブランド"]: r for r in csv.DictReader(fp)}
    all_rows = build_all_rows(lookups, v14, None)
    finalize(all_rows)
    held_all = redact_sole_proprietors(all_rows, lookups)
    ALL = os.path.join(HERE, "B1_打診候補_全社_優先度順.csv")
    with io.open(ALL, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write(HEADER_NOTE + "\n")
        w = csv.DictWriter(fp, fieldnames=COLS)
        w.writeheader(); w.writerows(all_rows)
    print("\n=== 全社版（両バッチ合計 %d社）===" % len(all_rows))
    for c in ("A_PLUS", "A", "B", "C", "D", "E"):
        n = sum(1 for r in all_rows if r["optout_class"] == c)
        if n:
            print("  %-7s %3d" % (c, n))
    reach = sum(1 for r in all_rows
                if r["optout_class"] not in ("D", "E")
                and any(r[k].strip() for k in CONTACT))
    print("  → **打診可能（D/E以外 かつ 連絡手段あり）: %d社**" % reach)
    if held_all:
        print("\n=== PUBLIC リポから連絡先を伏せた社（個人事業主の疑い）: %d社 ===" % len(held_all))
        for h in held_all:
            print("  - %s（%s）" % (h["メーカー名"], h["entity_type"]))
        print("  実データ: agent_output/T-20260904-004/B1/HELD_BACK_個人事業主疑い.jsonl")
        print("  → 掲載可否は社長判断。判断が出るまで CSV には出しません。")
    # --- 出したものを、出した直後に検算する ---------------------------
    # 「フィルタを書いた」と「フィルタが効いていた」は別。ここで自分の出力を読み直す。
    def _reread(path):
        ls = io.open(path, encoding="utf-8-sig").read().splitlines(True)
        while ls and ls[0].lstrip("\ufeff").startswith("#"):
            ls.pop(0)
        return list(csv.DictReader(io.StringIO("".join(ls))))
    import io as _io  # noqa
    back = _reread(OUT_TMP)
    leaked = [r["メーカー名"] for r in back if r.get("optout_class") in ("D", "E")]
    bad = ""
    if leaked:
        bad = "top50 に D/E が残っている: %s" % "、".join(leaked)
    elif len(back) != len(rows):
        bad = "top50 の行数が合わない: %d != %d" % (len(back), len(rows))
    if bad:
        os.remove(OUT_TMP)          # 不正なものをディスクに残さない
        raise SystemExit(bad)
    os.replace(OUT_TMP, OUT)        # ここで初めて所定の名前になる
    # ★宣言だけして一度も埋まらない列を捕まえる。
    #   commit ゲートの entity_type、この notice_status と、
    #   **同じ事故を3度やっている**。列を足すのは1箇所では済まず、
    #   COLS・main の取り込み・build_all_rows の取り込みの3箇所に要る。
    #   「列がある」と「列が埋まっている」は別。
    ALLOW_EMPTY = {"optout_e_subclass", "optout_decided_by", "optout_review_reason",
                   "optout_needs_review", "form_optout_notice", "宛名の注意",
                   "optout_hit_terms", "recheck_condition", "optout_rule_ids",
                   "法人番号", "メール", "allowed_channels", "optout_source_url",
                   # 全社版は contact_priority + 順位 で並べるため スコア を持たない
                   # （top50 用のキュー由来の値で、全社側には元データが無い）。
                   # ★これは検算が見つけた既存の穴。仕様として明示しておく。
                   "スコア"}
    for col in COLS:
        if col in ALLOW_EMPTY:
            continue
        if not any(str(r.get(col) or "").strip() for r in all_rows):
            raise SystemExit(
                "列 %r が全%d行で空。宣言しただけで埋め忘れている"
                % (col, len(all_rows)))

    print("検算: top50 に D/E なし（%d行）／ 全列に値あり" % len(back))

    print("\nwrote", OUT)
    print("wrote", ALL)


if __name__ == "__main__":
    main()
