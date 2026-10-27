---
name: 実画面書き戻し br1022 の手順と、カート価格が無いと 6b の戻り行が進まない件（2026-10-22）
description: br1021 と同じ型を1夜分。比較スクリプトは文字列で比べる（シート読み戻しは str・JSON は int）。apply_probe の行が残ることの確かめ方。T-20260920-003
type: knowledge
---

# 2026-10-22 夜間 br1022（35件）

## 手順（約25分・dry-run と本番が各5〜6分）
1. `RUN_TAG=pre_br1022_dry ledger_refresh.py --dry-run` → `after_dryrun.json` を `after_<日付>_pre_<tag>_dry.json` にコピー
2. `browser_results_import.py <tsv> --tag <日付>_browser --checked-at "..."`（先に --dry-run で件数だけ見る）
3. cart_check_<日付>_browser.csv の注意欄に前夜メモを引き継ぐ（utf-8-sig で書き戻す）。**前夜の cart_check の注意は新しいファイルに引き継がれない**ので、残す指示があるメモは手で写す
4. dry-run → 本番 RUN_TAG=<tag> → 2回目 dry-run。`cmp` で after 3本のバイト一致
5. one_step：前夜の台帳で前夜 TSV と一致を確かめてから今夜分（onestep.py の参照日付を2か所替える。sed で一括置換すると前夜の参照まで今夜に化けるので行番号指定で直す）

## 気づき
- 🔴 **差分スクリプトは str() で比べる。** `before_*.json`（シートの読み戻し）は文字列、`after_*.json` は数値が int のまま。生で比べると Amazon価格 7,128行などの偽差分が出る
- apply_probe（秘書の申請画面）が引き直しで残るかは「基準 dry-run vs シートの読み戻し」でゲート列の差0を見れば足りる。今夜 8行とも残った（10/21 の向き比較の修正が効いている）
- 6b で NO-GO→UNKNOWN に戻った「Keepa はカートなし」の行は、実画面で第三者カートが見えても **#13-14（価格履歴なし）と #18（売価未定）で止まる**。カズヨの TSV に「カート◯円」が無いと次に進まない。秘書に「カート価格を商品名列末尾に入れて」と返す
- Keepa の古い内訳が画面件数より優先される件（10/20 指摘）：今夜は2件（B018V4FW86・B0D1TRRXS9）だが判定には効かず未修正。効く行が出たら bound に落とす修正をする

## 結果
- 判定の変化0（GO 0／実績枠4／UNKNOWN 302／NO-GO 10,504）。one_step 21行（前夜20＋B0FFLKN5LS）

# 追記 2026-10-23 夜間 br1023（29件・同じ手順で約15分）
- 手順は上のとおりで再現できた。補助スクリプト（onestep.py・ldiff.py）は前夜のスクラッチに残っているのでコピーして使う（`/private/tmp/claude-501/<proj>/<session>/scratchpad/`。消えたら上の手順から書き直す）。onestep.py の日付は「前夜の after→前夜の one_step→今夜の after」の3つ。置換は一時トークン（__CUR__）を挟むと前夜参照が今夜に化けない
- 🔴 件数は **行ベース**で数える。ldiff.py は ASIN をキーに dict 化するので重複 ASIN 1行ぶん NO-GO が1少なく出る（10,510 vs 行ベース 10,511・総10,810行）。報告は onestep.py／行ベースの値
- カズヨが TSV の #7 末尾に「カート◯円／最安◯円」を入れるようになった。importer はカート価格列に入れない（空のまま）＝§3.3-28 に沿う。注意欄に「画面1点の参考値」と明記した。**6b の戻り行が採算に進むには、この1点ではなく Keepa の価格履歴が要る**（前夜の宿題は継続）
- 結果：判定変化0・one_step 21行（前夜と同じ顔ぶれ）・UNKNOWN 295
