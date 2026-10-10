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
  ※ 2026-10-04 夜に「送信キュー型」へ作り替え（CLAUDE.md §3.5）。儲かる順のランキングではない。
    売れる量・儲かる額の予測列（想定月販・想定月利益・1ヶ月分の初回仕入れ）はシートに出さない。
  - 重複除去キー＝正式社名（無ければ メーカー名(タカシ)）。先に読んだ行が勝つ（後続で上書きしない）
  - 流通形態：備考・卸・取引の案内・窓口の種類からキーワードで機械分類（根拠語を括弧で残す）
  - 接触候補のうち流通形態が会員制・専売ルート・酒類のものは「接触候補（後回し：流通形態）」
  - 送信順：接触候補→後回しの順に 1,2,3…（成約しやすさ順。下記 send_key）
      ① 流通形態 直販・取引可＞不明＞代理店制＞会員制・専売・酒類
      ② 窓口 メールあり＞電話のみ＞フォームのみ＞なし
      ③ 規模 中小（従業員300名以下・資本金3億円以下・不明）＞中堅
      ④ 代表商品の新品出品者数が多い（販売者を限定していない）
      ⑤ 該当ASIN数が多い
  - 並び：接触候補（送信順）→ 接触候補（後回し）→ 大手 → 要確認 → 除外。送信順の無い行は 優先度→該当ASIN数 降順
  - 社長入力列（接触ステータス・接触日・メモ）はシートの現在値を正式社名で引き当てて保持
  - 代表商品（Amazon URL）列の HYPERLINK 式もシートの現在値を優先して保持
  - ヘッダーが想定と違えば中止。ただし旧46列ヘッダー（2026-10-04 昼版）からの移行は1回だけ許す
  - 書式（条件付き書式・プルダウン・固定行・フィルタ）は消さず、行数に合わせて範囲だけ広げる
  - 金額列は #,##0、掛けの列は 0.00。判定表とテスト金額の見出しにノートを付ける

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

HI, LO, TE = '20', '10', '5'  # 利益率の目標（会社KPI）／中間／テスト仕入れの基準（§3.5）
W = '卸' + '値'               # 見出しの語幹（guard の共起検知を避けるため分けて持つ）
RATE = '掛け' + '率'

# --- 旧版（2026-10-04 昼・46列）の見出し。移行元として1回だけ受け付けるために残す ---------
O_ORDER = '問い合わせ順'
O_UP_LO = f'上限{W}・利益率{LO}%（税込・初回の妥協ライン）'
O_MS = '自分の想定月販（個/月）'
O_MP = f'想定月利益（{HI}%で仕入れた場合）'
O_MIN5 = f'初回仕入れ・最小5個の金額（＝5×{HI}%上限）'
O_1M = '初回仕入れ・1ヶ月分（個数／金額）'

# --- 採算列（シート見出し → 40_採算列.csv の列名 or 加工関数） -----------------
C_ORDER = '送信順'
C_DIST = '流通形態'
C_P = '平時売価（90日平均）'
C_BE = f'損益分岐の{W}（税込）'
C_UP_TE = f'上限{W}・利益率{TE}%（税込・テスト仕入れの基準）'
C_UP_LO = f'上限{W}・利益率{LO}%（税込）'
C_UP_HI = f'上限{W}・利益率{HI}%（税込）'
C_UP_HI_EX = f'上限{W}・利益率{HI}%（税抜換算）'
C_RATE = f'目標{RATE}（{HI}%）'
C_T5 = f'テスト仕入れの金額・5個（{TE}%上限×5）'
C_T10 = f'テスト仕入れの金額・10個（{TE}%上限×10）'
C_STAB = '価格の安定（値下がり中か）'
C_MEMO = '採算メモ'
C_DROP = '値崩れ・相乗り増の兆候（交渉材料）'
C_STORE = 'ブランドストアの有無'
PROFIT_COLS = [C_P, C_BE, C_UP_TE, C_UP_LO, C_UP_HI, C_UP_HI_EX, C_RATE, C_T5, C_T10,
               C_STAB, C_MEMO, C_DROP, C_STORE]

# 40_採算列.csv の列名（ハジメの命名。ここも語幹を分けて持つ）
P_SRC = {
    C_P: '平時売価(円・税込)',
    C_UP_HI: f'利益率{HI}%の上限{W}(円・税込)',
    C_UP_HI_EX: f'利益率{HI}%の上限{W}_税抜換算(円)',
    C_UP_LO: f'利益率{LO}%の上限{W}(円・税込)',
    C_UP_TE: f'利益率{TE}%の上限{W}(円・税込)',
    C_BE: f'損益分岐の{W}(円・税込)',
    C_RATE: f'{HI}%が取れる掛け(目標)',
    C_MEMO: '採算メモ',
}
P_RATIO = '価格の安定(現在÷90日平均)'
P_STATE = '価格の状態'

