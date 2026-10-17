"""dashin_order.classify の接触ステータスまわりのテスト（タカシ 2026-10-18）

実行：python3 -m pytest test_dashin_order.py  または  python3 test_dashin_order.py
シートも Keepa も触らない。DRAFTED（下書き済の固定リスト）と接触ステータスの優先順位だけを見る。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashin_order as d  # noqa: E402

LIST, CHECK = '出品可否', '基準チェック'
DRAFTED_NAME = d.DRAFTED[0]


def row(name, status):
    return {'正式社名': name, '接触ステータス': status, '判定': '接触候補'}


def test_refusal_beats_drafted():
    # 下書き済リストの社でも、お断りが来たら「お断り」を出す
    assert d.classify(row(DRAFTED_NAME, 'お断り'), LIST, CHECK)[0] == '対象外（接触済：お断り）'


def test_drafted_kept_when_sent_or_untouched():
    # 送信済・未接触のままなら従来どおり「下書き済」
    assert d.classify(row(DRAFTED_NAME, '送信済'), LIST, CHECK)[0] == '下書き済'
    assert d.classify(row(DRAFTED_NAME, '未接触'), LIST, CHECK)[0] == '下書き済'


def test_refusal_for_non_drafted():
    assert d.classify(row('株式会社テスト', 'お断り'), LIST, CHECK)[0] == '対象外（接触済：お断り）'


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_'):
            fn()
            print('ok', name)
