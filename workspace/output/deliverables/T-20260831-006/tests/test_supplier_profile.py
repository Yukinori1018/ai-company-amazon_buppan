"""業態の名寄せテスト。

**社名は実データそのまま**を使う（架空の社名で通しても表記ゆれの検証にならない）。
カズヨが管理画面から取得した `netsea_取引申請状況_480社.csv` の実在行から写している。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import supplier_profile as sp  # noqa: E402

ROWS = [
    {"申請日": "2026/06/03", "サプライヤー名": "株式会社 Sun Growing",
     "業態": "メーカー（雑貨）", "取引状況": "取引中"},
    {"申請日": "2026/06/03", "サプライヤー名": "MAYO×MAYO",
     "業態": "卸および小売業（食品）", "取引状況": "取引中"},
    {"申請日": "2026/06/03", "サプライヤー名": "オリヒロ",
     "業態": "メーカー（食品）", "取引状況": "取引中"},
    {"申請日": "2026/06/03", "サプライヤー名": "どこかの卸",
     "業態": "卸専業（雑貨）", "取引状況": "取引拒否"},
]
P = sp.SupplierProfiles(ROWS)


def test_法人格や空白の違いを吸収して当てる():
    # API は trade_name「オリヒロ 株式会社」、CSV は「オリヒロ」。この差で外れてはいけない。
    assert P.business_type("オリヒロ 株式会社") == "メーカー（食品）"
    assert P.business_type("株式会社オリヒロ") == "メーカー（食品）"
    assert P.business_type("ｵﾘﾋﾛ") == ""   # 半角カナまでは寄せない（誤爆より空欄）


def test_corp_nameとtrade_nameの両方で試す():
    assert P.business_type("知らない名前", "Sun Growing") == "メーカー（雑貨）"


def test_当たらなければ空欄にする():
    # 推測で別の会社の業態を貼る方が、空欄より害が大きい。
    assert P.business_type("存在しない会社") == ""
    assert P.lookup("存在しない会社") is None


def test_メーカー判定():
    assert P.is_maker("株式会社 Sun Growing")
    assert not P.is_maker("MAYO×MAYO")


def test_取引拒否は発注できないと判定する():
    assert P.is_orderable("どこかの卸") is False
    assert P.is_orderable("オリヒロ") is True


def test_名寄せに失敗したらFalseではなくNoneを返す():
    # 不明を駄目に倒すと、突合ミスで正当な取引先が黙って消える。
    assert P.is_orderable("存在しない会社") is None


def test_CSVが無ければ空のプロファイルになり落ちない():
    empty = sp.SupplierProfiles.load("/no/such/file.csv")
    assert len(empty) == 0
    assert empty.business_type("オリヒロ") == ""


def test_実CSVが読めるなら業態が付く():
    # 実ファイルがある環境でだけ確かめる（無ければ黙って飛ばす）。
    path = (Path(__file__).resolve().parents[4]
            / "agent_output" / "T-20260831-006" / "netsea_取引申請状況_480社.csv")
    if not path.exists():
        return
    real = sp.SupplierProfiles.load(path)
    assert len(real) >= 400
    assert real.business_type("オリヒロ 株式会社").startswith("メーカー")
