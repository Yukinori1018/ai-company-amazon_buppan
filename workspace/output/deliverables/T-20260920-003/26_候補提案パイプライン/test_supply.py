#!/usr/bin/env python3
"""SD アダプタと仕入れ先商品リストのテスト。**ネットワークもシートも触りません。**

    python3 test_supply.py

HTML の断片は 2026-09-30 に実ページから取った形をそのまま縮めたものです
（SD品番 13681795 / ブライエンタープライズ）。**作り話の HTML でテストしても意味がない**ので、
構造は実物に合わせてあります。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import superdelivery as sd
import supplier_catalog as cat

PASS = FAIL = 0


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  ✗ {label}")


# ── 実ページの形をした断片 ─────────────────────────────────────────────────

PRODUCT_HTML = """
<div class="dl-info-area"><div class="dl-info-box"><div class="dl-name">
<a class="dl-name-txt" href="/p/do/dpsl/205398/">ブライエンタープライズ</a></div></div></div>
<table class="co-contents-box-table dl-trade-tbl">
<tr><th>消費者への直送</th><td class="co-tac"> × </td></tr>
<tr><th>仕入れ前の販売</th><td class="co-tac"> × </td></tr>
<tr><th>画像転載</th><td class="co-tac"> △<br>（購入した商品のみ転載可） </td></tr>
<tr><th>ネット販売</th><td class="co-tac"> ○ </td></tr>
</table>
<span class="co-pc-only">SD品番：13681795</span>
<tr class="ts-tr02">
  <td class="co-align-center border-rt border-b co-pc-only">S1</td>
  <td class="border-rt border-b td-set-detail"><div>くまのプーさん 珪藻土マット ナチュラルハッピー
    <div class="co-mt3 co-pc-only">（mrs-2215051000）</div>
    <div class="co-fcgray td-jan">JAN：4992272443363</div></div></td>
  <td class="border-rt co-align-center co-pc-only"><span>2点</span></td>
  <td class="border-rt maker-product-price"><div class="float-left">メーカー希望小売価格（税抜）</div>
    <div class="float-right">&yen;1,000 / 1点<br /><span>1セット (2点)</span></div></td>
  <td class="stock-info co-align-center border-t"><span>卸価格は</span>会員のみ公開</td>
  <td class="tr-last co-ts-only"><table><tr><td><span>SD品番：13681795S1</span>
    <span> / メーカー品番：mrs-2215051000</span></td></tr></table></td>
</tr>
<tr class="ts-tr02">
  <td>S2</td>
  <td class="border-rt border-b td-set-detail"><div>くまのプーさん 珪藻土マット ナチュラルハッピー
    <div>（mrs-2215051000）</div><div class="td-jan">JAN：4992272443363</div></div></td>
  <td><span>3点</span></td>
  <td class="maker-product-price"><div>メーカー希望小売価格（税抜）</div>
    <div>&yen;1,000 / 1点<br /><span>1セット (3点)</span></div></td>
  <td class="stock-info">SOLD OUT <span>卸価格は</span>会員のみ公開</td>
  <td><table><tr><td><span>SD品番：13681795S2</span>
    <span> / メーカー品番：mrs-2215051000</span></td></tr></table></td>
