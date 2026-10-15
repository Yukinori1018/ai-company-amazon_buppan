"""criteria_check.py 基準5（利益率5%に必要な掛け ≥ 40%）のテスト（タカシ 2026-10-16）

実行：python3 -m pytest test_criteria_check.py  または  python3 test_criteria_check.py
Keepa もシートも触らない。基準1〜4・6 はすべて通る行を作り、基準5だけを動かす。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import criteria_check as cc  # noqa: E402

# 基準1〜4・6 を通す最小の行（月販100・本体在庫切れ率100%・FBA2・新品3・ランク1万位）
ROW = {'過去1ヶ月の販売数(実画面9/30)': '100点以上', 'Amazon本体の有無': 'なし', '新品出品数(実画面)': '3',
       '判定': '接触候補'}
CAND = {'本体365日在庫切れ率(代表)': '100', '代表のFBA数': '2'}
KP = {'stats': {'current': [0, 0, 0, 10_000]}}


def profit(price, up5):
    return {cc.COL_PRICE: str(price), cc.COL_UP5: str(up5)}


def test_low_price_ok_when_margin_reachable():
    # 売価2,000円（旧基準なら NG）・必要掛け45% → OK。採算メモ用に「掛け交渉次第」が出る
    p = profit(2000, 900)
    assert cc.check(ROW, CAND, p, KP) == 'OK'
    assert cc.kake_note(cc.need_kake(p)).startswith('掛け交渉次第')


def test_ng_when_margin_needs_low_kake():
    # 必要掛け30% → NG
    s = cc.check(ROW, CAND, profit(3000, 900), KP)
    assert s == 'NG：5%に必要な掛け30%<40%'
    assert cc.reason_tags(s) == ['必要な掛け']


def test_ng_when_cap_not_positive():
    # 上限卸値が0以下（タダでも5%に届かない）→ NG
    assert cc.check(ROW, CAND, profit(1500, -120), KP).startswith('NG：5%に必要な掛け0%<40%')


def test_unknown_when_no_profit_columns():
    # 採算列が無い → 未確認：採算（旧基準のように候補CSVの売価へは逃げない）
    assert cc.check(ROW, dict(CAND, 代表の売価='5000'), {}, KP) == '未確認：採算'


def test_cart_fba_fills_fba_lower_bound():
    # FBA 数が取れない行でも、実画面でカート保持者の出荷が FBA なら FBA≥1 として読む
    cand = {'本体365日在庫切れ率(代表)': '100'}
    assert cc.check(ROW, cand, profit(2000, 1000), KP) == '未確認：FBA数'
    assert cc.check(dict(ROW, _cart_fba=True), cand, profit(2000, 1000), KP) == 'OK'


def test_no_note_at_50_percent_or_more():
    assert cc.kake_note(cc.need_kake(profit(2000, 1000))) == ''


def _with_kz(est: dict):
    cc._KZ = {'BTEST00001': est}


HIDDEN = dict(ROW, **{'過去1ヶ月の販売数(実画面9/30)': '表示なし（月50個未満）／実画面10/16', '代表ASIN(タカシ)': 'BTEST00001'})


def test_kz_estimate_below_50_stays_ng_with_note():
    # 実画面で表示なし・推定 直近30日14個 → NG のまま。推定値と限界を〔〕で添え、集計タグは「月販表示なし」のまま
    _with_kz({'m': [14, 13, 13], 'obs': [73, 73, 64], 'family': True, 'badge': (50, '08/29'), 'day': '10/16'})
    s = cc.check(HIDDEN, CAND, profit(2000, 1000), KP)
    assert s.startswith('NG：月販表示なし〔キーゾン式推定（直近30日 14個 3か月 14/13/13')
    assert 'family' in s and '月13個超は過小' in s and '50+' in s
    assert cc.reason_tags(s) == ['月販表示なし']


def test_kz_estimate_50_or_more_passes():
    _with_kz({'m': [60, 40, 30], 'obs': [90, 90, 90], 'family': False, 'badge': None, 'day': '10/16'})
    assert cc.check(HIDDEN, CAND, profit(2000, 1000), KP) == 'OK'


def test_no_kz_history_keeps_old_behavior():
    cc._KZ = {}
    assert cc.check(HIDDEN, CAND, profit(2000, 1000), KP) == 'NG：月販表示なし'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
