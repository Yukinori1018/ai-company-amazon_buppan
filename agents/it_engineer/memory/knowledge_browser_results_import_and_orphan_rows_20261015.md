---
name: knowledge-browser-results-import-and-orphan-rows
description: カズヨの実画面 TSV を証跡ファイルへ変換する道具と、採点プール外の「孤児行」に人の確認が効かない落とし穴（2026-10-15 T-20260920-003）
metadata:
  type: knowledge
---

# 実画面 TSV の書き戻しと孤児行（2026-10-15・T-20260920-003）

## この依頼はこう処理した（再利用手順）
1. `26_候補提案パイプライン/browser_results_import.py <tsv> --tag <日付>_browser --checked-at "YYYY-MM-DD HH:MM" --dry-run`
   → ゲート/カート件数とメーカー本人の疑いを確認 → `--dry-run` を外して証跡 CSV（ledger20261010/gate_check_*・cart_check_*）と _sourcing_checks を書く
2. **証跡を置く前に** `ledger_refresh.py --dry-run` を基準として保存（after_dryrun.json をコピー）→ 置いた後の dry-run と行順で比較（ASIN 以外の行が動いていないか）
3. `RUN_TAG=<tag> ledger_refresh.py`（before_<日付>_<tag>.json が全値バックアップ）→ もう1回 dry-run して書いた値と差分0
4. 両方 PASS の行は判定理由の「【こう変えれば】」より前から `#番号 … FAIL/UNKNOWN` を抜いて残項目を数える

## 気づき
- 🔴 **採点プールに居ない行は、人がいくら確認しても台帳が動かない。**10/14 に POOL を 648行の凍結コピーへ戻した結果、10/13 の生きたプールでだけ採点された約850行が以後一度も引き直されない（判定日 10/13・10/14 のまま）。今回は85件中16件がこれで、ゲート FAIL（B07G4HFP3N）でも UNKNOWN のまま残っていた
  - 対処：`ledger_refresh.score_screened_orphans()`＝人の証跡がある ASIN だけ、生きたプールの行＋手元の Keepa データで再採点（データ無しは据え置き）。孤児の全量を戻すかは別判断として秘書に返した
  - 見分け方：dry-run 後に `判定日 != 今日` の行を数える
- カズヨの「第三者」も、保持者名＝ブランド名なら疑いに落とす（B0GJR86F8W ハナリラ）。§3.3-5 は人の読みより厳しい側で
- TSV に無い値（カート価格・FBA/自己発送の本数）は空欄のまま。空欄を文字列に埋め込むと「（円・」のような崩れが出る → 書式側で空を飛ばす
- GO 一覧の「セラー数」「Amazon 本体の有無」は Keepa 由来の列で、人の #7（新品n件・本体なし）を拾っていない。報告では TSV から補う（次に直す候補）
- 他のタカシが同じファイル（ledger_refresh.py）を未コミットで編集していた。読み直してから Edit し、commit メッセージに併記した
