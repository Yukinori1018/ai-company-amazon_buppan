"""scan_v14 のハーネス（ラウンドロビン・自動停止・再開）を **API を叩かずに** 検証する。

実行: このディレクトリで `python3 -m pytest test_scan_v14_loop.py -q`

Keepa を偽物に差し替えて、実トークンを1つも使わずに次の性質を固定する。
無人で12時間走らせるコードなので、**止まるべき時に止まること**が最重要の仕様。

1. シャードをラウンドロビンで回る（1帯に偏らない）
2. STOP ファイルで止まる
3. `--max-hours` で止まる
4. 新規ゼロが3ラウンド続いたら止まる
5. 再開時に取得済み ASIN を二度取りしない
6. CSV は取得のたびに追記され、途中で止めても行が残る
7. **API の障害を「掘り切った」と記録しない**（T-20260831-002 / M2。最重要）
8. ネットワークが死んでも無限に待たない（M7）
"""
import json
import types

import pytest


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """scan_v14 を読み込み、出力先を tmp に、Keepa を偽物に差し替えた状態を返す。"""
    import scan_v14 as s

    out = tmp_path / "v14"
    for name, sub in [("OUT", ""), ("RAW", "raw"), ("RAW_OFFERS", "raw_offers")]:
        p = out / sub if sub else out
        p.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(s, name, p)
    monkeypatch.setattr(s, "CSV_ALL", out / "all.csv")
    monkeypatch.setattr(s, "CSV_GO", out / "go.csv")
    monkeypatch.setattr(s, "CSV_MAKER", out / "makers.csv")
    monkeypatch.setattr(s, "PROGRESS", out / "progress.json")
    monkeypatch.setattr(s, "SEEN", out / "seen.txt")
    monkeypatch.setattr(s, "LOG", out / "scan.log")
    monkeypatch.setattr(s, "STOP_FILE", out / "STOP")
    monkeypatch.setattr(s, "CURSORS", out / "cursors.json")
    monkeypatch.setattr(s, "ALERT_FILE", out / "ALERT.md")
    monkeypatch.setattr(s, "HEARTBEAT", out / "heartbeat.json")
    # API の健康状態はモジュール全体で1つなので、テストごとに必ず作り直す。
    monkeypatch.setattr(s, "API", s.ApiHealth())
    monkeypatch.setattr(s, "token_status", lambda: {"tokensLeft": 9999, "refillRate": 20})
    monkeypatch.setattr(s.time, "sleep", lambda *_: None)

    calls = {"finder": 0, "detail": 0, "offers": 0, "bands": []}

    def fake_product(asin, seller_ids=("S1", "S2")):
        """最低限「候補」に通る商品。価格1800円・ドロップ30・実セラー2社。"""
        cur = [-1] * 20
        cur[1] = 1800          # NEW
        cur[3] = 5000          # ランク
        cur[11] = 2            # COUNT_NEW
        csv_series = [None] * 20
        csv_series[1] = [s.PRICE_DEF_CHANGE_KEEPA_MIN + 100, 1800]
        return {
            "asin": asin, "title": f"商品 {asin}", "brand": f"メーカー{asin[-1]}",
            "manufacturer": "", "availabilityAmazon": -1,
            "categoryTree": [{"catId": 1, "name": "ホーム＆キッチン"}],
            "packageWeight": 500, "packageLength": 200,
            "packageWidth": 150, "packageHeight": 100,
            "csv": csv_series,
            "stats": {"current": cur, "salesRankDrops30": 30, "minInInterval": []},
            "offers": [{"sellerId": sid, "condition": 1, "isFBA": True} for sid in seller_ids],
            "liveOffersOrder": list(range(len(seller_ids))),
        }

    def fake_keepa_get(path, params, budget, label):
        if path == "query":
            calls["finder"] += 1
            calls["bands"].append(label)
            sel = json.loads(params["selection"])
            page = sel["page"]
            if page > 0:                       # 1ページで掘り切る（テストを短くするため）
                return {"asinList": [], "totalResults": 100}
            lo = sel["current_NEW_gte"]
            return {"asinList": [f"B{lo:06d}{i:03d}" for i in range(5)], "totalResults": 5}
        if "offers" in params:
            calls["offers"] += 1
            return {"products": [fake_product(a) for a in params["asin"].split(",")]}
        if path == "seller":
            return {"sellers": {sid: {"sellerName": f"店舗{sid}"}
                                for sid in params["seller"].split(",")}}
        calls["detail"] += 1
        return {"products": [fake_product(a) for a in params["asin"].split(",")]}

    monkeypatch.setattr(s, "keepa_get", fake_keepa_get)
    monkeypatch.setattr(s, "DETAIL_CHUNK", 5)
    return types.SimpleNamespace(s=s, out=out, calls=calls)


