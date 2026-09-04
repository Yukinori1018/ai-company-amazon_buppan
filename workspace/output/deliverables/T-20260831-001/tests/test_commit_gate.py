#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""commit_gate.py の回帰テスト。

**なぜこのファイルが要るのか。**
2026-09-04（T-20260904-004 / B-1 前半）に、commit ゲートが `entity_type` 列を条件に
「個人事業主の疑い」を弾く実装になっていたが、`contacts_v1.csv` にその列自体が存在せず
（`pipeline/schema.ContactFields` に無い）、条件が常に空文字と比較されて**素通り**していた。
ゲートは「実行されて 0 件」を返しており、**通っているように見えていた**。

PUBLIC リポに個人の連絡先を1行でも commit すると、取り下げに force push
（CLAUDE.md §4.1 の不可逆操作）が要る。**素通りは事故に直結する。**

したがってこのテストは「例外なく走った」ではなく、
**わざと引っかかるデータを与えて、実際に検知が発火すること**を確かめる。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import commit_gate  # noqa: E402


CSV_COLS = ["メーカー名", "分類", "正式商号", "所在地", "公式HP", "電話",
            "問い合わせフォームURL", "メール"]


def _write_csv(path, rows):
    with io.open(path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CSV_COLS})
    return str(path)


def _write_jsonl(path, entries):
    with io.open(path, "w", encoding="utf-8") as fp:
        for e in entries:
            fp.write(json.dumps(e, ensure_ascii=False) + "\n")
    return str(path)


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """JSONL の参照先を差し替えたゲートを返す。"""
    def _run(csv_rows, jsonl_entries):
        jl = _write_jsonl(tmp_path / "exa_lookups.jsonl", jsonl_entries)
        monkeypatch.setattr(commit_gate, "EXA_JSONL", jl)
        c = _write_csv(tmp_path / "contacts.csv", csv_rows)
        return commit_gate.check(c)
    return _run


# --- ★本命。ここが素通りしていた ---------------------------------------

def test_個人事業主はCSVにentity_type列が無くてもJSONL経由で検知される(gate):
    """CSV 側に entity_type 列が存在しない状態を再現する。これが実際の contacts_v1.csv。"""
    rows = [{"メーカー名": "からからつみき", "公式HP": "http://example.jp/",
             "メール": "example@plala.or.jp"}]
    entries = [{"メーカー名": "からからつみき", "entity_type": "個人事業主の疑い"}]
    _rows, filled, hits = gate(rows, entries)

    assert filled, "連絡先が1つ以上ある行として拾えていない（前段の時点で壊れている）"
    assert any(k.startswith("個人事業主") for k, _n, _d in hits), \
        "個人事業主の疑いが検知されていない。ゲートが素通りしている"


def test_JSONLが空なら個人事業主は検知できない_フォールバックの依存を明示する(gate):
    """補完元が消えると検知力も消える、という依存関係をテストで固定する。

    JSONL を消したり移動したりしたときに**静かに検知力が落ちる**ことを、
    このテストの存在で気づけるようにしておく。
    """
    rows = [{"メーカー名": "からからつみき", "公式HP": "http://example.jp/"}]
    _rows, _filled, hits = gate(rows, [])
    assert not [h for h in hits if h[0].startswith("個人事業主")]


def test_CSV側にentity_type列がある場合はそちらが使われる(tmp_path, monkeypatch):
    """将来 schema に entity_type が入っても壊れないこと。"""
    jl = _write_jsonl(tmp_path / "e.jsonl", [])
    monkeypatch.setattr(commit_gate, "EXA_JSONL", jl)
    p = tmp_path / "c.csv"
    with io.open(p, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=CSV_COLS + ["entity_type"])
        w.writeheader()
        w.writerow({"メーカー名": "個人工房", "電話": "03-0000-0000",
                    "entity_type": "個人事業主"})
    _rows, _filled, hits = commit_gate.check(str(p))
    assert any(k.startswith("個人事業主") for k, _n, _d in hits)


# --- 残り4条件も、発火することを1件ずつ確かめる -------------------------

def test_ノーブランド個人らしきに連絡先が入ったら検知する(gate):
    rows = [{"メーカー名": "謎ブランド", "分類": "ノーブランド・個人らしき",
             "電話": "090-0000-0000"}]
    _r, _f, hits = gate(rows, [])
    assert any("ノーブランド" in k for k, _n, _d in hits)


def test_姓名らしいメールアドレスを検知する(gate):
    rows = [{"メーカー名": "某社", "メール": "t.suzuki@example.co.jp"}]
    _r, _f, hits = gate(rows, [])
    assert any("個人名らしいメール" in k for k, _n, _d in hits)


def test_infoアドレスは誤爆しない(gate):
    rows = [{"メーカー名": "某社", "メール": "info@example.co.jp"}]
    _r, _f, hits = gate(rows, [])
    assert not hits


