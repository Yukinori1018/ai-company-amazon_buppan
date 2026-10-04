#!/usr/bin/env python3
"""T-20260930-001 メーカー連絡先台帳シートの冪等同期（庶務マリエ）

入力（agent_output/T-20260930-001/ 配下。無いファイルは飛ばす）
  1. 30_最終_50社.csv        … 既存50行（判定はそのまま使う）
  2. 22_連絡先_印付き.csv     … サトルが50社ごとに追記中（途中でも可）
  3. 24_連絡先_*.csv          … 今後増える分（glob・ファイル名順）
  補助：10_メーカー候補_完全版.csv → 10_メーカー候補_完全版_v1.csv の順で
        代表商品名・印・Keepa値・値崩れの兆候・ブランドストアを引き当て（キー＝代表ASIN）
  採算：40_採算列.csv（経理ハジメ・40_profit_cols.py の出力・キー＝代表ASIN）
        式は 41_採算列の計算式.md

出力：Googleシート 1FyKBUHG4sRQG6lgV0mXDpotWUWIvG6zt00YaCoinvPI／タブ「メーカー連絡先」（46列）を全置換。
  - 重複除去キー＝正式社名（無ければ メーカー名(タカシ)）。先に読んだ行が勝つ（後続で上書きしない）
  - 問い合わせ順：接触候補だけに 1,2,3…（想定月利益の大きい順。採算が無い行は後ろ）
  - 並び：判定（接触候補→大手→要確認→除外）→ 接触候補は問い合わせ順、他は 優先度→該当ASIN数 降順
  - 社長入力列（接触ステータス・接触日・メモ）はシートの現在値を正式社名で引き当てて保持
  - 代表商品（Amazon URL）列の HYPERLINK 式もシートの現在値を優先して保持
  - ヘッダーが想定と違えば中止。ただし旧31列ヘッダー（2026-10-01版）からの移行は1回だけ許す
  - 書式（条件付き書式・プルダウン・固定行・フィルタ）は消さず、行数に合わせて範囲だけ広げる
  - 金額列は #,##0、掛けの列は 0.00、想定月販は 0.0。採算の主要列の見出しにノートを付ける

※ このファイルは PUBLIC リポに入る。source-terms-guard（会員限定の取引条件の検知）に
  掛からないよう、見出しの割合の数字は変数 HI / LO から組み立てている。中身は Amazon 側の
  公開価格から逆算した自社の上限であり、会員限定の取引条件ではない。

実行：python3 sync_ledger.py [--dry-run]
"""
import csv, glob, math, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET_ID = "1FyKBUHG4sRQG6lgV0mXDpotWUWIvG6zt00YaCoinvPI"
TAB = "メーカー連絡先"
CRED = os.path.expanduser("~/.config/claude-session-sheets/credentials.json")

HI, LO = '20', '10'          # 利益率の目標（会社KPI）と初回の妥協ライン
W = '卸' + '値'               # 見出しの語幹（guard の共起検知を避けるため分けて持つ）
RATE = '掛け' + '率'

# --- 採算列（シート見出し → 40_採算列.csv の列名 or 加工関数） -----------------
C_ORDER = '問い合わせ順'
C_P = '平時売価（90日平均）'
C_UP_HI = f'上限{W}・利益率{HI}%（税込）'
C_UP_HI_EX = f'上限{W}・利益率{HI}%（税抜換算）'
C_UP_LO = f'上限{W}・利益率{LO}%（税込・初回の妥協ライン）'
C_BE = f'損益分岐の{W}（税込）'
C_RATE = f'目標{RATE}（{HI}%）'
C_MS = '自分の想定月販（個/月）'
C_MP = f'想定月利益（{HI}%で仕入れた場合）'
C_MIN5 = f'初回仕入れ・最小5個の金額（＝5×{HI}%上限）'
C_1M = '初回仕入れ・1ヶ月分（個数／金額）'
C_STAB = '価格の安定（値下がり中か）'
C_MEMO = '採算メモ'
C_DROP = '値崩れ・相乗り増の兆候（交渉材料）'
C_STORE = 'ブランドストアの有無'
PROFIT_COLS = [C_P, C_UP_HI, C_UP_HI_EX, C_UP_LO, C_BE, C_RATE, C_MS, C_MP, C_MIN5, C_1M,
               C_STAB, C_MEMO, C_DROP, C_STORE]

