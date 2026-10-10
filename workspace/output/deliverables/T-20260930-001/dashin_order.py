"""T-20260930-001 打診順（第1弾／第2弾／下書き済／対象外）の付与と、第1弾の基準の検算（タカシ 2026-10-10）

社長承認（10/10）：「そのまま出品できる社から打診を始める。ただし基準は確保して」

区分（シート「メーカー連絡先」の 53 列目「打診順」）
  下書き済 … 打診メールの下書きを作成済み・送信済みの社（DRAFTED）。出品可否に関係なく
  第1弾-NN … 接触候補 ＆ 連絡先あり ＆ 基準チェック=OK ＆ 出品可否=出品できる ＆ 未送信 ＆ 下の検算を全部通過
  第2弾-NN … 同条件で 出品可否=出品許可が必要
  対象外（理由） … それ以外。理由は最初に当たったもの1つ
  NN は送信順（成約しやすさ順・sync_ledger.py の send_key）を保った連番

検算（第1弾・第2弾の全行。基準チェック列の判定とは独立に、値を取り直して1項目ずつ見る）
  月販 ≥ 50                      … 実画面の表示 → 候補CSV → Keepa monthlySold
  本体365日在庫切れ率 ≥ 90%       … 候補CSV → Keepa outOfStockPercentage365。実画面で本体ありなら NG
  FBA ≥ 2 または（新品 ≥ 2 かつ FBA ≥ 1）
  売れ筋ランク ≤ 5万              … Keepa stats.current[3]
  売価 ≥ 2,200円                  … 40_採算列の平時売価 → 代表の売価
  カート保持者が本体・メーカー本人でない、かつ実画面で確認済み
                                  … カート保持者列に「確認」の記載、または 30_verify_cart.tsv（9/30 実画面）
                                     ／61_checked_asins.json（10/5 実画面）に ASIN がある
  公式ページで商品と社名の紐付け確認済み … 紐付けの判定が「一致」で始まり、根拠URLがある

※ このファイルは PUBLIC リポに入る。値（連絡先・売価）はシートと agent_output の CSV にだけ出す。
"""
from __future__ import annotations

import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../../..')),
                    'workspace/output/agent_output/T-20260930-001')

COL = '打診順'
# 下書き作成済み・送信済み（10/4〜10/5 の打診文20社のうち、Gmail 下書きまで進んだ社）。正式社名で引く
DRAFTED = ['ナチュラルウェーブ株式会社', '株式会社ユニマットリケン', '第一酵母株式会社', 'Peaker株式会社',
           '株式会社feel.', '素数株式会社', '株式会社諏訪田製作所', 'リードバディ株式会社']
LIQUOR = '酒類'  # 流通形態がこれで始まる社は販売免許が無いので打診しない

MIN_SOLD, MIN_OOS, MAX_RANK, MIN_PRICE = 50, 90, 50_000, 2_200


def _int(s) -> int | None:
    m = re.search(r'-?\d[\d,]*', str(s or ''))
    return int(m.group().replace(',', '')) if m else None


def _load_live_asins() -> set[str]:
    """実画面でカート保持者を見た ASIN（9/30 上位50社・10/5 一括確認）。"""
    out: set[str] = set()
    p = os.path.join(WORK, '30_verify_cart.tsv')
    if os.path.exists(p):
        out |= {line.split('\t')[0] for line in open(p, encoding='utf-8') if line.strip()}
    p = os.path.join(WORK, '61_checked_asins.json')
    if os.path.exists(p):
        out |= set(json.load(open(p, encoding='utf-8')))
    return out


LIVE = _load_live_asins()


def contact_means(r: dict) -> str:
    """メール＞フォーム＞電話のみ＞なし（メールがあれば他の有無を問わずメール）。"""
    mail = '@' in (r.get('メールアドレス') or '')
    form = (r.get('問い合わせフォームURL') or '').startswith('http')
    tel = bool(re.search(r'\d{2,}', r.get('電話番号') or ''))
    if mail:
        return 'メール'
    if form:
        return 'フォーム' + ('（電話あり）' if tel else '')
    if tel:
        return '電話のみ'
    return 'なし'


