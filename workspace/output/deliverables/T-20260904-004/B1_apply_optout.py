#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""法務の A〜E ルールを、取得済みの全社に適用する（B-1 の applier）。

★2026-09-06: agent_output（Git 追跡外）から deliverables へ移設。
  ここが消えると B1_打診候補_全社_優先度順.csv を**作り直せなくなる**。
  出力（exa_lookups.jsonl）だけ追跡していても、判定を当て直す手段が無ければ
  法務ルールが v1.3 になったときに再現できない。

- 注記の**原文**（要約しない）と出典URLを窓口ごとに持たせ、`classify_window()` に掛ける
- 法務が個社を明示している場合（individual_decisions）は**そちらを優先**する
- 窓口が複数ある社は `pick_company_class()` で「最も緩い有効な窓口」を採る
- 注記が見つからなかった社は A（表示なし）。**「調べていない」ではなく「窓口の注記に無かった」**

原文はすべて私（タカシ）が実ページで確認して書き写したもの。出典URLを併記する。
"""
import io, json, os, re, sys

def _repo_root(start):
    """リポジトリの根を**階層の数え上げではなく目印で**探す。

    このファイルは agent_output（Git 追跡外）から deliverables へ移した。
    `".."` を5つ並べる書き方だと、置き場所が1階層変わるだけで黙って別の場所を指す。
    目印（CLAUDE.md）で探せば、どこに置いても同じ場所に着く。
    """
    d = os.path.dirname(os.path.abspath(start))
    while d != os.path.dirname(d):
        if os.path.exists(os.path.join(d, "CLAUDE.md")):
            return d
        d = os.path.dirname(d)
    raise SystemExit("リポジトリの根（CLAUDE.md のある場所）が見つからない: " + start)


REPO = _repo_root(__file__)
sys.path.insert(0, os.path.join(REPO, "workspace/output/deliverables/T-20260831-001"))
from pipeline.optout import (classify_window, pick_company_class,  # noqa: E402
                             individual_decisions, detect_negated_trade_window)

JL = os.path.join(REPO, "workspace/output/deliverables/T-20260831-001/pipeline/data/exa_lookups.jsonl")

#: 窓口ごとの注記原文。{メーカー名: [(窓口名, 原文, 出典URL), ...]}
#: **要約していない。実ページの文言そのまま。**
WINDOWS = {
 "愛知電線": [
   ("メールフォーム",
    "※こちらのメールフォームからのセールス・勧誘等は、「特定電子メールの送信に関する法律」に基づき、固くお断りします。※こちらのメールフォームからセールス・勧誘等があった場合、「迷惑メール相談センター」に通報します。",
    "https://www.aichidensen.co.jp/contact/"),
   ("代表電話", "", "https://www.aichidensen.co.jp/company/"),
 ],
 "すごろくや": [
   ("卸流通事業ページ",
    "実店舗をお持ちでないオンライン専売業者さまとのお取引につきましては一律お断りをさせていただいております。お問い合わせを頂戴いたしましても、ご要望にお応えできないことをあらかじめご了承ください。／弊社商品は、全ての小売店さまが安心して商品をお取扱いし、正当な対価を得ていただけるよう、悪質な海賊版や転売品の横行対策として、Amazon・楽天市場・Yahoo!ショッピング・メルカリなど、大手ECモールへの出品をご遠慮いただいております。",
    "https://sugorokuya.jp/wholesale_guide"),
 ],
 "カプコン(CAPCOM)": [
   ("その他お問い合わせ窓口",
    "※ 当社の製品・サービスに関するお問い合わせにはお答えいたしかねます。※ 営業・ご提案については書面にて、カプコン本社宛にお送りください。",
    "https://www.capcom.co.jp/ir/inquiry/index_01-2.html"),
 ],
 "リッチェル(Richell)": [
   ("法人向けお問い合わせフォーム",
    "商品やサービスの売り込み、製品アイデア等のご提案はご遠慮ください。",
    "https://www.richell.co.jp/form/business/contact.php"),
 ],
 "ジェイストーム": [
   ("（公式サイトに取引窓口の表示なし）", "", "https://www.storm-labels.co.jp/"),
 ],
 "フィッティ": [
   ("お問い合わせフォーム",
    "ご意見・お問い合わせにつきましては、下記専用フォームよりご連絡ください。なお、広告、協賛の依頼、営業活動もしくは営利を目的とするもの等はご遠慮ください。返信は原則として致しておりません。",
    "https://www.tamagawa-eizai.co.jp/support/form/"),
 ],
 "Hikari(ヒカリ)": [
   ("公式トップ",
    "弊社は一般のお客様への直接の販売は致しておりません。",
    "https://www.kyorin-net.co.jp/"),
 ],
 "ブリヂストン(BRIDGESTONE)": [
   ("お客様コールセンター",
    "※ こちらのフリーダイヤルは、一般のお客様専用です。お取引先様からのお問い合わせに関しましては、担当部門へお問い合わせください。",
    "https://jp.golf.bridgestone/callcenter/contact"),
 ],
 "扶桑社": [
   ("お問い合わせ",
    "扶桑社では個人の方向けの直接の書籍販売は行っておりません。お近くの書店、またはオンライン書店にてお申込みください。／【その他のお問い合わせ】法人・団体・企業ほか MAIL： info@fusosha.co.jp",
    "https://www.fusosha.co.jp/"),
 ],
 "ワーナーミュージック・ジャパン": [
   ("お問合せフォーム",
    "以下のような場合は、商品不良のお問合せ対象外となります。・中古品をご購入された場合・新品であっても、フリーマーケット・オークション・個人間のネット通販などでご購入された場合／カスタマーハラスメントとなる行為はご遠慮ください。",
    "https://supportform.jp/wmj"),
 ],
 "コモライフ": [
   ("A&Bトレード利用規約",
    "「Ａ＆Ｂトレードご利用規約 第9条（登録解除）9.その他当社が利用者として不適切と判断した時」により、90日間お取引履歴がない会員様や、極端にお取引履歴が少ない会員様に対しまして、今後も継続してご利用の意思がないものとし、事前通知なしに会員登録解除を行い、IDを無効とさせていただくことがございます。再登録をご希望の場合は…基本的にお断りさせていただいております。",
    "https://www.ab.comolife.net/abtrade/html/"),
 ],
 # SUN-S(サンエス) は窓口の注記が無いので WINDOWS に載せない（＝A）。
 # 会社概要の「主要取引先…全国弊社製品取扱代理店」を渡したところ A1 の『代理店』に
 # 誤爆して A_PLUS になった。**取引先の列挙は問い合わせ窓口の注記ではない**ので、
 # 法務の注意②（抽出範囲を窓口の注記ブロックに限定）に従い除外した。
 # 代理店制を敷いている事実は備考に残してある。
 "トキワ商事": [
   ("お問い合わせ／取引案内",
    "おもちゃの卸全般ご相談下さい ≫トキワ商事は他社とどう違うの？≫仕入れ完了までの流れは？≫個人でも取引できるの？≫初めての取引の場合はどうするの？",
    "https://www.tokiwatoy.com/"),
 ],
 "タカラ産業": [
   ("会社概要", "事業内容 プラスチック成形品・金属加工品の製造から組立に至る一貫生産及び販売",
    "https://www.takaranet.co.jp/outline.html"),
 ],
 "レヂトン(Resiton)": [
   ("お問い合わせ",
    "各種製品、特注品製作依頼のお問い合わせ等ございましたら、下記フォームまでお気軽にお問い合わせください。",
    "https://www.resiton.co.jp/pages/5/"),
 ],
 "ハピラ(Hapila)": [
   ("会社概要", "事業内容 輸入文具・生活用品等の企画、卸販売、OEM", "https://www.hpl.co.jp/company/"),
 ],
 "KAYOTOYS カヨトイズ": [
   ("会社概要", "事業内容 玩具・雑貨の企画、生産、販売。OEM生産、売り場の企画・総合ご提案など",
    "https://kayo-trading.com/about/"),
 ],
 "タイガーゴム": [
   ("会社案内", "オリジナルの製品の開発、ご提供も可能です。", "https://www.tigergomu.com/company.html"),
 ],
 "山形工房(Yamagata Koubou)": [
   ("グローバルメニュー", "OEM", "https://www.kendama.co.jp/"),
 ],
 "曙産業": [
   ("企業概要・PR",
    "お客様の仕様に従った製品（ＯＥＭ製品）の開発設計も承っております。…既製品の少量から大量受注も承ります。",
    "https://webdb.tsjiba.or.jp/main/company/00001529/show"),
 ],
 "タカギ(Takagi)": [
   ("法人向け（B2B）窓口", "会社名 株式会社タカギ 電話番号 048-615-3551（受注センター） メールアドレス b2b@takagi.co.jp",
    "https://hi-business.takagi.co.jp/corporate.php"),
 ],
 "ウッディプッディ(Woodypuddy)": [
   ("法人のお客様",
    "法人サービスに関するご案内は、以下の項目からご覧いただけます。ご不明点はお気軽にお問合せ下さい。",
    "https://www.woodypuddy.com/company/corporate/"),
 ],
 "ピープル": [
   ("お問い合わせ",
    "こちらは、上記以外の当社に関するお問い合わせの専用窓口です。法人のお客様、企業や採用に関してお問い合わせのある方は、こちらからお願いいたします。",
    "https://www.people-kk.co.jp/contact/"),
 ],
 "日本のオラクルカード・タロットカード全集": [
   ("会社概要", "主な事業内容 ・カード出版制作事業・カード販売事業・カード文化の振興事業・カードの講座・セミナー事業・ライセンス管理事業・メディア・B2B支援事業",
    "http://company.visionary-c.com/ja/company/"),
 ],
 "モリドライブ(MORIDRIVE)": [
   ("会社情報", "また、企業様向けのご提案も行っております。", "https://rootsangyo.co.jp/company/"),
 ],
 "モリグリーン(Moly Green)": [
   ("企業情報", "私たちは自動車関連総合卸機能とメーカー機能を併せ持つ次世代のホールセラー・CAPスタイルです。",
    "https://www.cap-style.co.jp/"),
 ],
 "フィード": [
   ("Contact for Business Partners", "パートナー・リレーションデスク／Contact for Business Partners TEL：0120-004-504",
    "https://www.feedcorp.co.jp/"),
 ],
 "快適設計IBR": [
   ("コーポレートサイト", "レディースアパレル卸・企画・製造ならIBR", "https://ibr.ne.jp/"),
 ],
 "ストレッチングボード": [
   ("会社概要", "事業内容 3．各種家庭用雑貨・健康器具等、卸販売", "https://www.asahi-healthy.com/contents/company.htm"),
 ],
}


# 窓口ページを実際に見た、と言えるURLか。contact/inquiry/取引 系のみ。
WINDOW_URL_RE = re.compile(r"contact|inquiry|toiawase|otoiawase|form|torihiki|"
                           r"business|support|faq|shop|dealer|partner", re.I)


def _add(row, reason):
    """needs_review の理由を**上書きせず足す**。

    検知器は複数あり、1社に2つ当たることがある。上書きすると
    先に見つけた理由が消えて、人が読み返すときに片方しか見えない。
    """
    old = (row.get("optout_review_reason") or "").strip()
    return (old + " ／ " + reason).strip(" ／ ") if old else reason


def notice_status(row):
    """『お断り表示が無い』ことを**確認したのか、見ていないだけ**なのかを3値で返す。

    ★この列が無いと「打診可能338社」が過大評価される。
      社長はその数字を「お断り表示が無いことを確認した先」と読むが、
      実際に原文を取得したのは66社だけだった（法務ハルオの自己申告 2026-09-04）。

    ★判定の根拠は**窓口ページを見た記録があるか**の一点に置く。
      `optout_window_url` は「出典として引いたページ」であって
      「窓口を検分した記録」ではない。会社概要ページに
      お断り表示が無いのは当たり前で、表示は別ページにある。
      **したがって会社概要URLしか無い社は「未取得」に倒す。**
      推測で「表示なし」に倒さない。安全側は未取得（カズヨ指示 2026-09-04）。
    """
    if (row.get("form_optout_notice") or "").strip():
        return "注記あり"
    url = (row.get("optout_window_url") or "").strip()
    if "optout_window_text" in row and url and WINDOW_URL_RE.search(url):
        return "確認済み_表示なし"
    return "未取得"


def main():
    rows = [json.loads(l) for l in io.open(JL, encoding="utf-8") if l.strip()]
    ind = individual_decisions()
    counts = {}
    for r in rows:
        name = r.get("メーカー名", "")
        # エントリ自身が窓口テキストを持っていればそれを使う（新方式）。
        # 無ければ WINDOWS 表（初期100社ぶんの手書き）にフォールバックする。
        wins = WINDOWS.get(name)
        if not wins and r.get("optout_window_text") is not None and r.get("optout_window_url"):
            wins = [("窓口", r.get("optout_window_text", ""), r["optout_window_url"])]
        if wins:
            results = [classify_window(t, url) for (_, t, url) in wins]
            picked = pick_company_class(results)
            # ★証跡は**全窓口から**集める（2026-09-04 タカシ・v1.2 適用時に発見）。
            #
            #   法務 v1.2 は「勝たなかった**規則**の証跡を残せ」と要求している。
            #   ところが同じ取りこぼしが**窓口**の単位でも起きていた。
            #   pick_company_class() は「最も緩い窓口」を採るので、
            #   採られなかった窓口の証跡が丸ごと消える。
            #
            #   実例: 愛知電線は窓口が2つある。
            #     ・メールフォーム … 「迷惑メール相談センターに通報します」→ D1;D2;D3
            #     ・代表電話       … 記載なし → A
            #   緩い方（代表電話）が採られ、**通報の明示という最も重い証跡が
            #   optout_rule_ids から消えていた。** 判定は個社判定で D のままなので
            #   結論は正しいが、**なぜ除外したのかが分からない**状態だった。
            #
            #   クラスは一切変えない。証跡と needs_review を足すだけ。
            for one in results:
                if one is picked:
                    continue
                for rid in (one.get("optout_rule_ids") or "").split(";"):
                    if rid and rid not in picked["optout_other_rule_hits"]:
                        picked["optout_other_rule_hits"] = (
                            picked["optout_other_rule_hits"] + ";" + rid).strip(";")
                for rid in (one.get("optout_other_rule_hits") or "").split(";"):
                    if rid and rid not in picked["optout_other_rule_hits"]:
                        picked["optout_other_rule_hits"] = (
                            picked["optout_other_rule_hits"] + ";" + rid).strip(";")
                if one.get("optout_needs_review"):
                    picked["optout_needs_review"] = True
                    if one.get("optout_review_reason"):
                        picked["optout_review_reason"] = ((picked.get("optout_review_reason") or "")
                                                          + " ／ " + one["optout_review_reason"]).strip(" ／ ")
            texts = [t for (_, t, _u) in wins if t]
            r["form_optout_notice"] = " ／ ".join(texts)
        else:
            picked = classify_window("", r.get("公式HP", ""))
            r["form_optout_notice"] = ""
        r.update({k: picked[k] for k in
                  ("optout_class", "optout_hit_terms", "optout_rule_ids",
                   "contact_priority", "action", "optout_source_url", "recheck_condition",
                   "optout_e_subclass", "optout_other_rule_hits")})
        # v1.1 の engine が立てた needs_review を起点にする（後段の検知器が足す）
        r["optout_needs_review"] = "true" if picked.get("optout_needs_review") else ""
        r["optout_review_reason"] = picked.get("optout_review_reason", "")
        r["allowed_channels"] = json.dumps(picked["allowed_channels"], ensure_ascii=False)
        r["optout_checked_at"] = "2026-09-04"
        r["optout_notice_status"] = notice_status(r)

        # ★暫定の事業判断ブロック（WEB専売お断り／法人様以外／直販なし）は
        #   **v1.1 で撤去した。** 法務が E4_web_only_refused・E3_corporate_only を
        #   規則として入れ、ブリヂストン・Hikari・扶桑社・ハイメス・BUNDOK・
        #   SBクリエイティブを individual_decisions に載せたため、
        #   ここで同じ判定を二重に持つと**どちらが正か分からなくなる。**
        #   判定基準は法務ルールJSONに一本化する。
        notice = r.get("form_optout_notice", "")

        # ★法務ルールの語彙欠落を検知する。**JSONは触らず印だけ付けて法務へ返す。**
        # 例: パール金属「**アイデアのご提案**等につきましてはお断りさせて頂いております」は
        #     リッチェル（C）と同型だが、C1 の left に『アイデアのご提案』が無いため A になる。
        # 「提案/アイデア/売り込み」と「お断り/ご遠慮」が近接しているのに A/A_PLUS のままなら、
        # ルールの穴を疑って人に回す。**自分でルールを足さない。**
        import re as _re
        if r["optout_class"] in ("A", "A_PLUS") and notice:
            flat = _re.sub(r"\s+", "", notice)
            for lt in ("ご提案", "アイデア", "売り込み", "提案"):
                for m in _re.finditer(_re.escape(lt), flat):
                    for rt in ("お断り", "ご遠慮", "お受けしておりません"):
                        for rm in _re.finditer(_re.escape(rt), flat):
                            if abs(rm.start() - m.start()) <= 40:
                                r["optout_needs_review"] = "true"
                                r["optout_review_reason"] = _add(r, (
                                    "『%s』と『%s』が近接しているが自動判定は %s。"
                                    "リッチェル（C）と同型の可能性。法務ルールの語彙に"
                                    "この言い回しが無い疑い" % (lt, rt, r["optout_class"])))
        # ★★A1_trade_window の否定形での誤爆を検知する（2026-09-04 タカシ・第2走行で発見）。
        #
        # A1 は「新規お取引」「卸売」「代理店」等を**肯定の取引窓口シグナル**として拾うが、
        # 右辺（否定語）を持たない。そのため
        #   「新規お取引は**行っておりません**」→ A_PLUS（最優先で打診）
        # と、**意味が正反対に転ぶ**。実例:
        #   ブラザー・ジョルダン社「以下の業種、業態の企業・店舗様との新規お取引は行っておりません。
        #                          ・WEBでの販売のみの企業様」
        #   → 当社（Amazon専業）を名指しで除外しているのに A_PLUS になっていた。
        # 前任もキョーリン「海外代理店への販売のみ」で同型の誤爆を踏んでいる。
        #
        # **最優先で打診すべき社に化ける**方向の誤りなので、検知したら A_PLUS を維持しない。
        # ただしクラスを勝手に作らない。判定は下の事業判断（E）と needs_review に委ねる。
        if r["optout_class"] == "A_PLUS" and notice:
            neg = detect_negated_trade_window(notice, r.get("optout_hit_terms") or "")
            if neg:
                term, ng, excerpt = neg
                r["optout_needs_review"] = "true"
                r["optout_review_reason"] = _add(r, (
                    "A1_trade_window が『%s』でヒットしたが、直後に否定表現『%s』がある"
                    "（『%s』）。取引窓口の告知ではなく**取引しない旨の告知**の可能性が高い。"
                    "A1 は右辺（否定語）を持たないため意味が反転する。法務ルールの穴。"
                    % (term, ng, excerpt)))

        # 法務が個社を明示しているものは自動判定より優先
        # 法務の individual_decisions は法人名で書かれている。当社のメーカー名（ブランド名）と
        # 表記が違う社があるため別名表を挟む。**勝手な同一視をしないよう1件ずつ根拠を書く。**
        # ★別名表をここに持たない。v1.1 で aliases が法務ルール側に入ったので、
        #   individual_decisions() が別名も込みで引ける。
        #   同じ対応表を2箇所に持つと、片方だけ更新されて食い違う。
        d = (ind.get(name) or ind.get(name.split("(")[0])
             or ind.get(r.get("正式商号", "").split("（")[0].strip())
             or ind.get(r.get("正式商号", "")))
        if d:
            r["optout_class"] = d["class"]
            # ★すごろくやの再評価条件を修正（2026-09-04 カズヨ承認）。
            #   法務 v1.0 は「実店舗取得時」だが、原典に**モール出品禁止**の一文があるため
            #   実店舗を取っても Amazon では売れない。JSONは触らず適用側で上書きし、根拠を残す。
            if name == "すごろくや":
                d = dict(d)
                d["recheck_condition"] = ("販路をモール以外に持ったとき"
                                          "（実店舗取得だけでは不十分。原典に Amazon・楽天・Yahoo!・"
                                          "メルカリ等 大手ECモールへの出品をご遠慮いただく旨の記載があるため）")
            r["contact_priority"] = d["priority"]
            r["allowed_channels"] = json.dumps(d.get("channels", []), ensure_ascii=False)
            r["action"] = {"D": "exclude", "E": "exclude", "C": "hold",
                           "B": "contact_restricted"}.get(d["class"], "contact")
            if d.get("recheck_condition"):
                r["recheck_condition"] = d["recheck_condition"]
            if d.get("e_subclass"):
                r["optout_e_subclass"] = d["e_subclass"]
            r["optout_decided_by"] = d.get("decided_by", "")
            # ★事業判断（decision_type: business）はルール再走行で覆さない。
            #   ブリヂストン・Hikari は法務の表示判定では A だが、
            #   「直販しない相手にメーカー直取引を打診しても無益」という
            #   カズヨの事業判断で E に固定されている（2026-09-04 指示）。
            if d.get("decision_type") == "business":
                r["optout_rule_ids"] = (r.get("optout_rule_ids", "")
                                        + ";business_decision").strip(";")
            r["optout_rule_ids"] = (r.get("optout_rule_ids", "") + ";legal_individual_decision").strip(";")
            if d.get("note"):
                # ★冪等にする。このスクリプトは50社ごとに JSONL 全体へ何度も掛け直すので、
                #   無条件に追記すると同じ注記が回数ぶん積み上がる。
                #   （愛知電線の備考に「【法務の個社判定】通報明示。最優先で除外。」が
                #     7回並んでいた。2026-09-04 に検知して修正）
                tag = " ／ 【法務の個社判定】" + d["note"]
                base = r.get("備考", "")
                if tag.strip() not in base:
                    r["備考"] = (base + tag).strip()
        counts[r["optout_class"]] = counts.get(r["optout_class"], 0) + 1

    with io.open(JL, "w", encoding="utf-8") as fp:
        for r in rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("適用: %d社" % len(rows))
    for c in ("A_PLUS", "A", "B", "C", "D", "E"):
        if counts.get(c):
            print("  %-7s %d" % (c, counts[c]))
    print("\n--- D / E / C（打診対象から外す or 保留） ---")
    for r in rows:
        if r["optout_class"] in ("C", "D", "E"):
            print("  [%s] %-28s %s" % (r["optout_class"], r["メーカー名"][:28],
                                       (r.get("optout_hit_terms") or "個社判定")[:52]))


if __name__ == "__main__":
    main()