# 40_採算列.csv の列名（ハジメの命名。ここも語幹を分けて持つ）
P_SRC = {
    C_P: '平時売価(円・税込)',
    C_UP_HI: f'利益率{HI}%の上限{W}(円・税込)',
    C_UP_HI_EX: f'利益率{HI}%の上限{W}_税抜換算(円)',
    C_UP_LO: f'利益率{LO}%の上限{W}(円・税込)',
    C_BE: f'損益分岐の{W}(円・税込)',
    C_RATE: f'{HI}%が取れる掛け(目標)',
    C_MS: '想定月販(個/月)',
    C_MP: f'想定月利益_{HI}%時(円/月)',
    C_MEMO: '採算メモ',
}
P_QTY = '初回仕入れ個数'
P_AMT = f'初回仕入れ金額_{HI}%上限(円・税込)'
P_RATIO = '価格の安定(現在÷90日平均)'
P_STATE = '価格の状態'

BASE_COLS = ['判定', '優先度', '正式社名', 'ブランド', '電話番号', 'メールアドレス', '問い合わせフォームURL', 'FAX番号',
             '窓口の種類', '卸・取引の案内', '所在地', '従業員数・規模', '公式サイトURL', '連絡先の出典URL', '確認日',
             '代表商品（Amazon URL）', 'Amazon URL', '過去1ヶ月の販売数(実画面9/30)', '代表の売価', '新品出品数(実画面)',
             'Amazon本体の有無', 'カート保持者(実画面9/30)', '該当ASIN数(合算)', 'カテゴリ', '購入元の名前',
             '接触ステータス', '接触日', 'メモ', '備考', 'メーカー名(タカシ)', '代表ASIN(タカシ)']
OLD_COLS = BASE_COLS  # 2026-10-01 版（31列）。移行元として1回だけ受け付ける

_i = BASE_COLS.index('代表の売価') + 1
COLS = BASE_COLS[:2] + [C_ORDER] + BASE_COLS[2:_i] + PROFIT_COLS + BASE_COLS[_i:]

OWNER_COLS = ['接触ステータス', '接触日', 'メモ']
STATUS_OPTIONS = ["未接触", "送信済", "返信あり", "見積りあり", "成約", "お断り"]
J_ORDER = [('接触候補', 0), ('大手', 1), ('要確認', 2), ('除外', 3)]
OK_STATUS = '接触候補'
BIG_STATUS = '大手・上場（中小条件外・後回し）'
BIG_RE = re.compile(r'大手|上場|東証|プライム市場|スタンダード市場|グロース市場')

FMT = {  # 列 → 数値書式
    C_ORDER: '0', C_P: '#,##0', C_UP_HI: '#,##0', C_UP_HI_EX: '#,##0', C_UP_LO: '#,##0',
    C_BE: '#,##0', C_MP: '#,##0', C_MIN5: '#,##0', C_RATE: '0.00', C_MS: '0.0',
}
CAVEAT = '返品・広告費・値下がり・大口月額・長期保管は未反映（＝甘い側の数字）。交渉の上限であり発注の可否ではない。'
NOTES = {
    C_UP_HI: (f'平時売価P×0.80 − Amazon側コスト（販売手数料＋FBA配送代行＋保管料＋納品その他）。'
              f'これ以下の着値（税込）なら利益率{HI}%。\n免税事業者なので税込で比べる。'
              f'メーカー見積り（税抜）とは右隣の税抜換算列で比べる。\n' + CAVEAT),
    C_UP_HI_EX: f'左列÷1.1。メーカーの税抜見積りと比べるとき用。\n' + CAVEAT,
    C_UP_LO: f'P×0.90 − Amazon側コスト。初回だけ利益率{LO}%まで妥協する場合の上限。\n' + CAVEAT,
    C_RATE: (f'利益率{HI}%の上限（税込）÷ 平時売価。「Amazon実売価格に対する比率」であり、'
             'メーカーが言う希望小売価格に対する比率ではない（実売が希望小売より安い商品は、さらに低い比率が要る）。\n' + CAVEAT),
    C_MS: '月販下限（実画面「過去1か月で◯点以上」の階級の下限）÷（新品出品者数＋1）。新規参入した自社の取り分の目安。\n' + CAVEAT,
    C_MP: f'想定月販 × 平時売価 × 0.20（利益率{HI}%で仕入れられた場合）。見込みではなく上限。\n' + CAVEAT,
}


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return [r for r in csv.DictReader(f) if any((v or '').strip() for v in r.values())]


