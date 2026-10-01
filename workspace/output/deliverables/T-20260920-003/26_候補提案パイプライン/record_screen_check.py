#!/usr/bin/env python3
"""人が実画面で見た結果を台帳に書く（2026-10-01 カズヨの6件）。

なぜスクリプトにするか
----------------------
`確認方法` が「機械判定のみ」でなくなった行は、以後**機械が上書きしません**
（`ledger_sheet.update_row` / `update_rows` が守る）。
つまり**ここに書いた時点で、その ASIN は二度と候補として提案されません。**
手で貼るとキーゾンの3列が空のまま「人が確認済み」になり、根拠が残らないので、
**値と出典をコードに書いて実行**します。

ここに書く数字は**カズヨが Chrome ＋キーゾンで実際に見たもの**で、Keepa の推定ではありません。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ledger_sheet  # noqa: E402

C = {n: i for i, n in enumerate(ledger_sheet.COLUMNS)}
CHECKED_BY = "カズヨ（Chrome＋キーゾンで実画面確認）"
METHOD = "実画面確認（Chrome＋キーゾン）2026-10-01"

# ASIN → 書き込む内容。`sold3` はキーゾンの「直近3ヶ月の実数」。
FINDINGS = {
    "B003G7XKTW": {
        "verdict": "NO-GO", "sold3": "0個（3ヶ月）", "rank": "299,573位",
        "why": "キーゾンで直近3ヶ月の販売が0個。売れ筋ランク299,573位。**死んでいる棚**です。",
    },
    "B003G7XKVK": {
        "verdict": "NO-GO", "sold3": "2個（3ヶ月）",
        "why": "キーゾンで直近3ヶ月の販売が2個＝月0.7個。12点仕入れると**17ヶ月**かかり、"
               "回転上限6ヶ月を大きく超えます。",
    },
    "B00Z9IMWKO": {
        "verdict": "NO-GO", "sold3": "データなし",
        "why": "キーゾンにデータなし。**バスタオル2枚で11,000円**は相場から外れており、"
               "終売か転売価格で売価が吊り上がっている疑いが濃厚です。"
               "この売価を前提にした採算は信用できません。",
    },
    "B01M01H03P": {
        "verdict": "NO-GO", "sold3": "データなし",
        "why": "キーゾンにデータなし。加えて利益率8.2%で、発注額が残枠8万円を大幅に超えます。"
               "**残枠8万円を大幅に超えます**（1 SKU の発注額の上限を機械のゲートにしました）。",
    },
    "B0GR4C7TFH": {
        "verdict": "NO-GO", "sold3": "4個（1ヶ月）",
        "why": "月4個。10点＝約22万円で**残枠8万円を大幅に超過**。さらに原価欄が空＝"
               "卸値の裏が取れていません。",
    },
    "B0FNWB76NG": {
        "verdict": "NO-GO", "sold3": "5個（1ヶ月）",
        "why": "🔴 **単位ずれ。**Amazon は「110g、18食入り」＝ Amazon 1個 ＝ 卸18点。"
               "原価は268円ではなく**4,824円**で、"
               "5,180 − 販売手数料456 − FBA 472 − 206 − 4,824 = **▲778円/個の赤字**。"
               "機械は『18食入り』を単品と読んで利益率75.5%と出していました"
               "（`set_count` を直し、卸率15%未満／利益率50%超を UNKNOWN に落とす番兵を入れました）。",
    },
}


def main() -> int:
    ws = ledger_sheet.open_tab()
    values = ws.get_all_values()
    updates, missing = [], set(FINDINGS)
    for i, row in enumerate(values[1:], start=2):
        if len(row) < len(ledger_sheet.COLUMNS):
            continue
        f = FINDINGS.get(row[C["ASIN"]])
        if not f:
            continue
        missing.discard(row[C["ASIN"]])
        new = list(row)
        new[C["判定"]] = f["verdict"]
        new[C["キーゾン 平均月販"]] = f["sold3"]
        if f.get("rank"):
            new[C["キーゾン 過去1ヶ月"]] = f["rank"]
        new[C["判定理由"]] = (f"【実画面確認 2026-10-01】{f['why']}"
                          f" ／ 機械判定の記録: {row[C['判定理由']]}")[:1000]
        new[C["確認方法"]] = METHOD
        new[C["確認者"]] = CHECKED_BY
        updates.append((i, new))
        print(f"  {row[C['ASIN']]} → {f['verdict']}（{f['sold3']}）")

    if missing:
        print(f"⚠️ 台帳に無い ASIN: {sorted(missing)}（行が無いので書けません）")
    # state を渡さない＝ここは人の書き込みなので保護を通さない（保護は機械側のための仕組み）。
    n = ledger_sheet.update_rows(updates, ws)
    print(f"\n{n}行に実画面確認の結果を書きました。"
          "以後この ASIN は機械判定で上書きされません（＝二度と候補に出ません）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
