# T-20260914-004 T-2 需要先行リスト × 卸の照合（タカシ）

| ファイル | 中身 | Git |
|---|---|---|
| `01_T2_卸照合.md` / `.html` | 本文。件数・率・ブランド単位のみ（金額なし） | 追跡 |
| `code/` | 再現用スクリプト（netsea_index → match → profit、wholesale_probe）。実行場所は `agent_output/T-20260914-004/takashi/`（NETSEA 索引 880MB がそこにある）。人の判定を入れる `review.py` は ASIN 別の判定を持つので agent_output にだけ置き、判定の結果は `out/t2_matched.csv` の「人の確認」列に入れた | 追跡 |
| `out/t2_matched.csv` | 照合36行の明細（卸値・利益・回転・人の確認と理由） | 追跡外（PUBLIC リポのため） |
| `out/t2_summary.json` / `out/t2_review.json` | 漏斗の件数（機械のまま／人の確認後） | 追跡外 |

入力: `T-20260914-002/out/t2_input.csv`（T-1）・`T-20260831-006/out/netsea_items.jsonl`（NETSEA raw 8/31）・T-1 product raw。NETSEA API 0 call・Keepa 0 token。