def measure(r: dict, cand: dict, profit: dict, kp: dict | None) -> dict:
    """検算に使う値と出典を1行ぶん取り出す（判定はしない）。"""
    from criteria_check import _keepa
    k = _keepa(kp or {})
    m: dict = {}

    shown = r.get('過去1ヶ月の販売数(実画面9/30)') or ''
    if shown and '表示なし' not in shown and _int(shown) is not None:
        m['月販'], m['月販の出典'] = _int(shown), ('Keepa' if 'Keepa' in shown else '実画面')
    elif _int(cand.get('過去1ヶ月の販売数(代表)')) is not None:
        m['月販'], m['月販の出典'] = _int(cand.get('過去1ヶ月の販売数(代表)')), '候補CSV(Keepa)'
    elif k['sold'] is not None:
        m['月販'], m['月販の出典'] = k['sold'], 'Keepaキャッシュ'
    else:
        m['月販'], m['月販の出典'] = (0, '実画面で表示なし') if '表示なし' in shown else (None, '')

    oos = _int(cand.get('本体365日在庫切れ率(代表)'))
    m['本体在庫切れ率365'] = oos if oos is not None else k['oos']
    m['本体あり(実画面)'] = (r.get('Amazon本体の有無') or '').startswith(('あり', '有')) \
        or 'Amazon.co.jp' in (r.get('カート保持者(実画面9/30)') or '')

    fba = _int(cand.get('代表のFBA数'))
    m['FBA数'] = fba if fba is not None else k['fba']
    new_s = r.get('新品出品数(実画面)') or ''
    new = _int(new_s) if new_s and not new_s.startswith(('未確認', '未調査')) else None
    if new is None:
        new = _int(cand.get('代表の新品オファー数'))
    m['新品数'] = new if new is not None else k['new']

    m['ランク'] = k['rank']
    m['売価'] = _int(profit.get('平時売価(円・税込)')) or _int(r.get('代表の売価')) or _int(cand.get('代表の売価'))

    cart = r.get('カート保持者(実画面9/30)') or ''
    m['カート保持者'] = cart
    m['カート実画面確認'] = (('確認' in cart and not cart.startswith('未調査'))
                       or r.get('代表ASIN(タカシ)', '') in LIVE)
    m['紐付けの判定'] = r.get('紐付けの判定') or ''
    m['紐付け根拠URL'] = r.get('紐付け根拠URL') or ''
    return m


def verify(m: dict, judge: str) -> list[str]:
    """満たさない項目を返す（空なら全部満たす）。データ欠けも「満たさない」に数える。"""
    bad = []
    if m['月販'] is None or m['月販'] < MIN_SOLD:
        bad.append(f'月販{m["月販"] if m["月販"] is not None else "不明"}<{MIN_SOLD}')
    if m['本体あり(実画面)']:
        bad.append('Amazon本体あり')
    elif m['本体在庫切れ率365'] is None or m['本体在庫切れ率365'] < MIN_OOS:
        bad.append(f'本体在庫切れ率{m["本体在庫切れ率365"]}%<{MIN_OOS}%')
    fba, new = m['FBA数'], m['新品数']
    if fba is None or not (fba >= 2 or (new is not None and new >= 2 and fba >= 1)):
        bad.append(f'FBA{fba}・新品{new}')
    if m['ランク'] is None or m['ランク'] > MAX_RANK:
        bad.append(f'ランク{m["ランク"]}>5万')
    if m['売価'] is None or m['売価'] < MIN_PRICE:
        bad.append(f'売価{m["売価"]}<2,200')
    cart = m['カート保持者']
    if 'Amazon.co.jp' in cart or judge.startswith('除外') or '本人' in judge:
        bad.append('カートが本体/メーカー本人')
    elif not m['カート実画面確認']:
        bad.append('カート保持者が実画面未確認')
    if not (m['紐付けの判定'].startswith('一致') and m['紐付け根拠URL'].startswith('http')):
        bad.append('公式ページでの紐付け未確認')
    return bad