def _args(**over):
    base = dict(max_hours=1.0, pilot=0, resume=False, rebuild=False, skip_bands="")
    base.update(over)
    return types.SimpleNamespace(**base)


def test_round_robin_visits_every_shard_before_repeating(sandbox):
    """1帯を掘り切ってから次へ、ではなく **全25帯を1巡してから**2巡目に入る。"""
    s = sandbox.s
    s.run(_args())
    first_round = sandbox.calls["bands"][:25]
    assert len(set(first_round)) == 25, "1巡目で同じシャードを2回引いている"


def test_stop_file_halts_the_run(sandbox):
    s = sandbox.s
    (sandbox.out / "STOP").write_text("")
    s.run(_args())
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert "STOP" in prog["stop_reason"]
    # STOP は勝手に消さない（「止めたい」意思を次回起動で握りつぶさないため）
    assert (sandbox.out / "STOP").exists()
    assert prog["counts"]["processed"] == 0


def test_max_hours_halts_the_run(sandbox):
    """正の値を渡したら、その時間で止まる。"""
    s = sandbox.s
    s.run(_args(max_hours=1e-9))
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert "時間に達しました" in prog["stop_reason"]


def test_max_hours_zero_means_no_time_limit(sandbox):
    """--max-hours 0 は「時間では止めない」。常時稼働（always_on.py）の前提。

    時間で止まらないので、止まる理由は掘り切り側になる。
    """
    s = sandbox.s
    s.run(_args(max_hours=0))
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert "時間に達しました" not in (prog["stop_reason"] or "")
    assert prog["auto_stop"]["max_hours"] == 0


def test_skip_bands_are_not_visited(sandbox):
    """掘り切り済みとして渡した帯は Finder を1回も叩かない（トークンを払わない）。"""
    s = sandbox.s
    skipped = [b[4] for b in s.shards()][:5]
    s.run(_args(skip_bands=",".join(skipped)))
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    # 飛ばした帯は最終 progress の exhausted に必ず入っている（周回管理が読む）
    assert set(skipped) <= set(prog["cursor"]["exhausted"])


def test_skipping_every_band_stops_immediately_without_tokens(sandbox):
    """全帯が掘り切り済みなら、Finder を1回も叩かずに即終了する（＝一周完了の合図）。"""
    s = sandbox.s
    s.run(_args(skip_bands=",".join(b[4] for b in s.shards())))
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert "掘り切りました" in prog["stop_reason"]
    assert sandbox.calls["finder"] == 0


def test_exhausting_all_shards_halts_the_run(sandbox):
    """偽 Finder は1ページで尽きるので、全シャードを掘り切って自然停止する。"""
    s = sandbox.s
    s.run(_args())
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert prog["stop_reason"] == "全シャードを掘り切りました"
    assert prog["counts"]["processed"] == 25 * 5      # 25シャード × 5件
    assert prog["counts"]["go"] == 25 * 5             # 全部が候補に通る作りにしてある


def test_resume_does_not_refetch_known_asins(sandbox):
    """2回走らせても、詳細取得の呼び出しは増えない（同じ ASIN に二度払わない）。"""
    s = sandbox.s
    s.run(_args())
    first = sandbox.calls["detail"]
    sandbox.calls["detail"] = 0
    s.run(_args())
    assert sandbox.calls["detail"] == 0, "取得済み ASIN を取り直している"
    assert first == 25


def test_csv_rows_survive_an_interrupted_run(sandbox):
    """途中で止めても、それまでの行は CSV に残っている（追記設計の担保）。"""
    import csv as _csv
    s = sandbox.s
    s.run(_args(pilot=10))
    rows = list(_csv.DictReader(open(sandbox.out / "go.csv", encoding="utf-8-sig")))
    assert len(rows) >= 10
    assert all(r["ASIN"] and r["メーカー/ブランド"] and r["想定仕入れ金額(上限)"] for r in rows)


