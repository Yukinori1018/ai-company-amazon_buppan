# 台帳に「横から」書いた値は、引き直しに知らせないと次の夜に消える（2026-10-21）

## 何が起きたか
- 10/20 夕、カズヨが出品申請画面（§3.3-41）を304件読み、`apply_probe_20261020/write_ledger.py` で
  台帳のゲート種別・ゲート可否だけを直接書いた。
- 10/21 02:04・02:09 の `unknown_stages.py run` → `ledger_refresh.py` がゲート列を組み直し、
  GO/UNKNOWN の55行が「可（新品）」（51）／「未確認」（4）に戻った。

## 原因（2つの経路）
1. `netsea_cells()` / `sd_screen()` は restrictions/approve（`gate_check_*.csv`・10/09 fallback）しか
   知らず、そのゲートがある行は毎回「可（新品）／不可」で上書きする。申請画面は見ていない。
2. SD 行は `sd_rows()` が行を丸ごと作り直す（初期値「未確認」）ので、横から書いた値が消える。

## 直し方（ledger_refresh.py）
- `load_apply_probe()`：`agent_output/T-20260920-003/apply_probe_*/results.tsv` をフォルダ日付順に読む（後勝ち）。
- `latest_gate_cells()`：申請画面と restrictions/approve を**観測日で比べて新しい方**。同日なら申請画面
  （書類の点数まで読んでいるので情報が多い）。restrictions/approve が新しければそちらの文言。
- `final` を組んだ直後に全行（人の行・追記行・SD 行も）へ当てる。判定・判定理由は触らない。
- summary に「ゲート列を申請画面／新しい観測で書き直した行」を出す。

## 再利用できる型
- **台帳を書く口が2つ以上あるとき、片方（引き直し）がもう片方の証跡を読まないと必ず上書きで負ける。**
  横から書くスクリプトを作ったら、同じ turn で ledger_refresh 側に「その証跡ファイルを読む口」を足す。
- 検算：before/after の JSON を列ごとに差分して、「変わった列」の内訳を通常回（例 02:09）の内訳と比べる。
  卸率4545・利益率467・Amazon価格121 は毎回出る表示ゆれ（今回の修正とは無関係）。
- 無課金で引き直しを確かめる：`unknown_stages.py run --no-fetch --no-write`（Keepa を叩かず ledger_refresh --dry-run）。

## 残した提案（別件）
- 区分（要書類 N 点・申請不要・不可）を判定に効かせる（#3 の N 点と在庫月数）。今回は表示だけ。
