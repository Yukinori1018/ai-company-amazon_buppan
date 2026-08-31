"""規模判定の検算（T-20260831-004 / タカシ）.

    python3 34_verify.py

秘書から渡された期待値を、実際の出力に当てて合否を出す。
**期待どおりにならなかったものは、原因まで書く。** 通ったことより落ちた理由が大事。

期待値（発注時に指定されたもの）:
  落ちるはず : ブシロード / Hamee（いずれも上場企業）
  残るはず   : すごろくや / BOS / 愛知電線 / オスモカラー
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

EXPECT_DROP = ["ブシロード", "Hamee"]
EXPECT_KEEP = ["すごろくや", "BOS", "愛知電線", "オスモカラー"]


def load(name: str) -> list[dict]:
    p = HERE / name
    if not p.exists():
        sys.exit(f"先に 32_resolve_size.py を実行してください（{name} が無い）")
    return list(csv.DictReader(p.open(encoding="utf-8-sig")))


def main() -> int:
    ledger = load("33c_規模判定_全件台帳.csv")
    by_name = {r["メーカー"]: r for r in ledger}

    def find(token: str) -> dict | None:
        for k, v in by_name.items():
            if token.lower() in k.lower():
                return v
        return None

    ok = True
    print("=" * 78)
    print("検算 — 発注時の期待値に対する実測結果")
    print("=" * 78)

    for token, want in [(t, "落ちる") for t in EXPECT_DROP] + [
        (t, "残る") for t in EXPECT_KEEP
    ]:
        r = find(token)
        if r is None:
            print(f"[NG] {token:12} 262社リストに存在しない")
            ok = False
            continue
        got = "落ちる" if r["理由コード"] in ("L1", "L2") else "残る"
        mark = "OK " if got == want else "NG "
        ok &= got == want
        print(
            f"[{mark}] {token:12} 期待={want} 実測={got}  "
            f"[{r['理由コード']}] 従業員={r['従業員数'] or '—'} "
            f"資本金={r['資本金'] or '—'} 商号={r['gBiz商号'] or '—'} "
            f"候補{r['候補件数'] or 0}件"
        )

    print()
    print("— 参考: 従業員数だけで判定した場合（資本金ルールを外すと何が起きるか）")
    for token in EXPECT_DROP:
        r = find(token)
        if not r:
            continue
        emp = r["従業員数"]
        verdict = "落ちる" if emp and int(emp) > 300 else "残ってしまう"
        print(f"    {token:12} 従業員={emp or '—'} → {verdict}")

    print()
    print("結果:", "全項目一致" if ok else "不一致あり（上記 NG を参照）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
