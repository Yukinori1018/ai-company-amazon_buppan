"""タケシの全メーカー台帳1,247社に、規模判定の結果を合流させる（T-20260831-004 / タカシ）.

    python3 35_merge_ledger.py

「落ちた会社を捨てない」ための1本の台帳を作る。
連絡候補262社には規模の理由コードが入り、それ以外の985社にはタケシの除外理由が残る。
どの会社も、**なぜ今ここにいるのか**が1行で分かる状態にする。
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

SRC_LEDGER = "12_全メーカー判定台帳.csv"
SIZE_LEDGER = "33_連絡候補_規模情報つき.csv"
OUT = "35_全メーカー台帳_規模判定込み.csv"

ADD_COLS = [
    "直接交渉の目安", "規模区分", "資本金区分", "理由コード", "理由",
    "従業員数", "資本金", "法人番号", "gBiz商号", "代表者名", "所在地", "企業URL",
    "照合の注意", "候補件数", "候補一覧", "参考_前方一致の未検証候補",
]


def main() -> int:
    base = list(csv.DictReader((HERE / SRC_LEDGER).open(encoding="utf-8-sig")))
    size = {
        r["メーカー"]: r
        for r in csv.DictReader((HERE / SIZE_LEDGER).open(encoding="utf-8-sig"))
    }

    rows = []
    for r in base:
        s = size.get(r["メーカー"])
        extra = {c: (s.get(c, "") if s else "") for c in ADD_COLS}
        if not s:
            # 連絡候補でない985社。規模は見ていない（見る必要が無い段階で落ちている）
            extra["直接交渉の目安"] = "— 規模を見ていない"
            extra["規模区分"] = "未取得"
            extra["資本金区分"] = "未取得"
            extra["理由コード"] = "N/A"
            extra["理由"] = f"連絡候補に到達していない（タケシ判定: {r['判定']}）"
        rows.append({**r, **extra})

    cols = list(base[0].keys()) + [c for c in ADD_COLS if c not in base[0]]
    with (HERE / OUT).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    c = Counter(r["理由コード"] for r in rows)
    stats = {
        "台帳の総行数": len(rows),
        "規模判定を当てた社数": sum(v for k, v in c.items() if k != "N/A"),
        "理由コード別": dict(sorted(c.items())),
    }
    (HERE / "35b_集計_台帳.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