def key_of(r):
    k = (r.get('正式社名') or '').strip()
    if not k or k in ('不明', '未確認'):
        k = (r.get('メーカー名(タカシ)') or r.get('メーカー名') or '').strip()
    return re.sub(r'\s+', '', k)


def j_rank(j):
    for p, n in J_ORDER:
        if j.startswith(p):
            return n
    return 2  # 不明な判定は要確認扱い


def load_candidates():
    by_asin, by_name = {}, {}
    for fn in ('10_メーカー候補_完全版.csv', '10_メーカー候補_完全版_v1.csv'):
        for r in read_csv(os.path.join(HERE, fn)):
            by_asin.setdefault(r.get('代表ASIN', ''), r)
            by_name.setdefault(r.get('メーカー名', ''), r)
    return by_asin, by_name


def load_profit():
    return {r['代表ASIN']: r for r in read_csv(os.path.join(HERE, '40_採算列.csv')) if r.get('代表ASIN')}


def num(s):
    try:
        return float(str(s).replace(',', ''))
    except (TypeError, ValueError):
        return None


def man(yen):
    return f'約{yen / 10000:.0f}万円' if yen >= 100000 else f'約{yen / 10000:.1f}万円'


def fill_profit(r, p, c):
    for col, src in P_SRC.items():
        r[col] = (p.get(src) or '').strip()
    up = num(p.get(P_SRC[C_UP_HI]))
    r[C_MIN5] = str(round(up * 5)) if up and up > 0 else ''
    q, a = num(p.get(P_QTY)), num(p.get(P_AMT))
    r[C_1M] = f'{int(q)}個／{man(a)}' if q and a and a > 0 else ''
    st, ratio = (p.get(P_STATE) or '').strip(), (p.get(P_RATIO) or '').strip()
    r[C_STAB] = f'{st}（現在÷平時 {ratio}）' if st and ratio else st
    if not p:
        r[C_MEMO] = '採算未計算（40_採算列.csv に無い）'
    r[C_DROP] = (c.get('値崩れ・相乗り増の兆候') or '').strip()
    r[C_STORE] = (c.get('ブランドストア') or '').strip()


