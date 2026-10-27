"""T-20260930-001 打診順（第1弾／第2弾／下書き済／対象外）の付与と、第1弾の基準の検算（タカシ 2026-10-10）

社長承認（10/10）：「そのまま出品できる社から打診を始める。ただし基準は確保して」

区分（シート「メーカー連絡先」の 53 列目「打診順」）
  下書き済 … 打診メールの下書きを作成済み・送信済みの社（DRAFTED）。出品可否に関係なく
  第1弾-NN … 接触候補 ＆ 連絡先あり ＆ 基準チェック=OK ＆ 出品可否=出品できる ＆ 未送信 ＆ 下の検算を全部通過
  第2弾-NN … 同条件で 出品可否=出品許可が必要
  保留（秘書判断：理由） … 第1弾/第2弾の条件は通ったが、秘書が後回しにした社（70_秘書判断_*.csv）
  対象外（理由） … それ以外。理由は最初に当たったもの1つ
  NN は送信順（成約しやすさ順・sync_ledger.py の send_key）を保った連番

検算（第1弾・第2弾の全行。基準チェック列の判定とは独立に、値を取り直して1項目ずつ見る）
  月販 ≥ 50                      … 実画面の表示 → 候補CSV → Keepa monthlySold
  本体365日在庫切れ率 ≥ 90%       … 候補CSV → Keepa outOfStockPercentage365。実画面で本体ありなら NG
  FBA ≥ 2 または（新品 ≥ 2 かつ FBA ≥ 1）
  売れ筋ランク ≤ 5万              … Keepa stats.current[3]
  利益率5%に必要な掛け ≥ 40%      … 40_採算列の上限卸値(5%)÷平時売価（criteria_check.need_kake）
                                     2026-10-16 までは「売価 ≥ 2,200円」（カズヨ判断A・§3.3-27／§3.5）
  カート保持者が本体・メーカー本人でない、かつ実画面で確認済み
                                  … カート保持者列に「確認」の記載、または 30_verify_cart.tsv（9/30 実画面）
                                     ／61_checked_asins.json（10/5 実画面）に ASIN がある
  公式ページで商品と社名の紐付け確認済み … 紐付けの判定を link_verdict() で4値に正規化して「一致」で始まり、根拠URLがある
                                     （「ブランド単位：…」「表記ゆれ：…」の自由記述も読む。シートの原文は書き換えない）

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

MIN_SOLD, MIN_OOS, MAX_RANK = 50, 90, 50_000  # 売価の下限 MIN_PRICE=2,200 は 2026-10-16 に廃止


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


# 2026-10-12（タカシ）：秘書の判断を上書きファイルで持つ（元の batch CSV・シートの原文は書き換えない）
# 70_秘書判断_*.csv：代表ASIN,正式社名,判定,理由,判断者,日付。判定は3値
#   除外   … 判定列を「除外：理由」に書き換える（送信キューから外れる）
#   後回し … 判定は接触候補のまま。第1弾/第2弾に入る行を「保留（秘書判断：理由）」にする
#   残す   … 区分は変えない。備考に注記だけ足す（2026-10-20 から秘書は「送る」とも書く。同じ扱い）
#   後回し解除 … 判定「接触候補（後回し：…）」を「接触候補」に戻す（元の判定は備考へ）。2026-10-14 追加
# どれも備考に「秘書判断（日付・判断者）：…」を追記する。後のファイルが勝つ
DECISION_GLOB = '70_秘書判断_*.csv'


def load_decisions() -> dict[str, dict]:
    import glob
    out: dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(WORK, DECISION_GLOB))):
        for x in csv.DictReader(open(p, encoding='utf-8-sig')):
            out[x['代表ASIN'].strip()] = {k: (v or '').strip() for k, v in x.items()}
    return out


DECISIONS = load_decisions()


def apply_decisions(rows: list[dict]) -> dict:
    """判定列（除外）と備考を秘書判断で上書きする。sync_ledger の送信順の並べ替えより前に呼ぶ。"""
    from collections import Counter
    n = Counter()
    for r in rows:
        d = DECISIONS.get(r.get('代表ASIN(タカシ)', ''))
        if not d:
            continue
        note = f'秘書判断（{d["日付"][5:].replace("-", "/")}・{d["判断者"]}）：{d["判定"]}：{d["理由"]}'
        if note not in (r.get('備考') or ''):
            r['備考'] = '／'.join(s for s in [r.get('備考') or '', note] if s)
        if d['判定'] == '除外':
            r['判定'] = f'除外：{d["理由"]}'
        elif d['判定'] in ('残す', '送る') and '酒類' in d['理由'] and (r.get('流通形態') or '').startswith(LIQUOR):
            # 2026-10-16（タカシ）：流通形態は備考の語で機械分類するので、カート保持店が「酒類卸」なだけの
            # 食品メーカー（沖縄製粉）が「酒類」になった。秘書が「残す・理由に酒類」と書いた行だけ解く
            r['流通形態'] = f'不明（秘書判断：酒類は機械分類の誤り。元：{r["流通形態"]}）'
            r['_dist'] = 1
            if (r.get('判定') or '').startswith('接触候補（後回し：流通形態）'):
                r['判定'] = '接触候補' + r['判定'][len('接触候補（後回し：流通形態）'):]
        elif d['判定'] == '後回し解除' and (r.get('判定') or '').startswith('接触候補（後回し'):
            # 2026-10-14（タカシ）：採取時の「接触候補（後回し：…）」を秘書が解いた行。元の判定は備考に残す
            old = f'元の判定：{r["判定"]}'
            if old not in r['備考']:
                r['備考'] = '／'.join(s for s in [r['備考'], old] if s)
            r['判定'] = '接触候補'
        n[d['判定']] += 1
    return dict(n)


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


LINK_VALUES = ('一致', '一致（ブランド単位）', '一致（表記ゆれ）', '未確認')


def link_verdict(raw: str) -> str:
    """紐付けの判定の自由記述を4値に正規化する（2026-10-11 タカシ）。

    10/04 の確認（09_）は「一致／一致（表記ゆれ）／一致（ブランド単位）／未確認」の4値だったが、
    その後のバッチで「ブランド単位：…」「表記ゆれ：…」と「一致」を付けずに書いた行があり、
    検算の startswith('一致') で取りこぼしていた。ブランド単位は 10/04 からの既定どおり確認済みに数える。
    「〜で確認済み」（他行への参照）は参照先を辿っていないので未確認のまま（甘く読まない）。
    """
    s = (raw or '').strip()
    if s.startswith(('一致（ブランド単位）', '一致(ブランド単位)', 'ブランド単位')):
        return '一致（ブランド単位）'
    if s.startswith(('一致（表記ゆれ）', '一致(表記ゆれ)', '表記ゆれ')):
        return '一致（表記ゆれ）'
    if s.startswith(('一致', '製造元として一致', '社名一致')):
        return '一致'
    return '未確認'


def measure(r: dict, cand: dict, profit: dict, kp: dict | None) -> dict:
    """検算に使う値と出典を1行ぶん取り出す（判定はしない）。"""
    from criteria_check import _keepa, need_kake
    k = _keepa(kp or {})
    m: dict = {}

    shown = r.get('過去1ヶ月の販売数(実画面9/30)') or ''
    # 2026-10-13：「未調査（batchZ3の範囲外）」のバッチ名の数字を月販と読まない（criteria_check._shown_int と同じ）
    if shown and '表示なし' not in shown and not shown.startswith(('未調査', '未確認')) and _int(shown) is not None:
        m['月販'], m['月販の出典'] = _int(shown), ('Keepa' if 'Keepa' in shown else '実画面')
    elif _int(cand.get('過去1ヶ月の販売数(代表)')) is not None:
        m['月販'], m['月販の出典'] = _int(cand.get('過去1ヶ月の販売数(代表)')), '候補CSV(Keepa)'
    elif k['sold'] is not None:
        m['月販'], m['月販の出典'] = k['sold'], 'Keepaキャッシュ'
    else:
        m['月販'], m['月販の出典'] = (0, '実画面で表示なし') if '表示なし' in shown else (None, '')
    # 2026-10-16：実画面で表示なしの行はキーゾン式推定（直近30日）を月販に使う（criteria_check と同じ線）
    if '表示なし' in shown and '実画面未確認' not in shown:
        from criteria_check import kz_estimate
        e = kz_estimate(r.get('代表ASIN(タカシ)') or (kp or {}).get('asin') or '')
        if e and not e.get('none'):
            m['月販'], m['月販の出典'] = e['m'][0], 'キーゾン式推定(実画面は表示なし)'

    oos = _int(cand.get('本体365日在庫切れ率(代表)'))
    m['本体在庫切れ率365'] = oos if oos is not None else k['oos']
    m['本体あり(実画面)'] = (r.get('Amazon本体の有無') or '').startswith(('あり', '有')) \
        or 'Amazon.co.jp' in (r.get('カート保持者(実画面9/30)') or '')

    fba = _int(cand.get('代表のFBA数'))
    m['FBA数'] = fba if fba is not None else k['fba']
    if m['FBA数'] is None and r.get('_cart_fba'):  # 実画面でカート保持者の出荷が FBA＝下限1（2026-10-16）
        m['FBA数'] = 1
    new_s = r.get('新品出品数(実画面)') or ''
    new = _int(new_s) if new_s and not new_s.startswith(('未確認', '未調査')) else None
    if new is None:
        new = _int(cand.get('代表の新品オファー数'))
    m['新品数'] = new if new is not None else k['new']

    m['ランク'] = k['rank']
    m['売価'] = _int(profit.get('平時売価(円・税込)')) or _int(r.get('代表の売価')) or _int(cand.get('代表の売価'))
    m['必要掛け'] = need_kake(profit)  # 利益率5%に必要な掛け（0〜1）。計算できなければ None

    cart = r.get('カート保持者(実画面9/30)') or ''
    m['カート保持者'] = cart
    m['カート実画面確認'] = (('確認' in cart and not cart.startswith('未調査'))
                       or r.get('代表ASIN(タカシ)', '') in LIVE)
    m['紐付けの判定(原文)'] = r.get('紐付けの判定') or ''
    m['紐付けの判定'] = link_verdict(m['紐付けの判定(原文)'])
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
    from criteria_check import kake_ng
    if m['必要掛け'] is None:
        bad.append('採算未計算')
    elif kake_ng(m['必要掛け']):
        bad.append(kake_ng(m['必要掛け']))
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
    st = (r.get('接触ステータス') or '').strip()
    # お断りは下書き済（DRAFTED の固定リスト）より先に見る。返事が来た社を「下書き済」に戻さない
    # （2026-10-18 ナチュラルウェーブ・第一酵母がお断りでも「下書き済」のままだった）
    if st == 'お断り':
        return '対象外（接触済：お断り）', []
    if (r.get('正式社名') or '') in DRAFTED:
        return '下書き済', []
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
    d = DECISIONS.get(r.get('代表ASIN(タカシ)', ''))
    if d and d['判定'] == '後回し' and lst.startswith(('出品できる', '出品許可が必要')):
        return f'保留（秘書判断：{d["理由"]}）', []
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
               '売れ筋ランク', '売価(円)', '5%に必要な掛け(%)', 'カート保持者', 'カート実画面確認', '紐付けの判定', '紐付けの判定(原文)', '紐付け根拠URL', '基準チェック']


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
                    '5%に必要な掛け(%)': '' if m['必要掛け'] is None else round(m['必要掛け'] * 100),
                    'カート保持者': m['カート保持者'], 'カート実画面確認': '済' if m['カート実画面確認'] else '未',
                    '紐付けの判定': m['紐付けの判定'], '紐付けの判定(原文)': m['紐付けの判定(原文)'], '紐付け根拠URL': m['紐付け根拠URL'],
                    '基準チェック': r.get(check_col, '')})
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_COLS)
        w.writeheader()
        w.writerows(out)
    return len(out)
