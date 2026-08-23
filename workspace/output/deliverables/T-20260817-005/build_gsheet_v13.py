"""T-20260817-005 / v1.3 候補100件を「メーカー仕入れ台帳」へ【新規タブとして非破壊追記】。

既存タブ（⭐月販実測あり(60商品) / ⭐︎売れ筋商品 / 連絡先取得済(優先) / サマリ・前提 / メーカー台帳）は
一切触らない。追加タブは PREFIX="v13_" の2枚のみ。

  1. v13_候補100件      … top100 CSV + No列 + リスク区分列（ヘッダー太字＋固定）
  2. v13_サマリ・前提   … 抽出条件・実績・前提（推測）・正直な注意

実行: python3 build_gsheet_v13.py
"""
import csv
import re
import time
from pathlib import Path

import gspread

CRED = "/Users/yukinori/.config/claude-session-sheets/credentials.json"
SHEET_ID = "1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4"
OUT = Path(__file__).resolve().parent
CSV_PATH = OUT / "candidates_v13_top100.csv"
URL_OUT = OUT / "sheet_url_v13.txt"

PREFIX = "v13_"
TAB_LIST = PREFIX + "候補100件"
TAB_INFO = PREFIX + "サマリ・前提"

# 既存タブ保護: PREFIX で始まらないタブは絶対に削除しない
PROTECTED_HINT = "既存タブの削除は禁止（非破壊追記のみ）"

# --- リスク区分の機械判定 -------------------------------------------------
# リチウム/PSE: 電池・電源・充電まわり（PSE / FBA危険物 / ODR の三重リスク）
LI_PSE_PAT = re.compile(
    "|".join([
        "モバイルバッテリー", "ポータブル電源", "充電器", "チャージャー", "チャージャ",
        "ACアダプタ", "ACアダプター", "電源タップ", "電源", "バッテリー", "リチウム",
        "急速充電", "充電ステーション", "充電スタンド", "蓄電",
        r"[Cc]harger", r"[Bb]attery", r"[Pp]ower ?[Bb]ank", r"[Pp]owerbank",
    ])
)
KADEN_PREFIX = "家電＆カメラ"


def risk_class(name: str, category: str) -> str:
    blob = f"{name} {category}"
    if LI_PSE_PAT.search(blob):
        return "リチウム/PSE"
    if category.startswith(KADEN_PREFIX):
        return "要確認"
    return ""


# --- シート操作 -----------------------------------------------------------
def fresh_tab(sh, title, rows, cols):
    """同名タブがあれば作り直す。PREFIX 以外のタブには絶対に触らない。"""
    assert title.startswith(PREFIX), f"{PROTECTED_HINT}: {title}"
    existing = {w.title: w for w in sh.worksheets()}
    if title in existing:
        sh.del_worksheet(existing[title])
    return sh.add_worksheet(title=title, rows=max(rows, 10), cols=max(cols, 2))


def write_block(sh, title, a1, values):
    for attempt in range(4):
        try:
            sh.values_update(
                f"'{title}'!{a1}",
                params={"valueInputOption": "RAW"},
                body={"values": values},
            )
            return
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"  retry {title}@{a1}: {type(e).__name__}", flush=True)
            time.sleep(5 * (attempt + 1))


def chunked(sh, title, header, data_rows, chunk=1200):
    ws = fresh_tab(sh, title, len(data_rows) + 5, len(header))
    write_block(sh, title, "A1", [header])
    start = 2
    for i in range(0, len(data_rows), chunk):
        block = data_rows[i:i + chunk]
        write_block(sh, title, f"A{start}", block)
        start += len(block)
        print(f"  {title}: {start - 2}/{len(data_rows)}行", flush=True)
        time.sleep(1)
    return ws


