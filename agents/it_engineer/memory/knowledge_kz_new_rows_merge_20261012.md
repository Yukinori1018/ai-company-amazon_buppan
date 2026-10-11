# kz 入口の「台帳に未登録」行を台帳へ合流させる型（2026-10-12 T-20260920-003）

## この依頼はこう処理した（再利用可）
1. **別ルートの候補 CSV をシートへ直接書かない。**`ledger_refresh.score_netsea()` に供給源を1本足す
   （`score_kz_entry`：候補 CSV の ASIN を既存行と同じ `S.build` で採点。Keepa は手元の jsonl＝0トークン）。
   こうすると人の証跡・季節・法務・SD 経路・GO 一覧がすべて同じ規則で当たる
2. 入口固有の値（kz）は**証跡ファイルの形**で渡す：`kz_entry_candidates.py estimate` →
   `ledger20261010/kz_estimate_20261011_kzentry.csv`（screen_checks.load_kz_estimate が glob で拾う）
3. 新しい Keepa 取得ファイルを使うなら `screen_checks.RAW_FILES` に足す（足さないと取り分＝UNKNOWN）
4. 人の実画面 CSV（秘書の形式）は既存の証跡形式に**転記**：cart_check_／gate_check_／offer_check_<日付>_<tag>.csv
   ＋ `scripts/sourcing_gate/check_record.py set ... --by kazuyo` で画面で見た項目だけ記録
5. 書き込みは**夜間走行の終了を待つ**（`until grep "<今日> .*夜間走行 終了" nightly.log` を run_in_background）。
   待つ間に dry-run・テスト・commit を済ませる
6. 本番：`RUN_TAG=kz_write python3 ledger_refresh.py` → もう1回 dry-run で差分0を確認

## 気づき・失敗
- **推奨初回点数が書類申請の10点を下回っていた**（`share_gate` で `rec = qty or floor`＝採算の点数6が優先）。
  §3.5 #3 の10点はゲート確認より後に効くので、下限は `max(qty, floor)` で当てる。テスト追加済み
- kz_entry 側の build は在庫月数（最小ロット100点で17か月）を見ていなかった。台帳側の share_gate が FAIL にした＝
  **入口スクリプトで通っても台帳の規則で落ちる**。入口の CSV の判定は「仮」と読む
- 実画面の現在価格が中央値と5割ずれても（キングジム 2,400 vs 1,598）、採算は90日中央値（§3.3-28）。
  `score_20261004.SCREEN_PRICES` に人の価格を入れると中央値を上書きしてしまうので、**入れない**
- 送料別の自己発送（1,500＋490）は Keepa BuyBox が送料込み1,990で持つ。FBA で1,990に並べる前提で手数料も1,990に掛かる（750円の崖とは無関係の帯）
- 日付が変わるだけで価格の傾き（90日窓）が動き、既存行の判定が変わる（B0H4QMMTXF UNKNOWN→NO-GO）。
  自分の変更の影響と混ぜずに報告する
- SD 起点 375行は ASIN 付き249件が全部台帳にあり、残り70行は ASIN なし（SD 取引条件で NO-GO）＝台帳のキーに載らない
