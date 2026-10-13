# 「データなし」が NO-GO に勝って判定理由を消した（2026-10-14 タカシ・T-20260920-003）

## 症状
10/13 18:00 の ledger_refresh 書き戻しで、台帳の NO-GO 764行（＋stage B が同日に判定した210行）が
「#13 今日の値を取り直せていません」の UNKNOWN に変わり、元の FAIL 理由が消えた。dry-run でも再現。

## 原因（対照実験で確定）
- `score_20261004.POOL` が `pipeline/buy_list_private.csv` を読んでいた。このファイルは nightly.sh の
  `write_report.py`（と make_buy_list.py）が**毎晩「判定台帳の全行ダンプ」で上書きする**
  （10/13 18:00 に 648 → 4,716行）
- 商品データ（RAW＝refetch20261004/raw.jsonl）は 648件のまま → 増えた行は全部「取り直し」UNKNOWN
- `ledger_refresh` の by_asin が「GO>UNKNOWN>NO-GO」で良い方を採るので、**データなし UNKNOWN が
  データのある NO-GO に勝った**
- 対照：同じ時刻・同じシートで POOL だけ 648行の凍結コピーに替えると、14:31 の結果と 4,504行が完全一致
  （判定差0）。現行 POOL のままだと 764行が再現。→ 入力の差し替えだけで説明がつく

## 直したこと
1. POOL を `agent_output/.../score20261004/old_pool_20261004.csv`（＝buy_list_private.before_20261010.csv の凍結コピー）に固定
2. `ledger_refresh.better()`：データなしの行はデータのある行に必ず負ける
3. `ledger_refresh.keep_when_no_data()`：データなしの採点で既存行（GO だけでなく NO-GO/UNKNOWN も）を上書きしない
4. `--restore-from <before_*.json>`：取り直しで上書きされた行を上書き前のスナップショットから戻す（一度だけの修復）
5. supplier_screen の `ledger_snapshots()`：dry-run の after を台帳として数えない（サトル引き継ぎの既知バグ）
6. テスト `test_ledger_nodata_20261014.py`（11項目）
- 結果：NO-GO 3,086→3,947／UNKNOWN 1,628→767（nightly の 18:00 集計と一致）。2回目の dry-run で差分0

## 教訓（再利用する形）
- **「行集合」と「その行の商品データ」は同じ時点のものを対で持つ。**片方だけ別のジョブが上書きするファイルを入力にしない
- **「良い方を採る」併合では、データなし（判定不能）を最下位に置く。**UNKNOWN は「データを見て決まらなかった」と「データが無い」の2種類があり、後者は根拠ではない
- 原因を語る前に、入力を1つだけ替えた対照を回す（§3.3-13）。今回は入力の差し替え1本で 0差分まで戻ったので確定できた
- 一度消えた値は before_*.json（書き込み前のシート全値）から戻せる。**書き込み前の全値退避は必ず続ける**

## 同じ夜の手順メモ（仕入れ先起点の台帳合流・Keepa 0）
1. `supplier_screen.py run <input> --label <x>z --tokens 0`（キャッシュだけで screen）
2. `supplier_feed_build.py feed <screen...>` → new_supplier_candidates_<日付>.csv（同日2回目はファイル名に a/b を付けて退避しないと上書きされる）
3. kz 再現値は screen の「キーゾン 過去1〜3ヶ月」を kz_estimate_<日付>[b]_supplier.csv に（feed の ASIN だけ・取得日はキャッシュの日付）
4. `sd-queue` → ledger_refresh dry-run（既存行の判定変化0を確認）→ 書き込み → 2回目 dry-run 差分0
- 追加行はほぼ NO-GO（今夜 5,720行中 5,580行）。台帳の経路構成が NETSEA 92.9% に寄ったので、報告では「行が増えた」ではなく経路比と GO 件数を先に書く
