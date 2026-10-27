---
name: 台帳外の追加確認1件の足し方と、Keepa の古い内訳が人の内訳に勝つ件（2026-10-20 br1020）
description: browser_extra の1行を原本 TSV を触らずに取り込む型・月販を手元 Keepa から kz 再現で足す型・share_gate が人の FBA/自己発送より Keepa buyBoxEligibleOfferCounts を優先する挙動（T-20260920-003）
type: knowledge
---

# 2026-10-20 夜間 br1020（35件＋1件）

## この依頼はこう処理した（10/19 と同じ型＋追加1行）
1. 基準 dry-run → `after_<日付>_pre_<tag>_dry.json`。今夜の stages 本番 after とバイト一致を先に見る（今回一致）
2. カズヨの原本 TSV は触らない。追加確認（browser_extra_*.txt）は TSV 形式の1行にして **`browser_results_<日付>_all.tsv` を別に作り**、それを import（同じ tag を2回 import すると cart_check が上書きされるため1本にまとめる）
   - 自由記述の「ゲート=申請で開く」は `PASS（申請で開く・書類10点）`、価格は商品名列末尾の `カート◯円` に入れれば importer が拾う
3. 注記（LIFE だけ／FBA・自己発送の内訳）は生成された cart_check の注意欄に追記（BOM 付き utf-8-sig で書き戻す）
4. 月販が「未確認（Keepa 非表示）」の行は、手元の keepa_stage_*.jsonl に商品があれば `kz_estimate.months(p, fetched//60 - T0)` で再現し、`ledger20261010/kz_estimate_<日付>_extra.csv`（kz_estimate_stages.csv と同じ列＋取得日）に置く。sorted で stages より前に並ぶので、stages に同じ ASIN があればそちらが勝つ
5. dry-run → cmp.py（TSV 外の変化0・判定が動いた行を列挙）→ 本番 RUN_TAG → cmp で事前 dry-run と一致 → 2回目 dry-run と一致
6. one_step は scratchpad の onestep2.py（「【こう変えれば】」前・「未達：」後・#18 派生除外）。前夜の台帳で前夜ファイルと一致を確認してから出す
- dry-run・本番とも1回 約5〜6分。4回で約25分

## 気づき
- 🔴 **share_gate は Keepa の buyBoxEligibleOfferCounts があると、人の出品一覧（新品n件・FBA/自己発送）より Keepa を使う。**人の内訳が offer_check_*.csv（FBA・即納の自己発送を整数で）に無い限りそうなる。B07K6L6GZ4 は Keepa 10/12（FBA1・自己発送7）で 0.7個/月 → FAIL。人の画面は FBA2・自己発送5 で、即納 k≦3 なら1.0個以上になる
  - 即納か取り寄せかを人が数えていないのに offer_check を作らない（推測で埋めない）。条件（k≦3）を注意欄と報告に書いて止める
  - 直すなら：Keepa の内訳の取得日が古く、人の新品件数と食い違うときは「上限・下限で挟む」（10/18 の bound）に落とす。今夜は結果が変わらない（family 合計なので子単独はもっと少ない）ため未修正。次に同型が出たら直す候補
- 「価格の更新だけで NO-GO→UNKNOWN に戻る」行（手残り数円の C ↔ 実績枠）は、取り分で再び落ちることが多い。月販が非表示の行は先に kz 再現を当てると一晩で決着する
