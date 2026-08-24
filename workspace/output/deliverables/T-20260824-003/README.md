# T-20260824-003 — Keepa `monthlySold` のメモリ記述を公式定義＋保存済み実データで突合

親チケット: T-20260824-001（Keepa 用語の公式ドキュメント突合／サトル）

## ファイル

| ファイル | 内容 |
|---|---|
| `monthly-sold-distribution.md` | **結果本体。** 実データ 4,002 ASIN の分布・階級値の一覧・欠測率・時期別の挙動・実装上の申し送り |
| `monthly-sold-distribution.html` | 上記の HTML 版（社長閲覧用） |
| `analyze_monthly_sold.py` | 集計スクリプト。**Keepa API は叩かない（0トークン）** |
| `analyze_output.md` | スクリプトの生出力（全月の表を含む完全版） |

## 一行結論

`monthlySold` は **11 種類の階級値しか取らず（50/100/200/…/1000）、66.5% が欠測**。
公式定義と完全に整合。ただし memory にあった「**月50個以上にしか出ない**」は
**履歴に 10/20/30/40 が実在するため誤り**で、50 はスキャン時期のたまたまの下限でした。

## 再現

```bash
python3 analyze_monthly_sold.py --repo-root "/path/to/ai-company-amazon_buppan"
```

入力は `workspace/output/deliverables/T-20260817-005/raw/*.json.gz`（固定）なので冪等です。

## 反映先

`agents/it_engineer/memory/knowledge_keepa_product_finder_fields.md`
→ 末尾に「`monthlySold` の正体（2026-08-24 T-20260824-003 で再検証・記述を修正）」節を追加。