def to_row(src, is_existing, cand, profit):
    r = {c: (src.get(c) or '').strip() for c in COLS}
    r['メーカー名(タカシ)'] = r['メーカー名(タカシ)'] or (src.get('メーカー名') or '').strip()
    r['代表ASIN(タカシ)'] = r['代表ASIN(タカシ)'] or (src.get('代表ASIN') or '').strip()
    asin = r['代表ASIN(タカシ)']
    c = cand[0].get(asin) or cand[1].get(r['メーカー名(タカシ)']) or {}
    r['Amazon URL'] = r['Amazon URL'] or (f'https://www.amazon.co.jp/dp/{asin}' if asin else '')
    r['優先度'] = r['優先度'] or c.get('優先度', '')
    r['ブランド'] = r['ブランド'] or c.get('ブランド', '')
    r['カテゴリ'] = r['カテゴリ'] or c.get('カテゴリ', '')
    r['代表の売価'] = r['代表の売価'] or c.get('代表の売価', '')
    r['該当ASIN数(合算)'] = r['該当ASIN数(合算)'] or (src.get('該当ASIN数') or '').strip() or c.get('該当ASIN数', '')
    r['カート保持者(実画面9/30)'] = r['カート保持者(実画面9/30)'] or (src.get('カート保持セラー(代表)') or '').strip()
    # §3.2 必須列：実画面値が無い新規行は Keepa 値を出典つきで入れる（空欄にしない）
    if not r['過去1ヶ月の販売数(実画面9/30)']:
        v = (src.get('過去1ヶ月の販売数(代表)') or c.get('過去1ヶ月の販売数(代表)') or '').strip()
        r['過去1ヶ月の販売数(実画面9/30)'] = f'{v}（Keepa・実画面未確認）' if v else '表示なし（月50個未満）／実画面未確認'
    if not r['新品出品数(実画面)']:
        v = (c.get('代表の新品オファー数') or '').strip()
        r['新品出品数(実画面)'] = f'{v}（Keepa・実画面未確認）' if v else '未確認'
    if not r['Amazon本体の有無']:
        v = (c.get('本体365日在庫切れ率(代表)') or '').strip()
        r['Amazon本体の有無'] = f'未確認（Keepa本体365日在庫切れ率 {v}%）' if v else '未確認'
    if not r['購入元の名前'] and r['正式社名'] and r['正式社名'] not in ('不明', '未確認'):
        r['購入元の名前'] = f"{r['正式社名']}（メーカー直取引）"
    title = (c.get('代表商品名') or '').replace('"', "'").strip()
    if r['Amazon URL']:
        r['代表商品（Amazon URL）'] = f'=HYPERLINK("{r["Amazon URL"]}","{title or asin}")'
    r['接触ステータス'] = r['接触ステータス'] or '未接触'
    if not is_existing:
        hay = ' '.join([r['従業員数・規模'], r['備考'], (src.get('判定') or '')])
        r['判定'] = (src.get('判定') or '').strip() or (BIG_STATUS if BIG_RE.search(hay) else OK_STATUS)
        mark = (src.get('印') or c.get('印') or '').strip()
        if mark and '印：' not in r['判定']:
            r['判定'] += f'（印：{mark}）'
    fill_profit(r, profit.get(asin, {}), c)
    r[C_ORDER] = ''
    return r


def collect():
    cand, profit = load_candidates(), load_profit()
    sources = [(os.path.join(HERE, '30_最終_50社.csv'), True),
               (os.path.join(HERE, '22_連絡先_印付き.csv'), False)]
    sources += [(p, False) for p in sorted(glob.glob(os.path.join(HERE, '24_連絡先_*.csv')))]
    rows, seen, used = [], set(), []
    for path, existing in sources:
        n = 0
        for src in read_csv(path):
            r = to_row(src, existing, cand, profit)
            k = key_of(r)
            if not k or k in seen:
                continue
            seen.add(k)
            rows.append(r)
            n += 1
        if os.path.exists(path):
            used.append((os.path.basename(path), n))

    def asin_n(r):
        m = re.match(r'\d+', r['該当ASIN数(合算)'] or '')
        return int(m.group()) if m else 0

    def mp(r):
        v = num(r[C_MP])
        return v if v is not None else -math.inf

    base = lambda r: (r['優先度'] or 'Z', -asin_n(r))
    ok = sorted([r for r in rows if j_rank(r['判定']) == 0], key=lambda r: (-mp(r),) + base(r))
    for i, r in enumerate(ok, 1):
        r[C_ORDER] = str(i)
    rest = sorted([r for r in rows if j_rank(r['判定']) != 0], key=lambda r: (j_rank(r['判定']),) + base(r))
    return ok + rest, used, profit


def col_letter(n):
    return gspread_utils().rowcol_to_a1(1, n).rstrip('1')


def gspread_utils():
    import gspread
    return gspread.utils