</tr>
"""

# ログイン済みの形（卸価格が金額で出る）。承認済みの行はこう見える。
LOGGED_IN_HTML = PRODUCT_HTML.replace(
    '<td class="stock-info co-align-center border-t"><span>卸価格は</span>会員のみ公開</td>',
    '<td class="stock-info co-align-center border-t">&yen;620 / 1点</td>')

SEARCH_HTML = """
<a href="/p/do/dpsl/205398/">ブライエンタープライズ</a>
<a href="/p/do/dpsl/205398/">ブライエンタープライズ（すべてのジャンル）</a>
<a href="/p/do/dpsl/57703/">ネオウィング ライフスタイル事業部（1号店）</a>
1 ～ 2社 （全2社）
<a href="/p/r/pd_p/13681795/">x</a><a href="/p/r/pd_p/13681817/">y</a>
<a href="/p/r/pd_p/13681795/">dup</a>
"""

EMPTY_HTML = "<p>ご指定の検索条件に該当する商品は ございませんでした。</p>"


def test_parse_product():
    rows = sd.parse_product(PRODUCT_HTML, "https://example/p/r/pd_p/13681795/")
    ok(len(rows) == 2, "規格2行になる（S1/S2）")
    a, b = rows
    ok(a.sd_code == "13681795S1", "SD品番（枝番つき）")
    ok(a.jan == "4992272443363", "JAN を読む")
    ok(a.maker_code == "mrs-2215051000", "メーカー品番を読む")
    ok(a.units_per_set == 2 and b.units_per_set == 3, "入り数は口ごとに違う")
    ok(a.retail_excl == 1000, "上代（税抜）")
    ok(a.name == "くまのプーさん 珪藻土マット ナチュラルハッピー", "商品名は品番の括弧より前")
    ok(a.supplier and a.supplier.name == "ブライエンタープライズ", "出展企業名")
    ok(a.supplier.supplier_id == "205398", "出展企業ID")
    ok(a.net_sales_ok == "○", "ネット販売可否を販売規制から読む")
    ok(a.direct_ship_ok == "×", "消費者直送可否を販売規制から読む")
    # ここが一番大事: **非ログインの「会員のみ公開」を 0 や「無し」に畳まない**
    ok(a.wholesale_price_excl is None, "非ログインの卸価格は None（0 に畳まない）")
    ok(a.approval == "未確認", "非ログインでは承認の有無が判らない＝未確認")
    ok(b.stock == "在庫なし", "SOLD OUT を在庫なしとして読む")
    ok(a.stock == "未確認", "在庫の記載が無ければ未確認（在庫ありと決めない）")


def test_parse_product_logged_in():
    rows = sd.parse_product(LOGGED_IN_HTML, logged_in=True)
    ok(rows[0].wholesale_price_excl == 620, "ログイン済みの HTML なら金額を読む")
    ok(rows[0].approval == "承認済み", "金額が読めた行は承認済み")
    ok(rows[1].approval == "卸価格未承認",
       "ログイン済みで金額が無い行だけを未承認と書く")


def test_sold_out_is_not_unapproved():
    """🔴 品切れ（SOLD OUT）を「卸価格未承認」と読まない。

    品切れの行は卸価格の欄に SOLD OUT が入り、「会員のみ公開」が出ません。
    以前はそれを未承認として書き、非ログインの10件が未承認に化けていました（2026-09-30 実測）。
    """
    html = PRODUCT_HTML.replace(
        '<td class="stock-info co-align-center border-t"><span>卸価格は</span>会員のみ公開</td>',
        '<td class="stock-info co-align-center border-t">SOLD OUT</td>')
    rows = sd.parse_product(html)                    # logged_in=False（既定）
    ok(rows[0].approval == "未確認", "非ログインの品切れは未確認（未承認と書かない）")
    ok(rows[0].stock == "在庫なし", "品切れは在庫なしとして記録する")
    ok(rows[0].wholesale_price_excl is None, "金額は作らない")


def test_parse_search():
    sups, pids, total = sd.parse_search(SEARCH_HTML)
    ok(total == 2, "「全2社」を社数として読む")
    ok(len(sups) == 2, "企業は重複とジャンルリンクを除いて2社")
    ok(sups[0].name == "ブライエンタープライズ", "企業名")
    ok(pids == ["13681795", "13681817"], "商品IDは重複を畳んで順番を保つ")
    sups, pids, total = sd.parse_search(EMPTY_HTML)
    ok((sups, pids, total) == ([], [], 0), "0件ページは (0,0,0)")


def test_lookup_plan():
    plan = sd.lookup_plan(jan="4992272443363", maker_code="mrs-2215051000",
                          brand="mrs", title="【バス用品】くまのプーさん 珪藻土マット 600×450mm")
    ok(plan[0] == "mrs-2215051000", "型番がいちばん先（当たりやすい）")
    ok(all("4992272443363" not in p for p in plan),
       "🔴 JAN は投げない（SD は JAN で検索できないと実測済み）")
    ok(any("くまのプーさん" in p for p in plan), "商品名のキーワードが入る")
    ok(all("600×450mm" not in p for p in plan), "サイズはキーワードにしない")
    ok(len(plan) == len(set(plan)), "同じ語を2回投げない")
    ok(sd.lookup_plan() == [], "手がかりが無ければ空（当てずっぽうを投げない）")


def test_fetcher_cap_raises():
    f = sd.Fetcher(cap=0)
    try:
        f("https://example.invalid/")
        ok(False, "上限0で例外になる")
    except sd.Fetcher.CapReached:
        ok(True, "上限に当たったら例外（黙って0件を返さない）")


def test_rate_limit_is_a_hard_stop():
    """🔴 429 は1件の失敗ではなく、全体を止める理由。

    2026-09-30、SD が本当に 429 を返した。最初の実装はこれを1件ずつの失敗として飲み込み、
    「JAN 付き0件」という**無害そうな結果**を返していた（原因は trace の中だけ）。
    「SD に無かった」と「こちらが止められた」を混ぜてはいけない。
    """
    ok(issubclass(sd.Fetcher.RateLimited, RuntimeError), "専用の例外型がある")
    ok(sd.Fetcher.RateLimited is not sd.Fetcher.CapReached,
       "上限到達とレート制限は別物（意味が違う）")

    # 検索ループ: 429 で即止まり、理由が trace に残る
    rows, trace = sd.index_by_words(["a", "b", "c"], fetch=_raise_429,
                                    log=lambda *a: None)
    ok(rows == [], "行は返らない")
    ok("レート制限" in (trace.get("stopped") or ""), "止まった理由が レート制限 と残る")
    ok(len(trace["words"]) == 0, "1語ずつ失敗として積まない（全体を止める）")

    # 企業ループでも同じ
    rows, trace = sd.index_by_dealer(["1", "2"], fetch=_raise_429, log=lambda *a: None)
    ok("レート制限" in (trace.get("stopped") or ""), "企業ループでも全体を止める")
    ok(len(trace["dealers"]) == 0, "企業ごとの error として飲み込まない")

    # 突合ループでも同じ
    hits, trace = sd.find_by_identity(jan="4992272443363", maker_code="x",
                                      fetch=_raise_429, log=lambda *a: None)
    ok(hits == [], "突合でも行は返らない")
    ok("レート制限" in (trace.get("stopped") or ""), "突合ループでも理由が残る")


def _raise_429(url):
    raise sd.Fetcher.RateLimited("SD が HTTP 429 を返しました（テスト）")


def test_report_stop_exit_code():
    """レート制限のときは終了コードで知らせる（0件と区別できるように）。"""
    import sd_lookup
    ok(sd_lookup.report_stop({}) == 0, "打ち切りが無ければ 0")
    ok(sd_lookup.report_stop({"stopped": "取得上限"}) == 0, "上限は 0（異常ではない）")
    ok(sd_lookup.report_stop({"stopped": "SD のレート制限: 429"}) == 2,
       "レート制限は 2（呼び出し側が気づける）")


def test_find_by_identity_confirms_by_jan():
    """検索が当たっても、**JAN が違えば一致にしない**。"""
    pages = {sd.search_url("mrs-2215051000"): SEARCH_HTML,
             sd.product_url("13681795"): PRODUCT_HTML,
             sd.product_url("13681817"): PRODUCT_HTML}
    calls = []

    def fake(url):
        calls.append(url)
        return pages.get(url, EMPTY_HTML)

    hits, trace = sd.find_by_identity(jan="4992272443363", maker_code="mrs-2215051000",
                                      fetch=fake, log=lambda *a: None)
    ok(len(hits) == 2 and hits[0].jan == "4992272443363", "JAN 一致で2規格が返る")
    ok(len(calls) == 2, "一致した時点で止める（無駄に開かない）")

    hits, trace = sd.find_by_identity(jan="9999999999999", maker_code="mrs-2215051000",
                                      fetch=fake, log=lambda *a: None)
    ok(hits == [], "JAN が違えば一致にしない")
    ok(len(trace["near"]) > 0, "近いもの（同じ企業の別品番）は near に残す")


def test_find_by_identity_skips_broad_queries():
    """広すぎる検索から商品ページを開かない。**先頭4枚は当てずっぽう**なので。"""
    broad = SEARCH_HTML.replace("（全2社）", "（全25社）")
    calls = []

    def fake(url):
        calls.append(url)
        return broad if "psl" in url else PRODUCT_HTML

    hits, trace = sd.find_by_identity(jan="4992272443363", maker_code="mrs-2215051000",
                                      fetch=fake, log=lambda *a: None)
    ok(hits == [], "広い検索では一致を名乗らない")
    ok(all("pd_p" not in u for u in calls), "商品ページを1枚も開かない")
    ok(any(q.get("skipped") for q in trace["queries"]), "飛ばした理由を記録する")


def test_merge_wholesale():
    rows = sd.parse_product(PRODUCT_HTML)
    # 🔴 2026-10-01 から `価格の単位` が必須です（同じ JAN に「1点」「×10点」の口が並び、
    #    画面の建て付けが口ごとに違うため）。単位が無い行は取り込みません。
    sd.merge_wholesale(rows, {"13681795S1": {"卸価格": 620, "価格の単位": "1点あたり",
                                             "在庫": "在庫あり"},
                              "13681795S2": {"承認状態": "卸価格未承認"}})
    ok(rows[0].wholesale_price_excl == 620, "人が見た卸価格が入る")
    ok(rows[0].approval == "承認済み", "金額が入れば承認済み")
    no_basis = sd.parse_product(PRODUCT_HTML)
    sd.merge_wholesale(no_basis, {"13681795S1": {"卸価格": 620}})
    ok(no_basis[0].wholesale_price_excl is None,
       "`価格の単位` が無い行は卸価格を取り込まない（推測しない）")
    ok(any("価格の単位" in n for n in no_basis[0].notes), "取り込まなかった理由を残す")
    ok(rows[0].stock == "在庫あり", "在庫も人の値で埋まる")
    ok(rows[1].wholesale_price_excl is None, "未承認の行に金額を作らない")
    ok(rows[1].approval == "卸価格未承認", "未承認は未承認として残す（NO-GO ではない）")


def test_approval_requests_does_not_apply():
    rows = sd.parse_product(PRODUCT_HTML)
    reqs = sd.approval_requests(rows)
    ok(len(reqs) == 1, "企業ごとに1件へ畳む")
    ok(reqs[0]["出展企業"] == "ブライエンタープライズ", "企業名が入る")
    ok(reqs[0]["該当商品数"] == 2, "該当商品数を数える")
    ok("申請したい理由" in reqs[0], "なぜ申請したいかが付く")
    ok("突合はまだ取れていない" in reqs[0]["申請したい理由"],
       "🔴 突合していないのに『Amazon で一致』と書かない（優先順位を読み違えるので）")
    ok(reqs[0]["Amazon突合済み"] == 0, "突合0件を0件と書く")
    with_asin = sd.approval_requests(rows, asin_by_jan={"4992272443363": "B0TEST0001"})
    ok(with_asin[0]["Amazon突合済み"] == 2, "突合できていれば数える")
    ok("実売のある棚" in with_asin[0]["申請したい理由"], "突合できた企業は理由が変わる")
    ok(len(reqs[0]["JAN例"]) == 1, "同じ JAN を JAN例に2回入れない")
    # 承認済みの行は申請対象にしない
    sd.merge_wholesale(rows, {"13681795S1": {"卸価格": 620, "価格の単位": "1点あたり"},
                              "13681795S2": {"卸価格": 600, "価格の単位": "1点あたり"}})
    ok(sd.approval_requests(rows) == [], "承認済みだけなら申請対象は0件")


# ── 仕入れ先商品リスト側 ──────────────────────────────────────────────────


def test_columns_fixed():
    ok(len(cat.COLUMNS) == 17, "17列固定")
    ok(cat.COLUMNS[0] == "登録日" and cat.COLUMNS[-1] == "備考", "先頭と末尾")
    ok(cat.COLUMNS[cat.I_JAN] == "JAN", "JAN 列の位置が合っている")
    ok(cat.COLUMNS[cat.I_SOURCE] == "仕入れ先", "仕入れ先 列の位置が合っている")


def test_row_has_no_blanks():
    cells = cat.Row(source="SD", jan="4992272443363").to_cells(today="2026-09-30")
    ok(len(cells) == 17, "セル数は17")
    ok(all(c != "" for c in cells[:-1]), "備考以外に空欄を作らない（§3.2）")
    ok(cells[cat.COLUMNS.index("卸価格(1点・税込)")] == "未確認",
       "卸価格が無ければ 0 ではなく「未確認」")
    ok(cells[cat.I_HAS_ASIN] == "未確認", "ASIN 不明は「なし」ではなく「未確認」")


def test_from_sd_sets():
    rows = cat.from_sd_sets(sd.parse_product(PRODUCT_HTML),
                            asin_by_jan={"4992272443363": "B0TEST0001"})
    ok(len(rows) == 2, "規格ごとに1行")
    ok(rows[0].source == "SD", "仕入れ先は SD")
    ok(rows[0].asin == "B0TEST0001", "突合できた ASIN が入る")
    ok(rows[0].wholesale_incl is None, "非ログインなら卸価格は None のまま")
    ok(any("上代" in n for n in rows[0].notes), "上代は備考に残す")


def test_from_netsea_index_tax_and_fields():
    idx = {"4901234567890": {"unit_price_excl": 1000, "min_lot_units": 6,
                             "stock": "在庫あり", "title": "テスト商品",
                             "tax_class": 0, "supplier_name": "テスト商事",
                             "supplier_url": "https://example/x", "shop_id": 6804}}
    rows = cat.from_netsea_index(idx)
    ok(len(rows) == 1 and rows[0].source == "NETSEA", "NETSEA 行になる")
    ok(rows[0].wholesale_incl == 1100, "税抜1,000 → 税込1,100")
    ok(rows[0].units_per_set == 1, "NETSEA の price は1点の値段なので入り数1")
    ok(rows[0].min_lot == 6, "set_num は最小ロット（入り数と別概念）")
    ok(rows[0].net_sales_ok == "○", "索引に入る条件がネット販売可")
    ok(rows[0].direct_ship_ok == "未確認", "API に無い項目を推測で埋めない")
    ok(rows[0].approval == cat.APPROVAL_OK, "承認済みサプライヤーしか API に出ない")
    idx["4901234567890"]["tax_class"] = 1
    ok(any("税区分" in n for n in cat.from_netsea_index(idx)[0].notes),
       "軽減税率の疑いは備考に残す（1.08 と推測しない）")


def test_jan_stays_text():
    """🔴 JAN は数字の並びであって数ではない。**先頭の0を落とさない。**

    2026-09-30、シートに `USER_ENTERED` で書いたら 088381753180 が 88381753180 になり、
    冪等の鍵が一致せず**同じ商品を二重登録しました**（59件が桁落ち・12組が重複）。
    列の TEXT 指定はシート側（`ensure_header`）で、ここでは値が文字列で通ることを見ます。
    """
    cells = cat.Row(source="NETSEA", jan="0088381753180").to_cells(today="2026-09-30")
    j = cells[cat.I_JAN]
    ok(isinstance(j, str) and j == "0088381753180", "先頭の0が残る")
    a = cat.Row(source="NETSEA", jan="0088381753180")
    b = cat.Row(source="NETSEA", jan="88381753180")
    ok(a.key != b.key, "桁落ちした JAN は別の鍵になる（＝重複として通さない）")


def test_dedupe_keeps_smallest_set():
    a = cat.Row(source="SD", jan="4900000000001", units_per_set=3, code="X3")
    b = cat.Row(source="SD", jan="4900000000001", units_per_set=2, code="X2")
    c = cat.Row(source="NETSEA", jan="4900000000001", units_per_set=1)
    out = cat.dedupe([a, b, c])
    ok(len(out) == 2, "仕入れ先が違えば別行（同じ JAN でも残す）")
    sd_row = [r for r in out if r.source == "SD"][0]
    ok(sd_row.code == "X2", "同じ仕入れ先なら入り数の小さい口を残す")
    ok(any("1セット3点" in n for n in sd_row.notes), "落とした口は備考に書く（黙って捨てない）")
    ok(cat.dedupe([cat.Row(source="SD", jan="")]) == [], "JAN が無い行は積まない")


def test_append_uses_raw_not_user_entered():
    """🔴 書き込みは RAW。`USER_ENTERED` は JAN の先頭0を落とす。

    列を TEXT 形式にするだけでは足りない（追記した行に効かない）ことを実測したので、
    **呼び出し方そのもの**をテストで固定する。
    """
    import inspect
    # コメントは落とす（なぜ RAW なのかの説明に USER_ENTERED が出てくるので）
    code = "\n".join(line.split("#")[0] for line in
                     inspect.getsource(cat.append).splitlines())
    ok('value_input_option="RAW"' in code, "append は RAW で書く")
    ok("USER_ENTERED" not in code, "append のコードに USER_ENTERED が残っていない")


def test_mark_already_trading():
    """既に取引中の企業を申請リストに混ぜない。**リストが無いことを根拠にしない。**"""
    import sd_lookup
    tsv = Path(__file__).resolve().parent / "_test_trading.tsv"
    tsv.write_text("dealer_id\tname\n205398\t株式会社ブライエンタープライズ\n"
                   "999999\tよその会社\n", encoding="utf-8")
    try:
        reqs = [{"出展企業": "ブライエンタープライズ", "supplier_id": "205398",
                 "該当商品数": 2, "申請したい理由": "x"},
                {"出展企業": "知らない商店", "supplier_id": "111111",
                 "該当商品数": 1, "申請したい理由": "y"}]
        out = sd_lookup.mark_already_trading(list(reqs), tsv=tsv)
        ok(out[0]["既に取引中"] is True, "出展企業ID で一致すれば取引中")
        ok("申請は不要" in out[0]["申請したい理由"], "取引中なら理由が書き換わる")
        ok(out[1]["既に取引中"] is False, "リストに無ければ申請が要る")
        # 社名の名寄せ（法人格を落として当てる）
        out = sd_lookup.mark_already_trading(
            [{"出展企業": "株式会社ブライエンタープライズ", "supplier_id": "000",
              "該当商品数": 1, "申請したい理由": "x"}], tsv=tsv)
        ok(out[0]["既に取引中"] is True, "ID が違っても社名の名寄せで当たる")
        # リストが無いときは「取引していない」と決めない
        out = sd_lookup.mark_already_trading(list(reqs), tsv=tsv.with_name("_nope.tsv"))
        ok("既に取引中" not in out[0], "リストが無ければ取引の有無を名乗らない")
        ok("未確認" in out[0]["取引中の判定"], "判定不能と書く")
    finally:
        tsv.unlink(missing_ok=True)


# ── Product Finder の抽出条件（SD 向け）──────────────────────────────────


def test_sd_friendly_categories():
    """SD が強いカテゴリに絞る。**生存の条件は緩めない。**"""
    import product_finder as pf
    sel = pf.sd_friendly_shelves(per_page=50)
    ok(sel["categories_include"] == pf.SD_FRIENDLY_ROOT_CATEGORIES, "include が入る")
    ok(3828871 in sel["categories_include"], "ホーム＆キッチンが入る（SD の本体）")
    ok(sel["monthlySold_gte"] == 50, "🔴 生存（実売）の条件は緩めない（§3.3-8）")
    ok("current_SALES_lte" in sel, "ランク上限も残る")
    # 避けるカテゴリを include と exclude の両方に入れない（矛盾する条件を投げない）
    ok(not (set(sel["categories_include"]) & set(sel["categories_exclude"])),
       "include と exclude が重ならない")
    for cid in (57239051, 160384011, 52374051, 465392):
        ok(cid not in sel["categories_include"],
           f"期限管理・薬機法が絡むカテゴリ {cid} を include に入れない")


def test_exclude_ids_match_real_data():
    """除外IDが実データのルートと一致していること（推測で書いた3件を直した回帰テスト）。

    以前は 562002（ミュージック）・637630（テレビゲーム）・161669011（ビューティー）と
    書いてあり、**手元の1,424商品のどれにも出てこない ID** でした。
    誤った ID を渡してもエラーにならないので、除外できていないことに気づけません。
    """
    import product_finder as pf
    for wrong in (562002, 637630, 161669011):
        ok(wrong not in pf.EXCLUDE_ROOT_CATEGORIES,
           f"実データに無い ID {wrong} を使っていない")
    for right in (561956, 637394, 52374051):
        ok(right in pf.EXCLUDE_ROOT_CATEGORIES, f"実データ由来の ID {right} を使っている")


def test_unproven_fields_flags_silently_ignored():
    """プローブしていないフィールドを挙げる。**Finder は未知の項目を黙って無視する。**"""
    import product_finder as pf
    log = Path(__file__).resolve().parent / "_test_probes.json"
    log.write_text('{"monthlySold_gte": {"effective": true},'
                   ' "bogusField": {"effective": false}}', encoding="utf-8")
    try:
        sel = {"productType": [0], "perPage": 50, "monthlySold_gte": 50,
               "bogusField": 1, "categories_include": [1]}
        bad = pf.unproven_fields(sel, log)
        ok("monthlySold_gte" not in bad, "有効だと確かめた項目は挙げない")
        ok("bogusField" in bad, "無効だと分かっている項目を挙げる（黙って通さない）")
        ok("categories_include" in bad, "未確認の項目を挙げる")
        ok("perPage" not in bad and "productType" not in bad,
           "絞り込みでない項目は対象外")
    finally:
        log.unlink(missing_ok=True)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