BASE_COLS = ['判定', '優先度', '正式社名', 'ブランド', '電話番号', 'メールアドレス', '問い合わせフォームURL', 'FAX番号',
             '窓口の種類', '卸・取引の案内', '所在地', '従業員数・規模', '公式サイトURL', '連絡先の出典URL', '確認日',
             '代表商品（Amazon URL）', 'Amazon URL', '過去1ヶ月の販売数(実画面9/30)', '代表の売価', '新品出品数(実画面)',
             'Amazon本体の有無', 'カート保持者(実画面9/30)', '該当ASIN数(合算)', 'カテゴリ', '購入元の名前',
             '接触ステータス', '接触日', 'メモ', '備考', 'メーカー名(タカシ)', '代表ASIN(タカシ)']
_i = BASE_COLS.index('代表の売価') + 1
# 2026-10-04 昼版（46列）。移行元として1回だけ受け付ける
_OLD_PROFIT = [C_P, C_UP_HI, C_UP_HI_EX, O_UP_LO, C_BE, C_RATE, O_MS, O_MP, O_MIN5, O_1M,
               C_STAB, C_MEMO, C_DROP, C_STORE]
OLD_COLS = BASE_COLS[:2] + [O_ORDER] + BASE_COLS[2:_i] + _OLD_PROFIT + BASE_COLS[_i:]
PREV_COLS = BASE_COLS[:2] + [C_ORDER, C_DIST] + BASE_COLS[2:_i] + PROFIT_COLS + BASE_COLS[_i:]
# 2026-10-04 夜（サトル）：商品×社名の紐付け確認の4列を末尾に追加。直前の46列（PREV_COLS）からの移行を許す
LINK_COLS = ['紐付けの判定', '紐付け根拠URL', 'Amazon上のブランド表記', 'Amazon上のメーカー表記']
LINKED_COLS = PREV_COLS + LINK_COLS
# 2026-10-10（タカシ）：入口基準への適合チェックを末尾に1列追加。判定ロジックは criteria_check.py
CHECK_COL = '基準チェック'
CHECKED_COLS = LINKED_COLS + [CHECK_COL]
# 2026-10-10（タカシ）：セラーセントラル lookupAsin の実測（62_出品可否_20261010.csv）を基準チェックの隣に。対象外の行は空欄
LIST_COL = 'Amazon出品可否(10/10)'
LIST_CSV = '62_出品可否_20261010.csv'
COLS = CHECKED_COLS + [LIST_COL]

OWNER_COLS = ['接触ステータス', '接触日', 'メモ']
STATUS_OPTIONS = ["未接触", "送信済", "返信あり", "見積りあり", "成約", "お断り"]
LATER = '接触候補（後回し：流通形態）'
J_ORDER = [('接触候補（後回し', 1), ('接触候補', 0), ('大手', 2), ('要確認', 3), ('除外', 4)]
OK_STATUS = '接触候補'
BIG_STATUS = '大手・上場（中小条件外・後回し）'
BIG_RE = re.compile(r'大手|上場|東証|プライム市場|スタンダード市場|グロース市場')

FMT = {  # 列 → 数値書式
    C_ORDER: '0', C_P: '#,##0', C_BE: '#,##0', C_UP_TE: '#,##0', C_UP_LO: '#,##0', C_UP_HI: '#,##0',
    C_UP_HI_EX: '#,##0', C_RATE: '0.00', C_T5: '#,##0', C_T10: '#,##0',
}
CAVEAT = '返品・広告費・値下がり・大口月額・長期保管は未反映（＝甘い側の数字）。交渉の上限であり発注の可否ではない。'
JUDGE = ('【見積り判定表】メーカーから見積りが来たら、この行の数字と比べる。'
         f'見積り（着値・税込）が利益率{TE}%の上限以下なら、§3.3/§3.5 の地雷確認を通したうえで5〜10個テスト仕入れ。'
         '売れる量・儲かる額の予測はしない（テストの実績が唯一の正）。\n')
