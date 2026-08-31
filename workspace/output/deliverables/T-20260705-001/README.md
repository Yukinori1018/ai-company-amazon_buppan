# T-20260705-001 — 原石密度の実測（インデックス）

## ⚠️ 2026-08-31: NETSEA 卸価格の列を削除しました

法務ハルオの判定書（`T-20260831-006/01_NETSEA仕入れの適法性判定.md` §5）を受けた是正です。
NETSEA 公式は「**商品の卸価格は会員様にのみ公開**」としており、当リポジトリは PUBLIC で 30 分ごとに自動 push されるため、
**バイヤー会員規約 第7条2項3号／API 利用規約 第15条（秘密保持）に抵触しうる**状態でした。

| ファイル | 落としたもの | 残したもの |
|---|---|---|
| `netsea_scan_results.csv` | `buy_excl`（卸価格・税抜）／`net`／`margin` の3列 | 269行すべて。`jan, name, amazon, asin, verdict, offers, msales, rank, tier1, tier2` |
| `netsea_run.log` | 「黒字だった卸商品」12行の `buy` / `net` / `率` | 行そのもの・商品名・Amazon 価格・相乗り数・月販 |

**`net` と `margin` も落とした理由:** `margin = net ÷ amazon` であり、`net` は卸価格から `calc/profit.py`（本リポジトリに commit 済み）で算出されています。
`amazon` を残したまま `net` を残すと、**卸価格が狭い幅で逆算できてしまう**ため、卸価格そのものと同視して削除しました。
`verdict` / `tier1` / `tier2` は粗い区分（帯）でしか価格を示さないため残しています。

**行は1行も削除していません。**ファイル削除・Git 履歴の書き換えも行っていません（CLAUDE.md §4.1）。
既に push 済みのため**履歴には残ります**。「現在の HEAD から消す」までが本是正のスコープです（ハルオ A 案）。

## 今後のルール（このフォルダのデータを扱う人へ）

**NETSEA 由来の卸価格を `deliverables/` に出さないこと。** 分析に必要な場合は `agent_output/`（`.gitignore` 対象）に留め、
成果物には集計値・判定結果だけを載せてください。データの素性と用途制限は `SOURCE.md` に記載があります。

## ファイル一覧

| 種別 | ファイル |
|---|---|
| 出所カード | `SOURCE.md` |
| NETSEA 卸起点スキャン | `netsea_scan.py` / `netsea_scan_results.csv` / `netsea_summary.json` / `netsea_run.log` |
| Yahoo/楽天 起点スキャン v1 | `density_scan.py` / `density_scan_results.csv` / `density_summary.json` / `scan_run.log` |
| Yahoo/楽天 起点スキャン v2（2000件） | `density_scan_v2.py` / `density_v2_results.csv` / `density_v2_gems_liquidity.csv` / `density_v2_summary.json` / `scan_v2_run.log` / `scan_v2_progress.log` |
| 買い候補の絞り込み | `vetting_filter.py` / `buy_shortlist.csv` / `buy_shortlist_amazon.csv` |
| スプレッドシート生成 | `build_spreadsheet.py` / `build_research_gsheet.py` / `populate_research_gsheet.py` / `原石密度_リサーチデータ_2000件.xlsx` |
| サマリ（社長向け） | `原石密度_実測PDCA_サマリ.{md,html,pdf}` / `原石密度_実測PDCA_サマリ_v2_2000件.{md,html,pdf}` |

> **上記のうち NETSEA 由来なのは `netsea_*` の4ファイルだけです。** `density_*` / `buy_shortlist*` / `.xlsx` の仕入れ価格は
> **Yahoo ショッピング・楽天**（一般消費者が閲覧できる小売価格）由来で、卸価格ではありません（2026-08-31 マリエが `source` / `buy_source` 列を実測して確認）。