def test_maker_csv_is_aggregated_by_maker(sandbox):
    import csv as _csv
    s = sandbox.s
    s.run(_args())
    makers = list(_csv.DictReader(open(sandbox.out / "makers.csv", encoding="utf-8-sig")))
    assert makers, "メーカー名寄せが空"
    total = sum(int(m["該当商品数"]) for m in makers)
    assert total == 25 * 5
    assert all(m["代表ASIN"] and m["メーカー検索(Google)"] for m in makers)


def test_seller_gate_rejects_single_seller_products(sandbox, monkeypatch):
    """実セラー1社（＝メーカー独占）は候補に入れない。これが唯一の必須ゲート。"""
    s = sandbox.s
    orig = s.keepa_get

    def one_seller(path, params, budget, label):
        payload = orig(path, params, budget, label)
        if "offers" in params:
            for p in payload["products"]:
                # 同一セラーが FBA と FBM の2本 → COUNT_NEW は2だが実セラーは1社
                p["offers"] = [{"sellerId": "SOLO", "condition": 1, "isFBA": True},
                               {"sellerId": "SOLO", "condition": 1, "isFBA": False}]
                p["liveOffersOrder"] = [0, 1]
        return payload

    monkeypatch.setattr(s, "keepa_get", one_seller)
    s.run(_args())
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert prog["counts"]["go"] == 0
    assert prog["counts"]["rejected_seller"] == 25 * 5


def test_interrupted_page_is_resumed_not_skipped(sandbox, monkeypatch):
    """1ページ(1000件)を食べ切る前に落ちても、残りは次回ちゃんと拾える。

    ページカーソルを取得直後に進めてしまうと、途中で止めた回の残りが
    **二度と拾えないまま**次ページへ飛ぶ。母数を取り続ける設計の急所なので固定する。
    """
    s = sandbox.s
    # 1ページ=10件、1回のバッチ=3件 → 1回の訪問ではページを食べ切れない
    monkeypatch.setattr(s, "DETAIL_CHUNK", 3)
    orig = s.keepa_get

    def ten_per_page(path, params, budget, label):
        if path == "query":
            payload = orig(path, params, budget, label)
            if payload["asinList"]:
                lo = json.loads(params["selection"])["current_NEW_gte"]
                payload["asinList"] = [f"B{lo:06d}{i:03d}" for i in range(10)]
            return payload
        return orig(path, params, budget, label)

    monkeypatch.setattr(s, "keepa_get", ten_per_page)

    s.run(_args(pilot=3))                        # 1シャードで3件だけ処理して中断
    cursors = json.loads((sandbox.out / "cursors.json").read_text(encoding="utf-8"))
    assert cursors.get("1500-1999円", 0) == 0, "食べ切る前にページを進めている"

    s.run(_args(pilot=3))                        # 再開: 同じページの残りを拾う
    seen = (sandbox.out / "seen.txt").read_text(encoding="utf-8").split()
    first_page = {f"B001500{i:03d}" for i in range(10)}
    assert len(set(seen) & first_page) == 6, "再開後に同じページの続きを拾えていない"


# ==========================================================================
# T-20260831-002: 常時稼働のための不具合修正（マサルのプレモーテム M2/M7/M9/F8）
# ==========================================================================
def test_api_failure_is_never_recorded_as_exhaustion(sandbox, monkeypatch):
    """★最重要。Keepa がエラーを返したのを「掘り切りました」と書かない。

    ここを混ぜると、キー失効もプラン切れも Keepa 障害も全部「正常終了」に見え、
    誰も壊れたことに気づけません（night-shift が14日間死んでいたのと同じ構図）。
    """
    s = sandbox.s
    real = s.keepa_get

    def failing(path, params, budget, label):
        if path == "query":
            s.API.fail(f"{label} HTTP 402")
            return {}                    # エラー時に呼び出し側へ返る値
        return real(path, params, budget, label)

    monkeypatch.setattr(s, "keepa_get", failing)
    s.run(_args())

    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert prog["cursor"]["exhausted"] == []          # 掘り切り扱いにしていない
    assert "掘り切りました" not in prog["stop_reason"]
    assert "異常応答" in prog["stop_reason"]
    alert = (sandbox.out / "ALERT.md").read_text(encoding="utf-8")
    assert "掘り切りではありません" in alert


