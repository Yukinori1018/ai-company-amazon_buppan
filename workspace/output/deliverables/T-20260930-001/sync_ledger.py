#!/usr/bin/env python3
"""T-20260930-001 メーカー連絡先台帳シートの冪等同期（庶務マリエ）

入力（agent_output/T-20260930-001/ 配下。無いファイルは飛ばす）
  1. 30_最終_50社.csv        … 既存50行（判定はそのまま使う）
  2. 22_連絡先_印付き.csv     … サトルが50社ごとに追記中（途中でも可）
  3. 24_連絡先_*.csv          … 今後増える分（glob・ファイル名順）
  補助：10_メーカー候補_完全版.csv … 代表商品名・印・Keepa値の引き当て用

出力：Googleシート 1FyKBUHG4sRQG6lgV0mXDpotWUWIvG6zt00YaCoinvPI／タブ「メーカー連絡先」（31列）を全置換。
  - 重複除去キー＝正式社名（無ければ メーカー名(タカシ)）。先に読んだ行が勝つ（後続で上書きしない）
  - 並び：判定（接触候補→大手→要確認→除外）→優先度→該当ASIN数 降順
  - 社長入力列（接触ステータス・接触日・メモ）はシートの現在値を正式社名で引き当てて保持
  - 代表商品（Amazon URL）列の HYPERLINK 式もシートの現在値を優先して保持
  - 書式（条件付き書式・プルダウン・固定行・フィルタ）は消さず、行数に合わせて範囲だけ広げる

実行：python3 sync_ledger.py [--dry-run]
"""
import csv, glob, os, re, sys, collections

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET_ID = "1FyKBUHG4sRQG6lgV0mXDpotWUWIvG6zt00YaCoinvPI"
TAB = "メーカー連絡先"
CRED = os.path.expanduser("~/.config/claude-session-sheets/credentials.json")

COLS = ['判定', '優先度', '正式社名', 'ブランド', '電話番号', 'メールアドレス', '問い合わせフォームURL', 'FAX番号',
        '窓口の種類', '卸・取引の案内', '所在地', '従業員数・規模', '公式サイトURL', '連絡先の出典URL', '確認日',
        '代表商品（Amazon URL）', 'Amazon URL', '過去1ヶ月の販売数(実画面9/30)', '代表の売価', '新品出品数(実画面)',
        'Amazon本体の有無', 'カート保持者(実画面9/30)', '該当ASIN数(合算)', 'カテゴリ', '購入元の名前',
        '接触ステータス', '接触日', 'メモ', '備考', 'メーカー名(タカシ)', '代表ASIN(タカシ)']
OWNER_COLS = ['接触ステータス', '接触日', 'メモ']
STATUS_OPTIONS = ["未接触", "送信済", "返信あり", "見積りあり", "成約", "お断り"]
J_ORDER = [('接触候補', 0), ('大手', 1), ('要確認', 2), ('除外', 3)]
OK_STATUS = '接触候補'
BIG_STATUS = '大手・上場（中小条件外・後回し）'
BIG_RE = re.compile(r'大手|上場|東証|プライム市場|スタンダード市場|グロース市場')


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
    for r in read_csv(os.path.join(HERE, '10_メーカー候補_完全版.csv')):
        by_asin.setdefault(r.get('代表ASIN', ''), r)
        by_name.setdefault(r.get('メーカー名', ''), r)
    return by_asin, by_name


def to_row(src, is_existing, cand):
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
    return r


def collect():
    cand = load_candidates()
    sources = [(os.path.join(HERE, '30_最終_50社.csv'), True),
               (os.path.join(HERE, '22_連絡先_印付き.csv'), False)]
    sources += [(p, False) for p in sorted(glob.glob(os.path.join(HERE, '24_連絡先_*.csv')))]
    rows, seen, used = [], set(), []
    for path, existing in sources:
        n = 0
        for src in read_csv(path):
            r = to_row(src, existing, cand)
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
    rows.sort(key=lambda r: (j_rank(r['判定']), r['優先度'] or 'Z', -asin_n(r)))
    return rows, used


def main():
    dry = '--dry-run' in sys.argv
    rows, used = collect()
    import warnings; warnings.filterwarnings('ignore')
    import gspread
    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB)

    # 社長入力列・既存ハイパーリンク式を保持
    cur = ws.get_all_values(value_render_option='FORMULA')
    if cur and cur[0][:len(COLS)] != COLS:
        sys.exit(f'ヘッダーが想定と異なるため中止しました: {cur[0]}')
    keep = {}
    for line in cur[1:]:
        d = dict(zip(COLS, line + [''] * (len(COLS) - len(line))))
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
    print('入力:', ', '.join(f'{f}={c}行' for f, c in used))
    print(f'総行数: {n}')
    for j, c in sorted(counts.items(), key=lambda x: (j_rank(x[0]), -x[1])):
        print(f'  {c:>4}  {j}')
    if missing:
        print('注意: 入力から消えたが社長入力があった行（シートからは落ちます）:', missing)
    if dry:
        print('(dry-run: シートは更新していません)')
        return

    need_rows = max(n + 1 + 20, ws.row_count)
    if need_rows > ws.row_count:
        ws.resize(rows=need_rows)
    last_col = gspread.utils.rowcol_to_a1(1, len(COLS)).rstrip('1')
    ws.batch_clear([f'A2:{last_col}{ws.row_count}'])
    ws.update(values=[[r[c] for c in COLS] for r in rows], range_name=f'A2:{last_col}{n + 1}',
              value_input_option='USER_ENTERED')

    # 書式の範囲を行数に追従させる（条件付き書式・プルダウン・フィルタ）
    sid = ws.id
    md = sh.fetch_sheet_metadata(params={'fields': 'sheets(properties(sheetId),conditionalFormats,basicFilter)'})
    meta = next(s for s in md['sheets'] if s['properties']['sheetId'] == sid)
    reqs = []
    for i, cf in enumerate(meta.get('conditionalFormats', [])):
        for rg in cf['ranges']:
            rg['endRowIndex'] = max(rg.get('endRowIndex', 0), n + 1)
        reqs.append({'updateConditionalFormatRule': {'index': i, 'sheetId': sid, 'rule': cf}})
    zc = COLS.index('接触ステータス')
    reqs.append({'setDataValidation': {
        'range': {'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': n + 1, 'startColumnIndex': zc, 'endColumnIndex': zc + 1},
        'rule': {'condition': {'type': 'ONE_OF_LIST', 'values': [{'userEnteredValue': v} for v in STATUS_OPTIONS]},
                 'strict': True, 'showCustomUi': True}}})
    if meta.get('basicFilter'):
        bf = meta['basicFilter']
        bf['range'] = {'sheetId': sid, 'startRowIndex': 0, 'endRowIndex': n + 1, 'startColumnIndex': 0, 'endColumnIndex': len(COLS)}
        reqs.append({'setBasicFilter': {'filter': bf}})
    reqs.append({'updateSheetProperties': {'properties': {'sheetId': sid, 'gridProperties': {'frozenRowCount': 1}},
                                           'fields': 'gridProperties.frozenRowCount'}})
    sh.batch_update({'requests': reqs})
    print(f'シート更新完了: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit')


if __name__ == '__main__':
    main()
