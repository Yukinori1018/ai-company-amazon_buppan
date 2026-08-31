"""規模判定の検算（T-20260831-004 / タカシ）.

    python3 34_verify.py

**社長の訂正（2026-08-31）で期待値が変わった。**
「従業員300人以下はあくまで目安です。絶対的な数字としないでください。
  仕入れサイトからだともしかしたら大企業でも仕入れられるかもしれません。」

したがって検算する内容は「落ちること」ではなく：
  1. **262社が262社のまま出ていること**（1社も落ちていない）
  2. ブシロード・Hamee に**規模が大きいという印が付いていること**
  3. すごろくや・愛知電線が**中小の目安に入っていること**
  4. BOS・オスモカラー（規模を確認できない会社）が**リストに残っていること**
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIST = "33_連絡候補_規模情報つき.csv"
SOURCE = "10_連絡候補メーカー.csv"

#: (メーカー名の一部, 期待する直接交渉の目安の先頭文字)
#: ◎=中小の目安 / △=規模が大きい / —=規模を確認できず
EXPECT = [
    ("ブシロード", "△"),
    ("Hamee", "△"),
    ("すごろくや", "◎"),
    ("愛知電線", "◎"),
    ("BOS", "—"),
    ("オスモカラー", "—"),
]


def load(name: str) -> list[dict]:
    p = HERE / name
    if not p.exists():
        sys.exit(f"先に 32_resolve_size.py を実行してください（{name} が無い）")
    return list(csv.DictReader(p.open(encoding="utf-8-sig")))


def main() -> int:
    rows = load(LIST)
    src = load(SOURCE)
    ok = True

    print("=" * 78)
    print("検算 — 規模は目安であり足切りではない（社長の訂正 2026-08-31 を反映）")
    print("=" * 78)

    # 1. 1社も落ちていないこと
    lost = {r["メーカー"] for r in src} - {r["メーカー"] for r in rows}
    if lost:
        print(f"[NG ] 入力{len(src)}社 → 出力{len(rows)}社。{len(lost)}社が消えた: "
              f"{sorted(lost)[:5]}")
        ok = False
    else:
        print(f"[OK ] 入力{len(src)}社 → 出力{len(rows)}社。**1社も落ちていない**")
    print()

    by_name = {r["メーカー"]: r for r in rows}

    def find(token: str) -> dict | None:
        for k, v in by_name.items():
            if token.lower() in k.lower():
                return v
        return None

    for token, want in EXPECT:
        r = find(token)
        if r is None:
            print(f"[NG ] {token:12} リストに存在しない")
            ok = False
            continue
        got = r["直接交渉の目安"][:1]
        mark = "OK " if got == want else "NG "
        ok &= got == want
        print(
            f"[{mark}] {token:12} 期待={want} 実測={got}  [{r['理由コード']}] "
            f"規模区分={r['規模区分']:<10} 従業員={r['従業員数'] or '—':>5} "
            f"資本金={r['資本金'] or '—':>12} 商号={r['gBiz商号'] or '—'}"
        )

    print()
    print("— 従業員数だけを見ると、上場2社は「300人以下」に入ってしまう")
    for token in ("ブシロード", "Hamee"):
        r = find(token)
        if r:
            print(f"    {token:12} 従業員={r['従業員数']}人 → 区分「{r['規模区分']}」。"
                  f"資本金 {int(r['資本金'])/1e8:.1f}億円 で規模の大きさが分かる")

    print()
    print("結果:", "全項目一致" if ok else "不一致あり（上記 NG を参照）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