def main():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        src_cols = list(reader.fieldnames)
        rows = list(reader)

    # 列構成: No + 元CSV27列 + リスク区分（カテゴリの直後に置くと見やすいので末尾ではなく前方へ）
    header = ["No", "リスク区分"] + src_cols
    data = []
    counts = {"リチウム/PSE": 0, "要確認": 0, "": 0}
    for i, r in enumerate(rows, start=1):
        rc = risk_class(r.get("商品名", ""), r.get("カテゴリ", ""))
        counts[rc] += 1
        data.append([i, rc] + [r.get(c, "") for c in src_cols])

    gc = gspread.service_account(filename=CRED)
    sh = gc.open_by_key(SHEET_ID)
    before = [w.title for w in sh.worksheets()]
    print("opened:", sh.title, flush=True)
    print("既存タブ(保護):", before, flush=True)

    # --- 1) 候補100件 ---
    ws = chunked(sh, TAB_LIST, header, data)
    ws.freeze(rows=1)
    ws.format("A1:AC1", {"textFormat": {"bold": True}})
    print(f"wrote {TAB_LIST}: {len(data)}件 / リスク区分 {counts}", flush=True)

    # --- 2) サマリ・前提 ---
    li = counts["リチウム/PSE"]
    kaku = counts["要確認"]
    info = [
        ["メーカー仕入れ v1.3 候補100件（T-20260817-005）", ""],
        ["作成日", "2026-08-23"],
        ["実行者", "タカシ(IT・Keepa実走) ＋ マリエ(庶務・整形/シート化)"],
        ["元チケット", "T-20260817-005（status=doing。タスク3・4は未着手）"],
        ["", ""],
        ["■ 抽出条件（v1.3・社長裁可 2026-08-17）", ""],
        ["抽出軸", "Keepa 月間ドロップ数（ランク上限は30万位まで開放し足切りに使わない）"],
        ["価格帯A", "1,500〜8,000円 × 月間ドロップ10以上"],
        ["価格帯B", "8,000〜20,000円 × 月間ドロップ4以上"],
        ["出品者数", "2〜6"],
        ["Amazon本体", "不在（Amazon本体が出品している商品は除外）"],
        ["レビュー数", "5〜300（＝あまり有名でない、の代理指標）"],
        ["バリエーション", "1〜3"],
        ["サイズ", "FBA標準サイズ以内（45x35x20cm かつ 9kg 以内。大型は除外）"],
        ["追跡期間", "Keepa 追跡開始から180日以上"],
        ["除外カテゴリ", "ドラッグストア／ビューティー／食品／アダルト の4つ"],
        ["段1 回転", "想定月販＝ドロップ数÷(出品者数+1)。消化月数3ヶ月以内＝GO"],
        ["段2 値下げ耐性", "過去1年最安売価×0.65−外注費＝損益分岐仕入れ値（メーカーへの提示上限）"],
        ["段3 出品制限", "加点扱い（制限なし縛りは撤廃）。機械判定できないため本表では空欄"],
        ["", ""],
        ["■ 実績（2026-08-21 実走）", ""],
        ["Finder該当", "A 7,933件 ／ B 4,095件"],
        ["詳細取得", "3,702件（CSV 4,002行）"],
        ["GO判定", "2,479件（62%）"],
        ["本タブ", "GO を消化月数の昇順に並べた上位100件（消化月数 0.62〜0.94ヶ月）"],
        ["Keepa消費", "約3,821トークン ／ 所要 2時間34分"],
        ["", ""],
        ["■ 見送り内訳（4,002行のうち）", ""],
        ["FBA大型サイズ", 849],
        ["回転不足（消化月数>3）", 800],
        ["最安値で黒字化不能", 91],
        ["出品者数が範囲外", 47],
        ["Amazon本体あり", 13],
        ["除外カテゴリ", 9],
        ["ランク圏外", 1],
        ["", ""],
        ["■ 前提（推測・要社長確認）", ""],
        ["初回ロット", "10個で消化月数を計算（5個版は『消化月数_ロット5』列に併記）"],
        ["外注費", "ラベル22円＋梱包10円＋納品送料150〜300円＝サイズ別 182／282／332円"],
        ["過去1年最安値", "Keepa 新品最安（NEW, index=1）の365日最小値"],
        ["", ""],
        ["■ 正直な注意（そのまま読んでください）", ""],
        ["①「仕入れられる」は未確認",
         "「売れている」は実測です。ただしメーカーが個人事業主に卸すか・最低ロット・掛け率は問い合わせないと分かりません。"],
        ["② 実質のふるいは段1とFBAサイズ",
         "段2（値下げ耐性）は4,002行中91件しか落としていません。ふるいとしてはほぼ効いていません。"],
        ["③ 掛け率40%未満は買えない可能性大",
         "『仕入れ掛け率上限%』が40%未満の商品は、条件を満たしていても現実の卸値では買えない見込み（top100中16件）。人の目で切ってください。"],
        ["④ 段3（出品制限）は空欄",
         "機械判定できません。発注前にワンクリック解除テスト＋請求書記載の事前確約が必須です。"],
        ["⑤ リスク区分について",
         f"商品名・カテゴリのキーワードによる機械判定です。リチウム/PSE {li}件・要確認 {kaku}件。"
         "『要確認』は家電＆カメラ配下のみを対象にしています（ホーム＆キッチン>家電 は対象外＝空欄）。最終判断は人の目で。"],
        ["", ""],
        ["■ 承認ルール", ""],
        ["§4.1 該当", "実購入・メーカーへの実連絡は社長承認が必須です。このシートは候補の可視化までで、連絡・発注は一切していません。"],
        ["", ""],
        ["■ 元データ（リポジトリ内・Git追跡対象）", ""],
        ["候補100件CSV", "workspace/output/deliverables/T-20260817-005/candidates_v13_top100.csv"],
        ["全件CSV（4,002行・見送り理由つき）", "workspace/output/deliverables/T-20260817-005/candidates_v13.csv"],
        ["実行サマリ", "workspace/output/deliverables/T-20260817-005/summary.json"],
        ["Finder条件", "workspace/output/deliverables/T-20260817-005/finder_selections.json"],
        ["スキャナ", "workspace/output/deliverables/T-20260817-005/scan_v13.py（--from-raw で再集計はトークン消費ゼロ）"],
        ["本シート生成スクリプト", "workspace/output/deliverables/T-20260817-005/build_gsheet_v13.py"],
        ["README", "workspace/output/deliverables/T-20260817-005/README.md"],
    ]
    ws2 = fresh_tab(sh, TAB_INFO, len(info) + 3, 2)
    write_block(sh, TAB_INFO, "A1", info)
    ws2.format("A1:B1", {"textFormat": {"bold": True}})
    print(f"wrote {TAB_INFO}: {len(info)}行", flush=True)

    after = [w.title for w in sh.worksheets()]
    lost = [t for t in before if t not in after]
    assert not lost, f"既存タブが消えました: {lost}"
    print("タブ一覧(after):", after, flush=True)

    URL_OUT.write_text(sh.url, encoding="utf-8")
    print("URL:", sh.url, flush=True)


if __name__ == "__main__":
    main()
