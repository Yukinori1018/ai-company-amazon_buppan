# kz 入口：monthlySold を問わず「キーゾン再現の3か月販売数」で Amazon 起点の母数を作る

2026-10-11 / T-20260920-003。社長「GO 2件では事業にならない」→ カズヨ発注。

## 手順（再利用可・コードは deliverables/T-20260920-003/26_候補提案パイプライン/kz_entry_*.py）
1. `kz_entry_harvest.py`：agent_output の Keepa キャッシュ総ざらい（1,199ファイル・約1分・トークン0）→ `agent_output/.../kz_entry/harvest.pkl`
   - 65,189 ASIN のうち **ランク履歴 csv[3] を持つのは 6,488 だけ**（大半のキャッシュは history=0）。kz を全件にかけるには履歴の取り直しが要る
   - だから**先に NETSEA 索引（67,667 JAN・10/01）で JAN を当てて絞り**、当たった分だけ履歴を取る（2,849 ASIN が当たる）
2. `kz_entry_fetch.py hist <queue>`：stats=90&history=1 で1トークン/ASIN。履歴なし・在庫ありの 728件 = 728トークン
3. `kz_entry_candidates.py queue`：kz平均≥6・既知の本体カートを除外 → queue_full.json（925件）
4. `kz_entry_fetch.py full <queue>`：buybox=1 を足して3トークン/ASIN。**10/10以降に buybox 付きで取った既存の生データを先に流し込む**と 208件ぶん（624トークン）浮いた
5. `kz_entry_candidates.py build`：score_20261004.build() をそのまま呼び、「実売」ゲートだけ kz に差し替え。A/B かつ取り分≥3 を CSV に出す。台帳に既にある ASIN は別ファイル

## 気づき
- **二段で払う**：足切り（kz）は history だけで決まるので1トークン。buybox（+2）は通った ASIN にだけ払う
- 等級 UNKNOWN の主因は「セット数の不一致（商品名の数 ≠ Keepa PQ）」と「90日の売価が無い」。ここは単位ずれ＝真偽なので機械で埋めない（§3.3-17）
- バリエーション子の kz は family 合計。実売ゲートは UNKNOWN にして注意を書く（PASS にしない）

## 事故と是正
- 🔴 **NETSEA の `list_suppliers()` が本番失敗時に黙ってサンプル（ID 1000〜1003 の4社）を返していた。**2026-10-11 夜 api.netsea.jp がタイムアウト・www は 503 の時間帯に「承認済み4社・索引済み227社は全部消えた」ように見えた。→ 本番失敗時は `NetseaError` を投げるよう修正（T-20260521-005/code/adapters/netsea.py）。§3.3-11 と同型（search 側は 9/30 に直っていたが suppliers 側が残っていた）
- サンドボックスの外でも同じ＝こちらのネットワークではなく NETSEA 側の停止。**停止中は 10/01 の索引で判定し、卸値・在庫は「発注直前に引き直し」と書く**