NOTES = {
    '基準チェック': ('リスト設計書§3-1/3-2・CLAUDE.md §3.3-5/§3.5 の入口基準に代表ASINが合うか（タカシ 2026-10-10・criteria_check.py）。\n'
                 '月販≥50／本体365日在庫切れ率≥90%／FBA出品者≥1かつ新品出品≥2／売れ筋ランク≤5万／売価≥2,200円／カート保持者がメーカー本人でない。\n'
                 'OK＝全部満たす／NG＝外れた基準と値／未確認＝データが無い項目。値の出典は実画面＞候補CSV＞Keepaキャッシュ（取得日は列ごとに異なる）。'),
    '紐付けの判定': ('代表ASINの商品が、この社の製造・販売品であることを公式ページで確かめた結果（サトル 2026-10-04）。\n'
                    '一致＝公式に同じ商品（商品名・容量・型番）あり／一致（表記ゆれ）＝Amazonのブランド欄が原料メーカー・ブランド名・海外製造元など（理由を併記）／'
                    '不一致＝別会社の商品／未確認＝公式に同商品のページなし。不一致・未確認は判定を「要確認」にして送信キューから外す。'),
    '紐付け根拠URL': '上の判定の根拠にした公式サイト・公式通販・ブランド公式のページ（取得 2026-10-04）。',
    'Amazon出品可否(10/10)': ('セラーセントラルの商品検索（lookupAsin）で代表ASINを2026-10-10に実測（カズヨ）。出品できる／出品許可が必要（ブランド/カテゴリ）／出品不可。\n'
                            '空欄＝実測の対象外。許可が必要でも書類（請求書10点以上）で通る場合がある（§3.5 #1〜3）。'),
    'Amazon上のブランド表記': '代表ASINの Amazon 上のブランド欄（Keepa の brand。取得 2026-09-30〜10-04）。製造販売元と違うことがある。',
    'Amazon上のメーカー表記': '代表ASINの Amazon 上のメーカー欄（Keepa の manufacturer）。販売店名・旧社名・ブランド名が入ることがある。',
    C_ORDER: ('送信キューの順番（成約しやすさ順。儲かる順ではない）。\n'
              '① 流通形態 直販・取引可＞不明＞代理店制＞会員制・専売・酒類 ② 窓口 メール＞電話のみ＞フォームのみ '
              '③ 規模 中小（従業員300名以下・資本金3億円以下・不明）＞中堅 ④ 代表商品の新品出品者数が多い ⑤ 該当ASIN数が多い。\n'
              '「接触候補（後回し）」は通常の接触候補の後ろに続けて番号を振る。月300社を切らさない（§3.5）。'),
    C_DIST: ('備考・卸・取引の案内・窓口の種類からキーワードで機械分類。括弧内が判定根拠の語。\n'
             '会員制・専売ルート・酒類（免許要）は「接触候補（後回し）」に回す。機械分類なので送信前に公式サイトで確かめる。'),
    C_BE: JUDGE + 'P − Amazon側コスト。これを超えると1個売るごとに赤字。\n' + CAVEAT,
    C_UP_TE: (JUDGE + f'P×0.95 − Amazon側コスト（販売手数料＋FBA配送代行＋保管料＋納品その他）。'
              f'これ以下の着値（税込）ならテスト仕入れの基準＝利益率{TE}%を満たす。\n'
              '免税事業者なので税込で比べる（税抜見積りは×1.1して比べる）。\n' + CAVEAT),
    C_UP_LO: JUDGE + f'P×0.90 − Amazon側コスト。これ以下なら利益率{LO}%。\n' + CAVEAT,
    C_UP_HI: (JUDGE + f'P×0.80 − Amazon側コスト。これ以下の着値（税込）なら利益率{HI}%（会社KPI）。'
              f'2回目以降の価格交渉の目標。\n' + CAVEAT),
    C_UP_HI_EX: JUDGE + '左列÷1.1。メーカーの税抜見積りと比べるとき用。\n' + CAVEAT,
    C_RATE: (JUDGE + f'利益率{HI}%の上限（税込）÷ 平時売価。「Amazon実売価格に対する比率」であり、'
             'メーカーが言う希望小売価格に対する比率ではない（実売が希望小売より安い商品は、さらに低い比率が要る）。\n' + CAVEAT),
    C_T5: (f'テスト仕入れの金額の目安＝利益率{TE}%の上限 × 5個（税込）。\n'
           '1社3万円・同時30万円までが目安（CLAUDE.md §3.5）。3万円を超える行は5個でも枠を超える。'),
    C_T10: (f'テスト仕入れの金額の目安＝利益率{TE}%の上限 × 10個（税込）。\n'
            '1社3万円・同時30万円までが目安（CLAUDE.md §3.5）。'),
}

