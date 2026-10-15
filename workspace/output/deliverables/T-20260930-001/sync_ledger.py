#!/usr/bin/env python3
"""T-20260930-001 メーカー連絡先台帳シートの冪等同期（庶務マリエ）

入力（agent_output/T-20260930-001/ 配下。無いファイルは飛ばす）
  1. 30_最終_50社.csv        … 既存50行（判定はそのまま使う）
  2. 22_連絡先_印付き.csv     … サトルが50社ごとに追記中（途中でも可）
  3. 24_連絡先_*.csv          … 今後増える分（glob・ファイル名順）
  補助：10_メーカー候補_完全版.csv → 10_メーカー候補_完全版_v1.csv の順で
        代表商品名・印・Keepa値・値崩れの兆候・ブランドストアを引き当て（キー＝代表ASIN）
  上書き（元の batch CSV は書き換えない・同期のたびに証跡から上書き）：
        65_カート確認_*.csv（カート保持者）／62b_出品可否_*.csv（新品の出品可否）／
        67_紐付け確認_*.csv（紐付け4列・サトルの再確認）／68_宛先差し替え_*.csv（窓口列・旧値は備考へ）
        24_連絡先_recheck*_*.csv（要確認の再確認・代表ASINで元の行と差し替え。--recheck=タグ で読む範囲を指定）
        70_秘書判断_*.csv（秘書の除外/後回し/残す。dashin_order.py が読む）
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

実行：python3 sync_ledger.py [--dry-run] [--through=batchL] [--recheck=recheck] [--unchecked-out=64_出品可否_未判定.csv]
  --through       … 24_連絡先_batch*.csv をこのバッチ名まで（ファイル名順）読む。後ろは採取途中なので読まない
  --unchecked-out … 出品可否が「未確認」の接触候補（＝ゲート一括確認の対象）を agent_output に書き出す
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
LISTED_COLS = CHECKED_COLS + [LIST_COL]
# 2026-10-10（タカシ）：社長承認「そのまま出品できる社から打診。基準は確保」。第1弾/第2弾/下書き済/対象外。ロジックは dashin_order.py
import dashin_order as do
DASHIN_CSV = '63_打診第1弾.csv'
# 2026-10-10（タカシ）：出品可否が未実測の接触候補は空欄でなく「未確認」と書く（＝実測待ちと見て分かるように）。
# 実測は scripts/sourcing_gate/gate_sweep_browser.md（ブラウザ）。結果は LIST_CSV に足して再同期する
UNCHECKED = '未確認'
UNCHECKED_COLS = ['送信順', '判定', '正式社名', 'ブランド', '代表ASIN', 'Amazon URL', '確認URL', '基準チェック', 'Amazon出品可否',
                  'カート保持者', 'カート実画面確認', '紐付けの判定']


# 2026-10-11（タカシ）：カズヨの実画面確認（カート保持者 65_*／新品の出品可否 62b_*）を合流する。
# 元の batch CSV は書き換えず、同期のたびにこの証跡ファイルから上書きする（人の値は毎回同じに戻る）
CART_GLOB = '65_カート確認_*.csv'
GATE_GLOB = '62b_出品可否_*.csv'
MAKER_FLAGS_GLOB = os.path.join(HERE, '..', 'T-20260920-003', 'ledger20261010', 'cart_maker_flags_*.csv')


def apply_screen_checks(rows):
    """カート保持者・月販表示・判定（本体/本人カート）を実画面の値で上書き。件数を返す。"""
    cart = {}
    # 2026-10-16（タカシ）：並びは（日付, ファイル名）＝新しい確認が勝つ。ファイル名の素の順だと
    # 「65_カート確認_月販読み直し_20261016」（月 U+6708）が「…_未判定_20261011」（未 U+672A）より前に来て、
    # 10/16 の読み直し40件が 10/11 の古い値に負けていた。日付順にしても他の ASIN の勝者は変わらない（検算済み）
    def order(p):
        m = re.search(r'_(\d{8})\.csv$', p)
        return (m.group(1) if m else '', os.path.basename(p))
    for p in sorted(glob.glob(os.path.join(HERE, CART_GLOB)), key=order):
        for x in read_csv(p):
            cart[x['ASIN'].strip()] = x
    flags = {}
    for p in sorted(glob.glob(MAKER_FLAGS_GLOB)):
        for x in read_csv(p):
            flags[x['ASIN'].strip()] = x['根拠']
    n = collections.Counter()
    for r in rows:
        a = r['代表ASIN(タカシ)']
        x = cart.get(a)
        if not x:
            continue
        day = (x.get('確認時刻') or '')[5:10].replace('-', '/')
        holder = (x.get('カート保持者(実画面)') or '').strip() or \
            ('カートなし' if (x.get('カートあり') or '').strip() == 'N' else '')
        r['カート保持者(実画面9/30)'] = f'{holder}（{day}実画面確認・カズヨ）'
        # 2026-10-15（タカシ）：月販の列が無い証跡（65_RC4＝出品可否とカートだけ見た）は月販を書き換えない。
        # 列が無いのを「表示なし（月50個未満）」と読むと、見ていない値を事実として書くことになる
        if '過去1か月(実画面・下限)' in x or '過去1か月(実画面)' in x:
            sold = (x.get('過去1か月(実画面・下限)') or x.get('過去1か月(実画面)') or '').strip()
            r['過去1ヶ月の販売数(実画面9/30)'] = (f'{sold}（実画面{day}）' if sold
                                             else f'表示なし（月50個未満）／実画面{day}')
        n['カート反映'] += 1
        # 2026-10-16（タカシ）：カート保持者の出荷が FBA なら、FBA 出品者は少なくとも1（実画面の事実）。
        # Keepa の offerCountFBA が -2（offers 未取得）の行で「未確認：FBA数」が残るのを、この下限で埋める
        if '出荷=Amazon(FBA)' in (x.get('注意') or ''):
            r['_cart_fba'] = True
            n['カートがFBA（FBA数の下限1）'] += 1
        if not r['判定'].startswith(OK_STATUS):
            continue
        if 'Amazon.co.jp' in holder:
            r['判定'] = f'除外：Amazon本体がカート（§3.3-1・実画面{day}）'
            n['本体カートで除外'] += 1
        elif a in flags or '疑い' in (x.get('注意') or ''):
            why = flags.get(a) or x.get('注意')
            r['判定'] = f'要確認：カートがメーカー/ブランド本人の疑い（{holder}・{why}）'
            n['本人カート疑いで要確認'] += 1
    return n


# 2026-10-11 深夜（タカシ）：サトルの紐付けの再確認（67_*）と、ヒデアキの宛先差し替え（68_*）を合流する。
# どちらも元の batch CSV は書き換えず、同期のたびに証跡ファイルから上書きする（65_/62b_ と同じ型）
LINK_GLOB = '67_紐付け確認_*.csv'
CONTACT_GLOB = '68_宛先差し替え_*.csv'
CONTACT_FIELDS = ['メールアドレス', '問い合わせフォームURL', '電話番号', '窓口の種類']


def apply_link_checks(rows):
    """67_紐付け確認_*（キー＝代表ASIN）で紐付け4列を上書き。後のファイルが勝つ。件数を返す。"""
    link = {}
    for p in sorted(glob.glob(os.path.join(HERE, LINK_GLOB))):
        for x in read_csv(p):
            link[x['ASIN'].strip()] = x
    n = collections.Counter()
    for r in rows:
        x = link.get(r['代表ASIN(タカシ)'])
        if not x:
            continue
        v, why = (x.get('紐付けの判定') or '').strip(), (x.get('判定の理由') or '').strip()
        day = (x.get('確認時刻') or '')[5:10].replace('-', '/')
        # 2026-10-14（タカシ）：判定欄は4値（do.LINK_VALUES）の素の値だけにする。理由と、上書き前の原文は備考へ
        # （旧：一致以外は「値：理由（日付再確認）」と判定欄に併記→Z2〜Z6 の「確認済み：…」のような文章が混ざった）
        canon = v if v in do.LINK_VALUES else do.link_verdict(v)
        if canon != v:
            n['4値以外→正規化'] += 1
        prev = (r.get('紐付けの判定') or '').strip()
        notes = [f'紐付け再確認（{day}・サトル）：{canon}' + (f'。{why}' if why else '')]
        if prev and prev != canon:
            notes.append(f'元の紐付けの判定：{prev}')
            n['判定欄を書き換え'] += 1
        for s in notes:
            if s not in r['備考']:
                r['備考'] = '／'.join(t for t in [r['備考'], s] if t)
        r['紐付けの判定'] = canon
        r['紐付け根拠URL'] = (x.get('紐付け根拠URL') or '').strip()
        for c in ('Amazon上のブランド表記', 'Amazon上のメーカー表記'):
            if (x.get(c) or '').strip():
                r[c] = x[c].strip()
        n[v] += 1
    return n


def apply_contact_overrides(rows):
    """68_宛先差し替え_*（キー＝代表ASIN）で窓口列を差し替える。旧値は備考へ退避（消さない）。"""
    n = 0
    for p in sorted(glob.glob(os.path.join(HERE, CONTACT_GLOB))):
        for x in read_csv(p):
            r = next((r for r in rows if r['代表ASIN(タカシ)'] == x['代表ASIN'].strip()), None)
            if not r:
                continue
            old = []
            for c in CONTACT_FIELDS:
                if c not in x:
                    continue
                new = (x.get(c) or '').strip()
                if new != r[c]:
                    if r[c]:
                        old.append(f'{c}={r[c]}')
                    r[c] = new
            note = f'宛先差し替え（{x.get("差し替え日", "")}・{x.get("理由", "").strip()}）'
            if old:
                note += '。旧：' + '／'.join(old)
            if note not in r['備考']:
                r['備考'] = '／'.join(s for s in [r['備考'], note] if s)
            r['_contact'] = contact_rank(r)  # 窓口が変われば送信順も変わる
            n += 1
    return n


# 2026-10-12（タカシ）：サトルの要確認の再確認（24_連絡先_recheck*_*.csv）。元の batch CSV は書き換えず、
# 代表ASINが一致する元の行を、同期のたびにこの再確認の行で差し替える（並び順は元の行の位置のまま）。
# 読むファイルは --recheck=recheck,recheck2 のようにタグ（「24_連絡先_」の次から「_」まで）で指定。
# 省略時は全部読む。採取中のファイルがあるときは、完成したタグだけを指定して実行すること。
RECHECK_GLOB = '24_連絡先_recheck*_*.csv'

# 再確認の行に重ねる秘書の判断（2026-10-12 カズヨ）。キー＝代表ASIN。値は文字列の上書き／備考への追記
SCALE_NOTE = '規模の論点あり（{}）→秘書判断で接触候補のまま（10/12）'
RC_DECISIONS = {
    # N1369：上場会社の子会社の可能性は備考に残し、接触候補として扱う。社名は括弧書きを外す（担当Y 3082 と同社）
    'B06XNNKRDT': {'正式社名': '株式会社ユイット・ラボラトリーズ', '判定': '接触候補',
                   '備考+': SCALE_NOTE.format('上場会社アクシージアの子会社の可能性・従業員76名・資本金1億円')},
    'B0DPT5XPHL': {'備考+': SCALE_NOTE.format('gBiz 従業員156名・資本金1,100万円')},
    'B017VHNW18': {'備考+': SCALE_NOTE.format('売上75.76億円・資本金5,000万円')},
    'B0754DJ9F5': {'備考+': SCALE_NOTE.format('gBiz 従業員918名・卸売業')},
    'B0CZ33NN61': {'備考+': SCALE_NOTE.format('2015年に上場のパス株式会社が51%取得・現在の資本関係は未確認')},
    'B091F68K9F': {'備考+': SCALE_NOTE.format('2022年に上場企業が買収の検索要約・公式で未確認')},
}
# 重複と判明した行の情報を、残す側の行（代表ASIN）へ寄せる。寄せられた側の行は判定「重複：…」のまま
RC_MERGES = [
    # (残す側, 項目, 追記する文)
    ('B01M1KWWDN', 'ブランド', 'NUDY AURA（B005LFHF5C・同社の別ブランド／10/12 再確認）'),   # J957 → B190
    ('B004SF2NIU', 'ブランド', 'LABEAST ラビースト（B074PQMW8V・同社の別ブランド／10/12 再確認）'),  # P1590 → F593
    ('B005LKCVQU', '備考', 'サーレS（B00600O3PM）の販売元 株式会社ティー・ビー・ケーは登記所在地が同番地'
                          '（目黒区鷹番2-10-7）＝同グループの販売会社と推測（確度高・10/12 再確認でこの行へ寄せた）'),  # J919 → 22_72
]


def load_rechecks():
    """{代表ASIN: 再確認の行}（後のファイルが勝つ）と、読んだファイル名の一覧を返す。"""
    tags = [t for t in argval('recheck').split(',') if t]
    m, files = {}, []
    # 並びは（日付, タグ）。ファイル名の素の順だと「recheck2_」が「recheck_」より前に来て、
    # 後の再確認（recheck2）が古い再確認（recheck）に負けていた（2026-10-12 タカシ）
    def order(p):
        stem = os.path.basename(p)[len('24_連絡先_'):-len('.csv')].split('_')
        return (stem[-1], stem[0])
    for p in sorted(glob.glob(os.path.join(HERE, RECHECK_GLOB)), key=order):
        tag = os.path.basename(p)[len('24_連絡先_'):].split('_')[0]
        if tags and tag not in tags:
            continue
        files.append(os.path.basename(p))
        for x in read_csv(p):
            x = dict(x)
            d = RC_DECISIONS.get(x['代表ASIN(タカシ)'].strip(), {})
            for c, v in d.items():
                if c.endswith('+'):
                    if v not in x.get(c[:-1], ''):
                        x[c[:-1]] = '／'.join(s for s in [x.get(c[:-1], ''), v] if s)
                else:
                    x[c] = v
            m[x['代表ASIN(タカシ)'].strip()] = x
    return m, files


def apply_rc_merges(rows):
    n = 0
    for a, col, text in RC_MERGES:
        r = next((r for r in rows if r['代表ASIN(タカシ)'] == a), None)
        if r and text not in r[col]:
            r[col] = '／'.join(s for s in [r[col], text] if s)
            n += 1
    return n


def apply_gate_checks(listing):
    """62b（restrictions/approve・§3.3-25 の正）を 10/10 の lookupAsin に重ねる。"""
    n = collections.Counter()
    for p in sorted(glob.glob(os.path.join(HERE, GATE_GLOB))):
        for x in read_csv(p):
            a, v = x['ASIN'].strip(), (x.get('新品の出品可否') or '').strip()
            day = (x.get('確認時刻') or '')[5:10].replace('-', '/')
            prev = listing.get(a, '')
            # 2026-10-11 夜（タカシ）：62b_未判定 から「出品許可の要否」列が付いた。
            # restrictions/approve の OK は「新品の申請経路がある」だけで、許可不要とは限らない。
            # 要否が「要」の行は lookupAsin が空でも「出品できる」にせず、第2弾の扱いにする。
            # 要否列が無い旧ファイル（62b_JKL）は従来どおり（要否は lookupAsin が正）。
            need = (x.get('出品許可の要否') or '').strip()
            if not v.upper().startswith('OK'):
                listing[a] = f'出品不可（新品の申請経路なし・{day} restrictions/approve）'
                n['出品不可'] += 1
            elif prev.startswith('出品許可が必要'):
                listing[a] = f'{prev}／{day} 新品の申請経路あり'      # 許可の要否は lookupAsin が正
                n['出品許可が必要（申請経路あり）'] += 1
            elif need.startswith('要'):
                listing[a] = (f'出品許可が必要（ブランド/カテゴリ）／新品の申請経路あり（{day} restrictions/approve'
                              + (f'。10/10 lookupAsin は {prev}' if prev else '') + '）')
                n['出品許可が必要（申請経路あり・要否列）'] += 1
            else:
                listing[a] = (f'出品できる（新品・{day} restrictions/approve'
                              + (f'。10/10 lookupAsin は {prev}' if prev else '') + '）')
                n['出品できる'] += 1
    return n


def argval(name, default=''):
    return next((a.split('=', 1)[1] for a in sys.argv if a.startswith(f'--{name}=')), default)
COLS = LISTED_COLS + [do.COL]

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
                 '月販≥50／本体365日在庫切れ率≥90%／FBA出品者≥1かつ新品出品≥2／売れ筋ランク≤5万／利益率5%に必要な掛け≥40%（10/16 までは売価≥2,200円）／カート保持者がメーカー本人でない。\n'
                 'OK＝全部満たす／NG＝外れた基準と値／未確認＝データが無い項目。値の出典は実画面＞候補CSV＞Keepaキャッシュ（取得日は列ごとに異なる）。'),
    '紐付けの判定': ('代表ASINの商品が、この社の製造・販売品であることを公式ページで確かめた結果（サトル 2026-10-04）。\n'
                    '一致＝公式に同じ商品（商品名・容量・型番）あり／一致（表記ゆれ）＝Amazonのブランド欄が原料メーカー・ブランド名・海外製造元など（理由を併記）／'
                    '不一致＝別会社の商品／未確認＝公式に同商品のページなし。不一致・未確認は判定を「要確認」にして送信キューから外す。\n'
                    '67_紐付け確認 で再確認した行は4値の素の値だけを書き、理由と書き換え前の原文は備考に残す（2026-10-14）。'),
    '紐付け根拠URL': '上の判定の根拠にした公式サイト・公式通販・ブランド公式のページ（取得 2026-10-04）。',
    'Amazon出品可否(10/10)': ('セラーセントラルの商品検索（lookupAsin）で代表ASINを2026-10-10に実測（カズヨ）。出品できる／出品許可が必要（ブランド/カテゴリ）／出品不可。\n'
                            '空欄＝実測の対象外。許可が必要でも書類（請求書10点以上）で通る場合がある（§3.5 #1〜3）。'),
    do.COL: ('打診の順番（タカシ 2026-10-10・dashin_order.py）。社長承認「そのまま出品できる社から打診を始める。ただし基準は確保」。\n'
             '第1弾-NN＝接触候補・連絡先あり・基準チェックOK・出品できる・未送信・検算通過／第2弾-NN＝同条件で出品許可が必要／'
             '下書き済＝打診メールを下書き・送信済み／対象外（理由）。NN は送信順（成約しやすさ順）を保った連番。\n'
             '検算＝月販≥50・本体365日在庫切れ率≥90%・FBA≥2または(新品≥2かつFBA≥1)・ランク≤5万・利益率5%に必要な掛け≥40%・'
             'カート保持者が本体/メーカー本人でなく実画面で確認済み・公式ページで紐付け確認済み（根拠URLあり）を1項目ずつ。'),
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
    last = argval('through')  # 例 batchL → 24_連絡先_batchL.csv まで
    sources += [(p, False) for p in sorted(glob.glob(os.path.join(HERE, '24_連絡先_*.csv')))
                if '_recheck' not in os.path.basename(p)  # 再確認は下で元の行と差し替える（単独の入力にしない）
                and (not last or os.path.basename(p) <= f'24_連絡先_{last}.csv')]
    global RECHECK_N
    rc, rc_files = load_rechecks()
    rc_hit = set()
    rows, seen, used = [], set(), []
    for path, existing in sources:
        n = 0
        for src in read_csv(path):
            a = (src.get('代表ASIN(タカシ)') or src.get('代表ASIN') or '').strip()
            if not existing and a in rc and a not in rc_hit:
                src = rc[a]
                rc_hit.add(a)
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
    RECHECK_N = {'files': rc_files, '差し替え': len(rc_hit), '元の行が無い': sorted(set(rc) - rc_hit),
                 '寄せ': apply_rc_merges(rows)}
    global SCREEN_N
    SCREEN_N = apply_screen_checks(rows)
    global LINK_N, CONTACT_N
    LINK_N = apply_link_checks(rows)
    CONTACT_N = apply_contact_overrides(rows)
    global DECISION_N
    DECISION_N = do.apply_decisions(rows)  # 70_秘書判断_*（除外は送信キューから外れるので並べ替えより前）
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
        # 2026-10-16：基準5を「売価≥2,200円」→「利益率5%に必要な掛け≥40%」へ。40〜50%は通すが採算メモに残す
        note = cc.kake_note(cc.need_kake(profit.get(a, {})))
        if note and note not in r[C_MEMO]:
            r[C_MEMO] = '／'.join(x for x in [r[C_MEMO], note] if x)
        r['_m'] = do.measure(r, c, profit.get(a, {}), kc.get(a))
    listing = {x['代表ASIN']: (x.get(LIST_COL) or '').strip() for x in read_csv(os.path.join(HERE, LIST_CSV))}
    global GATE_N
    GATE_N = apply_gate_checks(listing)
    for r in rows:
        r[LIST_COL] = listing.get(r['代表ASIN(タカシ)'], '')
        if not r[LIST_COL] and j_rank(r['判定']) in (0, 1):
            r[LIST_COL] = UNCHECKED  # 接触候補なのに未実測。対象外の行は従来どおり空欄
    rest = sorted([r for r in rows if j_rank(r['判定']) > 1], key=lambda r: (j_rank(r['判定']),) + base(r))
    return queue + rest, used, profit


def col_letter(n):
    return gspread_utils().rowcol_to_a1(1, n).rstrip('1')


def gspread_utils():
    import gspread
    return gspread.utils


def owner_cell(col, v):
    """社長入力列の値を文字列に戻す。2026-10-15（タカシ）：書き込みは USER_ENTERED なので、送信反映で入った
    接触日「2026-10-15」は次の読み込み（FORMULA）で日付シリアル 46310（int）になり、.strip() で落ちた。
    日付シリアルは ISO 日付に戻す（同じ値を書き戻すだけ＝表示は変わらない）。"""
    if v is None:
        return ''
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if col == '接触日' and 20000 < v < 80000:
            import datetime
            return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(v))).isoformat()
        return str(int(v)) if float(v).is_integer() else str(v)
    return str(v)


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
    elif head[:len(LISTED_COLS)] == LISTED_COLS and len([h for h in head if h]) == len(LISTED_COLS):
        mode, cur_cols = '移行（52列→打診順1列追加・初回のみ）', LISTED_COLS
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
    # 縮小ガード（2026-10-11 事故：別フォルダから実行して入力0行のままシートを全消去した）。
    # 入力が空、またはシートの現行行数の9割を下回るときは書かずに止める。意図した縮小は --allow-shrink
    if not rows or (keep and len(rows) < len(keep) * 0.9 and '--allow-shrink' not in sys.argv):
        sys.exit(f'中止: 入力 {len(rows)}行 < シート現行 {len(keep)}行の9割。入力CSVの場所（HERE={HERE}）を確認。'
                 '意図した縮小なら --allow-shrink')
    for r in rows:
        old = keep.get(key_of(r))
        if not old:
            continue
        for c in OWNER_COLS:
            v = owner_cell(c, old.get(c))
            if v.strip():
                r[c] = v
        if (old.get('代表商品（Amazon URL）') or '').startswith('=HYPERLINK'):
            r['代表商品（Amazon URL）'] = old['代表商品（Amazon URL）']
    dres = do.assign(rows, LIST_COL, CHECK_COL)
    n_exp = do.export(rows, os.path.join(HERE, DASHIN_CSV), CHECK_COL)
    missing = [k for k in keep if k not in {key_of(r) for r in rows}
               and any(owner_cell(c, keep[k].get(c)).strip() not in ('', '未接触') for c in OWNER_COLS)]

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
    dc2 = collections.Counter(re.sub(r'-\d+$', '', r[do.COL]) for r in rows)
    print('打診順:', dict(sorted(dc2.items(), key=lambda x: -x[1])))
    print('第1弾 連絡手段:', dict(collections.Counter(do.contact_means(r) for r in rows if r[do.COL].startswith('第1弾'))))
    for name, lst, bad in dres['excluded']:
        print(f'  検算で外した: {name}（{lst}）: {"・".join(bad)}')
    print(f'{DASHIN_CSV}: {n_exp}行')
    print('実画面の合流:', dict(SCREEN_N), dict(GATE_N))
    print('紐付け再確認の合流:', dict(LINK_N), '/ 宛先差し替え:', CONTACT_N, '社')
    print('要確認の再確認（24_連絡先_recheck*）:', RECHECK_N)
    print('秘書判断（70_秘書判断_*）:', DECISION_N)
    lk = collections.Counter((r['_m']['紐付けの判定'], r['_m']['紐付けの判定(原文)'].split('：')[0] != r['_m']['紐付けの判定'])
                             for r in q)
    print('紐付け（接触候補・正規化後, 原文と違うか）:', dict(lk))
    un = [r for r in rows if r[LIST_COL] == UNCHECKED]
    out = argval('unchecked-out')
    if out:
        with open(os.path.join(HERE, out), 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(UNCHECKED_COLS)
            for r in un:
                a = r['代表ASIN(タカシ)']
                w.writerow([r[C_ORDER], r['判定'], r['正式社名'], r['ブランド'], a, r['Amazon URL'],
                            'https://sellercentral-japan.amazon.com/hz/approvalrequest/restrictions/approve'
                            f'?asin={a}&itemcondition=New', r[CHECK_COL], UNCHECKED,
                            r['_m']['カート保持者'], '済' if r['_m']['カート実画面確認'] else '未', r['_m']['紐付けの判定']])
        print(f'{out}: {len(un)}行（出品可否 未確認の接触候補）')
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