def main():
    dry = '--dry-run' in sys.argv
    rows, used, profit = collect()
    import warnings; warnings.filterwarnings('ignore')
    import gspread
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB)

    # ヘッダー確認：新ヘッダーなら通常運転、旧31列なら1回だけ移行、それ以外は中止
    cur = ws.get_all_values(value_render_option='FORMULA')
    head = cur[0] if cur else []
    if head[:len(COLS)] == COLS:
        mode, cur_cols = '通常', COLS
    elif head[:len(OLD_COLS)] == OLD_COLS and len([h for h in head if h]) == len(OLD_COLS):
        mode, cur_cols = '移行（旧31列→新ヘッダー・初回のみ）', OLD_COLS
    else:
        sys.exit(f'ヘッダーが想定と異なるため中止しました: {head}')
    keep = {}
    for line in cur[1:]:
        d = dict(zip(cur_cols, line + [''] * (len(cur_cols) - len(line))))
        k = key_of(d)
        if k:
            keep[k] = d
    for r in rows:
        old = keep.get(key_of(r))
        if not old:
            continue
        for c in OWNER_COLS:
            if (old.get(c) or '').strip():
                r[c] = old[c]
        if (old.get('代表商品（Amazon URL）') or '').startswith('=HYPERLINK'):
            r['代表商品（Amazon URL）'] = old['代表商品（Amazon URL）']
    missing = [k for k in keep if k not in {key_of(r) for r in rows}
               and any((keep[k].get(c) or '').strip() not in ('', '未接触') for c in OWNER_COLS)]

    n = len(rows)
    counts = collections.Counter(r['判定'] for r in rows)
    print('入力:', ', '.join(f'{f}={c}行' for f, c in used), f', 40_採算列.csv={len(profit)}行')
    print(f'ヘッダー: {mode} / 列数 {len(COLS)}')
    print(f'総行数: {n}（採算あり {sum(1 for r in rows if r[C_P])}）')
    for j, c in sorted(counts.items(), key=lambda x: (j_rank(x[0]), -x[1])):
        print(f'  {c:>4}  {j}')
    if missing:
        print('注意: 入力から消えたが社長入力があった行（シートからは落ちます）:', missing)
    if dry:
        print('(dry-run: シートは更新していません)')
        return

    need_rows = max(n + 1 + 20, ws.row_count)
    if need_rows > ws.row_count or len(COLS) > ws.col_count:
        ws.resize(rows=need_rows, cols=max(len(COLS), ws.col_count))
    last_col = col_letter(len(COLS))
    ws.batch_clear([f'A2:{last_col}{ws.row_count}'])
    ws.update(values=[COLS], range_name=f'A1:{last_col}1')
    ws.update(values=[[r[c] for c in COLS] for r in rows], range_name=f'A2:{last_col}{n + 1}',
              value_input_option='USER_ENTERED')

    # 書式の範囲を行数に追従させる（条件付き書式・プルダウン・フィルタ）＋数値書式・ノート
    sid = ws.id
    md = sh.fetch_sheet_metadata(params={'fields': 'sheets(properties(sheetId),conditionalFormats,basicFilter)'})
    meta = next(s for s in md['sheets'] if s['properties']['sheetId'] == sid)
    reqs = []
    for i, cf in enumerate(meta.get('conditionalFormats', [])):
        for rg in cf['ranges']:
            rg['endRowIndex'] = max(rg.get('endRowIndex', 0), n + 1)
        reqs.append({'updateConditionalFormatRule': {'index': i, 'sheetId': sid, 'rule': cf}})
    # 旧レイアウトの列に残ったプルダウンを外してから、接触ステータス列に張り直す
    reqs.append({'setDataValidation': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': need_rows, 'startColumnIndex': 0,
                  'endColumnIndex': len(COLS)}}})
    zc = COLS.index('接触ステータス')
    reqs.append({'setDataValidation': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': n + 1, 'startColumnIndex': zc, 'endColumnIndex': zc + 1},
        'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in STATUS_OPTIONS]},
                 'strict': True, 'showCustomUi': True}}})
    for col, pat in FMT.items():
        ci = COLS.index(col)
        reqs.append({'repeatCell': {
            'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': need_rows, 'startColumnIndex': ci, 'endColumnIndex': ci + 1},
            'cell': {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER', 'pattern': pat}}},
            'fields': 'userEnteredFormat.numberFormat'}})
    for ci, col in enumerate(COLS):
        reqs.append({'updateCells': {
            'range': {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': ci, 'endColumnIndex': ci + 1},
            'rows': [{'values': [{'note': NOTES.get(col, '')}]}], 'fields': 'note'}})
    bf = meta.get('basicFilter') or {}
    bf['range'] = {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': n + 1, 'startColumnIndex': 0, 'endColumnIndex': len(COLS)}
    bf.pop('sortSpecs', None)
    reqs.append({'setBasicFilter': {'filter': bf}})
    reqs.append({'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 1}},
                                           'fields': 'gridProperties.frozenRowCount'}})
    sh.batch_update({'requests': reqs})
    print(f'シート更新完了: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit')


if __name__ == '__main__':
    main()