def classify(r: dict, list_col: str, check_col: str) -> tuple[str, list[str]]:
    """（区分, 検算で外れた項目）。区分は '第1弾'/'第2弾'/'下書き済'/'対象外（理由）'。"""
    if (r.get('正式社名') or '') in DRAFTED:
        return '下書き済', []
    st = (r.get('接触ステータス') or '').strip()
    if st and st != '未接触':
        return f'対象外（接触済：{st}）', []
    j = r.get('判定') or ''
    if not j.startswith('接触候補'):
        return f'対象外（判定：{re.split(r"[：（]", j)[0] or "空欄"}）', []
    if contact_means(r) == 'なし':
        return '対象外（連絡先なし）', []
    lst = r.get(list_col) or ''
    if lst.startswith('出品不可'):
        return '対象外（出品不可）', []
    chk = r.get(check_col) or ''
    if chk.startswith('NG'):
        return '対象外（基準NG）', []
    if chk != 'OK':
        return '対象外（基準未確認）', []
    if not lst or lst.startswith('未確認'):  # 未確認＝sync_ledger が未実測の接触候補に入れる値
        return '対象外（出品可否 未実測）', []
    if (r.get('流通形態') or '').startswith(LIQUOR):
        return '対象外（酒類：販売免許なし）', []
    bad = verify(r['_m'], j)
    if bad:
        return '対象外（検算NG：' + '・'.join(bad) + '）', bad
    if lst.startswith('出品できる'):
        return '第1弾', []
    if lst.startswith('出品許可が必要'):
        return '第2弾', []
    return f'対象外（出品可否：{lst}）', []


def assign(rows: list[dict], list_col: str, check_col: str) -> dict:
    """rows（送信順で並んでいる前提）に COL を書き込み、集計を返す。"""
    n = {'第1弾': 0, '第2弾': 0}
    excluded = []  # 基準チェック=OK なのに検算で外れた行
    for r in rows:
        kind, bad = classify(r, list_col, check_col)
        if kind in n:
            n[kind] += 1
            r[COL] = f'{kind}-{n[kind]:02d}'
        else:
            r[COL] = kind
        if bad:
            excluded.append((r.get('正式社名') or r.get('メーカー名(タカシ)'), r.get(list_col, ''), bad))
    return {'excluded': excluded}


EXPORT_COLS = ['打診順', '送信順', '正式社名', 'ブランド', '代表ASIN', 'Amazon URL', '連絡手段', 'メールアドレス',
               '電話番号', '問い合わせフォームURL', '流通形態', '月販', '月販の出典', '本体在庫切れ率365(%)', 'FBA数', '新品数',
               '売れ筋ランク', '売価(円)', 'カート保持者', 'カート実画面確認', '紐付けの判定', '紐付け根拠URL', '基準チェック']


def export(rows: list[dict], path: str, check_col: str, prefix: str = '第1弾-') -> int:
    """第1弾の一覧を CSV に出す（連絡先を含むので agent_output＝gitignore 側にだけ置く）。"""
    out = []
    for r in rows:
        if not r.get(COL, '').startswith(prefix):
            continue
        m = r['_m']
        out.append({'打診順': r[COL], '送信順': r.get('送信順', ''), '正式社名': r.get('正式社名', ''),
                    'ブランド': r.get('ブランド', ''), '代表ASIN': r.get('代表ASIN(タカシ)', ''),
                    'Amazon URL': r.get('Amazon URL', ''), '連絡手段': contact_means(r),
                    'メールアドレス': r.get('メールアドレス', ''), '電話番号': r.get('電話番号', ''),
                    '問い合わせフォームURL': r.get('問い合わせフォームURL', ''), '流通形態': r.get('流通形態', ''),
                    '月販': m['月販'], '月販の出典': m['月販の出典'], '本体在庫切れ率365(%)': m['本体在庫切れ率365'],
                    'FBA数': m['FBA数'], '新品数': m['新品数'], '売れ筋ランク': m['ランク'], '売価(円)': m['売価'],
                    'カート保持者': m['カート保持者'], 'カート実画面確認': '済' if m['カート実画面確認'] else '未',
                    '紐付けの判定': m['紐付けの判定'], '紐付け根拠URL': m['紐付け根拠URL'],
                    '基準チェック': r.get(check_col, '')})
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLS)
        w.writeheader()
        w.writerows(out)
    return len(out)