def test_居宅らしい所在地を検知する(gate):
    rows = [{"メーカー名": "某社", "電話": "03-0000-0000",
             "所在地": "東京都○○区○○1-2-3 ○○マンション203"}]
    _r, _f, hits = gate(rows, [])
    assert any("居宅" in k for k, _n, _d in hits)


def test_工業団地を居宅と誤判定しない(gate):
    """2026-09-04 に旭化成ワッカーシリコンの『つくば明野工業団地』で発火した誤爆の回帰。"""
    rows = [{"メーカー名": "某社", "電話": "029-000-0000",
             "所在地": "茨城県筑西市つくば明野工業団地1-1"}]
    _r, _f, hits = gate(rows, [])
    assert not hits


def test_号室つき所在地は別区分で人に回す(gate):
    rows = [{"メーカー名": "某社", "電話": "03-0000-0000",
             "所在地": "東京都○○区○○1-2-3 ○○ビル905号室"}]
    _r, _f, hits = gate(rows, [])
    assert any("号室" in k for k, _n, _d in hits)


def test_連絡先が空の行は検査対象外(gate):
    """連絡先が無ければ公衆送信される個人情報も無い。ここで弾いておかないとノイズだらけになる。"""
    rows = [{"メーカー名": "からからつみき", "所在地": "東京都○○区○○マンション203"}]
    entries = [{"メーカー名": "からからつみき", "entity_type": "個人事業主の疑い"}]
    _r, filled, hits = gate(rows, entries)
    assert filled == []
    assert hits == []


def test_抵触ゼロなら空リストを返す(gate):
    rows = [{"メーカー名": "株式会社某", "所在地": "東京都千代田区丸の内1-1-1",
             "電話": "03-0000-0000", "メール": "info@example.co.jp"}]
    _r, filled, hits = gate(rows, [])
    assert len(filled) == 1
    assert hits == []


# --- ★2件目の「読めていないのに緑」事故の回帰 -------------------------

def test_注記行で始まるCSVでもヘッダを取り違えない(tmp_path, monkeypatch):
    """成果物CSVは打診文の禁止事項を `#` 注記としてヘッダ行の前に置いている。

    2026-09-04、この注記行を csv.DictReader がヘッダとして食い、列名が1つも
    一致しなくなった結果、ゲートが「連絡先が1つ以上ある行: 0 / 抵触0件 →
    commit してよい」と**緑を返した**。全行が連絡先の一覧であるファイルに対して。
    """
    jl = _write_jsonl(tmp_path / "e.jsonl", [])
    monkeypatch.setattr(commit_gate, "EXA_JSONL", jl)
    p = tmp_path / "deliv.csv"
    with io.open(p, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("# 【打診文の絶対条件】メール本文・署名にURLを一切貼らないこと\n")
        w = csv.DictWriter(fp, fieldnames=CSV_COLS)
        w.writeheader()
        w.writerow({"メーカー名": "某社", "電話": "03-0000-0000",
                    "メール": "info@example.co.jp"})
    rows, filled, hits = commit_gate.check(str(p))
    assert len(rows) == 1
    assert len(filled) == 1, "注記行をヘッダと取り違えている（連絡先を1件も見つけられていない）"
    assert hits == []


def test_連絡先の列が無いCSVは緑にせず例外にする(tmp_path, monkeypatch):
    """「読めなかった」を「問題なし」に化けさせない。"""
    jl = _write_jsonl(tmp_path / "e.jsonl", [])
    monkeypatch.setattr(commit_gate, "EXA_JSONL", jl)
    p = tmp_path / "wrong.csv"
    with io.open(p, "w", encoding="utf-8-sig", newline="") as fp:
        fp.write("列A,列B\n1,2\n")
    try:
        commit_gate.check(str(p))
    except commit_gate.GateCannotRead:
        return
    raise AssertionError("連絡先の列が1つも無いのに例外にならなかった（緑に化ける）")


def test_伏せ字は連絡先として数えない(gate):
    """伏せた欄の「【非掲載】…」を連絡先とみなすと、伏せた社が延々と再ヒットする。"""
    mark = commit_gate.REDACTED_MARK_PREFIX + "個人事業主の疑いのため掲載しない"
    rows = [{"メーカー名": "個人工房", "電話": mark, "公式HP": mark, "メール": mark}]
    entries = [{"メーカー名": "個人工房", "entity_type": "個人事業主の疑い"}]
    _r, filled, hits = gate(rows, entries)
    assert filled == [], "伏せ字を連絡先として数えている"
    assert hits == []


def test_伏せ字と実データが混在する行は実データを見る(gate):
    mark = commit_gate.REDACTED_MARK_PREFIX + "掲載しない"
    rows = [{"メーカー名": "某社", "電話": mark, "メール": "t.suzuki@example.co.jp"}]
    _r, filled, hits = gate(rows, [])
    assert len(filled) == 1
    assert any("個人名らしいメール" in k for k, _n, _d in hits)