def test_a_genuine_empty_page_is_still_treated_as_exhaustion(sandbox):
    """正常に0件が返ったときは、これまでどおり掘り切りとして扱う（ALERT は出さない）。"""
    s = sandbox.s
    s.run(_args())
    prog = json.loads((sandbox.out / "progress.json").read_text(encoding="utf-8"))
    assert prog["stop_reason"] == "全シャードを掘り切りました"
    assert not (sandbox.out / "ALERT.md").exists()


def test_a_high_api_error_rate_halts_the_run(sandbox):
    """直近リクエストのエラー率が閾値を超えたら止まる（S3）。"""
    s = sandbox.s
    watch = s.StopWatch(1.0)
    for _ in range(30):
        s.API.fail("HTTP 500")
    assert watch.should_stop()
    assert "API エラー率" in watch.reason
    assert (sandbox.out / "ALERT.md").exists()


def test_token_wait_gives_up_instead_of_spinning_forever(sandbox, monkeypatch):
    """★M7。ネットワークが死んでいるとき、以前は永久に10秒スリープを繰り返していた。"""
    s = sandbox.s

    def dead():
        raise OSError("ネットワークに到達できません")

    monkeypatch.setattr(s, "token_status", dead)
    monkeypatch.setattr(s, "TOKEN_STARVE_MINUTES", 0)   # 即座に諦める設定
    watch = s.StopWatch(1.0)
    assert s.Budget().wait(100, watch) is False
    assert watch.reason
    assert (sandbox.out / "ALERT.md").exists()


def test_maker_csv_carries_a_freshness_date(sandbox):
    """★M9。想定仕入れ金額は取得時点の価格から逆算した値なので、日付が要る。"""
    s = sandbox.s
    s.run(_args())
    with open(sandbox.out / "makers.csv", encoding="utf-8-sig") as f:
        rows = list(__import__("csv").DictReader(f))
    assert rows
    assert rows[0]["最終取得日"]
    assert rows[0]["鮮度"] == "OK"        # 今取ったばかりなので OK


def test_duplicate_asins_do_not_inflate_the_contact_order(sandbox):
    """★F8。台帳が消えて重複行が入っても「該当商品数」を水増ししない。

    水増しされると 03_メーカー名寄せ.csv の並び順が変わり、
    社長が上から連絡する順番が、見た目では分からないまま壊れます。
    """
    s = sandbox.s
    s.run(_args())
    import csv as _csv
    with open(sandbox.out / "go.csv", encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    s.append_rows(s.CSV_GO, s.FIELDS, rows)      # 同じ行をもう一度追記＝重複を作る
    before = {r["メーカー/ブランド"]: r["該当商品数"] for r in _read_makers(sandbox)}
    s.rebuild_maker_csv()
    after = {r["メーカー/ブランド"]: r["該当商品数"] for r in _read_makers(sandbox)}
    assert after == before


def _read_makers(sandbox):
    import csv as _csv
    with open(sandbox.out / "makers.csv", encoding="utf-8-sig") as f:
        return list(_csv.DictReader(f))


def test_seen_ledger_is_rebuilt_from_csv_when_it_disappears(sandbox):
    """台帳ファイルが消えても、CSV から復元して二度取りを防ぐ（F8 の元栓）。"""
    s = sandbox.s
    s.run(_args())
    known = s.load_seen()
    assert known
    (sandbox.out / "seen.txt").unlink()
    assert s.load_seen() == known


def test_heartbeat_is_written_while_scanning(sandbox):
    """★M1。PID ではなく心拍ファイルの mtime で生死を判定する。"""
    s = sandbox.s
    s.run(_args())
    hb = json.loads((sandbox.out / "heartbeat.json").read_text(encoding="utf-8"))
    assert hb["epoch"] > 0
    assert hb["pid"] == __import__("os").getpid()


def test_raw_responses_are_not_written_by_default(sandbox):
    """★M8。どのコードも読んでいない 1GB/日 を既定で書かない。"""
    s = sandbox.s
    s.run(_args())
    assert list((sandbox.out / "raw").glob("*.gz")) == []


def test_keep_raw_flag_still_writes_them(sandbox, monkeypatch):
    s = sandbox.s
    monkeypatch.setattr(s, "KEEP_RAW", [True])
    s.run(_args())
    assert list((sandbox.out / "raw").glob("*.gz"))