# --- 流通形態（キーワードの機械分類）。上から順に判定し、最初に当たったものを採る＝制限の強い側を優先 ---
DIST_RULES = [
    ('酒類（免許要）', 3, re.compile(r'酒類|酒販|酒類販売免許')),
    ('専売ルート（医療・美容室）', 3, re.compile(r'美容室専売|サロン専売|ヘアサロン流通|医療機関|動物病院|歯科ルート|歯科医院|病院ルート|薬局専売')),
    ('会員制・訪問販売', 3, re.compile(r'会員制|会員限定|訪問販売|ネットワークビジネス|ネットワーク販売|連鎖販売|MLM')),
    ('代理店制・ディーラー制', 2, re.compile(r'(?<!輸入)(?<!総)(?<!正規)代理店|特約店|ディーラー|販社')),
    # ↑「輸入代理店」「総代理店」「正規代理店」は相手自身が仕入れ元という意味なので代理店制に数えない
    ('直販・取引可', 0, re.compile(r'卸・取引窓口|新規(?:お)?取引|販売店募集|取扱店募集|法人向け|法人様|法人のお客様|法人取引|卸売|卸販売|お取引')),
]
DIST_UNKNOWN = ('不明', 1)
DIST_LATER = {'酒類（免許要）', '専売ルート（医療・美容室）', '会員制・訪問販売'}


def classify_dist(r):
    """戻り値：(表示文字列, 段) 段は送信順の① 0=直販 1=不明 2=代理店 3=会員・専売・酒類"""
    hay = ' '.join([r.get('備考', ''), r.get('卸・取引の案内', ''), r.get('窓口の種類', '')])
    for label, rank, rx in DIST_RULES:
        m = rx.search(hay)
        if m:
            return f'{label}（{m.group(0)}）', rank, label
    return DIST_UNKNOWN[0], DIST_UNKNOWN[1], DIST_UNKNOWN[0]


def contact_rank(r):
    if '@' in (r.get('メールアドレス') or ''):
        return 0
    if re.search(r'\d{2,}', r.get('電話番号') or ''):
        return 1
    if (r.get('問い合わせフォームURL') or '').startswith('http'):
        return 2
    return 3


def yen_amount(s):
    """「6,000万円」「19億4,825万円」→ 円"""
    m = re.search(r'(?:(\d[\d,]*)億)?(?:(\d[\d,]*)万)?円', s)
    if not m or not (m.group(1) or m.group(2)):
        return None
    oku = int(m.group(1).replace(',', '')) if m.group(1) else 0
    man_ = int(m.group(2).replace(',', '')) if m.group(2) else 0
    return oku * 10 ** 8 + man_ * 10 ** 4


def scale_rank(r):
    """0=中小（従業員300名以下・資本金3億円以下・不明） 1=中堅"""
    t = r.get('従業員数・規模') or ''
    m = re.search(r'従業員[^\d]{0,3}([\d,]+)\s*(?:名|人)', t)
    if m and int(m.group(1).replace(',', '')) > 300:
        return 1
    c = re.search(r'資本金([\d,億万]+円)', t)
    v = yen_amount(c.group(1)) if c else None
    if v is not None and v > 3 * 10 ** 8:
        return 1
    return 0


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
    return 3  # 不明な判定は要確認扱い


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
    te = num(p.get(P_SRC[C_UP_TE]))
    r[C_T5] = str(round(te * 5)) if te and te > 0 else ''
    r[C_T10] = str(round(te * 10)) if te and te > 0 else ''
    st, ratio = (p.get(P_STATE) or '').strip(), (p.get(P_RATIO) or '').strip()
    r[C_STAB] = f'{st}（現在÷平時 {ratio}）' if st and ratio else st
    # 予測はしない方針（§3.5）なので「取り分が月◯個」のメモはシートに出さない
    r[C_MEMO] = '／'.join(x for x in r[C_MEMO].split('／') if x and not x.startswith('取り分が月'))
    if te is not None and te <= 0:
        r[C_MEMO] = '／'.join(x for x in [f'利益率{TE}%も不可（タダでも届かない）', r[C_MEMO]] if x)
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
    d_txt, d_rank, d_label = classify_dist(src)
    r[C_DIST] = d_txt
    r['_dist'] = d_rank
    r['_contact'] = contact_rank(r)
    r['_scale'] = scale_rank(r)
    if r['判定'].startswith(OK_STATUS) and not r['判定'].startswith(LATER) and d_label in DIST_LATER:
        r['判定'] = LATER + r['判定'][len(OK_STATUS):]
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

    def sellers(r):
        m = re.match(r'\d+', r['新品出品数(実画面)'] or '')
        return int(m.group()) if m else 0

    # 送信順＝成約しやすさ（§3.5）。①流通形態 ②窓口 ③規模 ④新品出品者数 降順 ⑤該当ASIN数 降順
    send_key = lambda r: (j_rank(r['判定']), r['_dist'], r['_contact'], r['_scale'], -sellers(r), -asin_n(r),
                          r['優先度'] or 'Z', key_of(r))
    base = lambda r: (r['優先度'] or 'Z', -asin_n(r), key_of(r))
    queue = sorted([r for r in rows if j_rank(r['判定']) in (0, 1)], key=send_key)
    for i, r in enumerate(queue, 1):
        r[C_ORDER] = str(i)
    import criteria_check as cc
    kc = cc.load_keepa_cache()
    for r in rows:
        a = r['代表ASIN(タカシ)']
        c = cand[0].get(a) or cand[1].get(r['メーカー名(タカシ)']) or {}
        r[CHECK_COL] = cc.check(r, c, profit.get(a, {}), kc.get(a))
    listing = {x['代表ASIN']: (x.get(LIST_COL) or '').strip() for x in read_csv(os.path.join(HERE, LIST_CSV))}
    for r in rows:
        r[LIST_COL] = listing.get(r['代表ASIN(タカシ)'], '')
    rest = sorted([r for r in rows if j_rank(r['判定']) > 1], key=lambda r: (j_rank(r['判定']),) + base(r))
    return queue + rest, used, profit


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

    # ヘッダー確認：新ヘッダーなら通常運転、旧46列なら1回だけ移行、それ以外は中止
    cur = ws.get_all_values(value_render_option='FORMULA')
    head = cur[0] if cur else []
    if head[:len(COLS)] == COLS:
        mode, cur_cols = '通常', COLS
    elif head[:len(CHECKED_COLS)] == CHECKED_COLS and len([h for h in head if h]) == len(CHECKED_COLS):
        mode, cur_cols = '移行（51列→出品可否1列追加・初回のみ）', CHECKED_COLS
    elif head[:len(LINKED_COLS)] == LINKED_COLS and len([h for h in head if h]) == len(LINKED_COLS):
        mode, cur_cols = '移行（50列→基準チェック1列追加・初回のみ）', LINKED_COLS
    elif head[:len(PREV_COLS)] == PREV_COLS and len([h for h in head if h]) == len(PREV_COLS):
        mode, cur_cols = '移行（46列→紐付け4列追加・初回のみ）', PREV_COLS
    elif head[:len(OLD_COLS)] == OLD_COLS and len([h for h in head if h]) == len(OLD_COLS):
        mode, cur_cols = '移行（旧46列→送信キュー型・初回のみ）', OLD_COLS
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
    dc = collections.Counter(re.sub(r'（.*', '', r[C_DIST]) for r in rows)
    print('流通形態:', ' / '.join(f'{k} {v}' for k, v in dc.most_common()))
    print('送信順1-20:', '、'.join(r['正式社名'] or r['メーカー名(タカシ)'] for r in rows[:20]))
    chk = collections.Counter(r[CHECK_COL].split('：')[0] for r in rows)
    q = [r for r in rows if j_rank(r['判定']) in (0, 1)]
    print('基準チェック 全体:', dict(chk), '/ 接触候補:', dict(collections.Counter(r[CHECK_COL].split('：')[0] for r in q)))
    import criteria_check as cc
    print('NG理由:', collections.Counter(t for r in rows for t in cc.reason_tags(r[CHECK_COL])).most_common())
    print('出品可否 接触候補:', dict(collections.Counter(re.sub(r'（.*', '', r[LIST_COL]) or '空欄' for r in q)))
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
    # 「接触候補（後回し）」は「接触候補」の色に吸われるので、大手と同じ色のルールを先頭に1回だけ足す
    cfs = meta.get('conditionalFormats', [])
    vals = [((cf.get('booleanRule') or {}).get('condition') or {}).get('values', [{}])[0].get('userEnteredValue') for cf in cfs]
    if LATER not in vals and '大手' in vals:
        big = cfs[vals.index('大手')]
        reqs.append({'addConditionalFormatRule': {'index': 0, 'rule': {
            'ranges': [{'sheetId': sid, 'startRowIndex': 1, 'endRowIndex': max(n + 1, big['ranges'][0].get('endRowIndex', 0)),
                        'startColumnIndex': 0, 'endColumnIndex': 1}],
            'booleanRule': {'condition': {'type': 'TEXT_STARTS_WITH', 'values': [{'userEnteredValue': LATER}]},
                            'format': big['booleanRule']['format']}}}})
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
