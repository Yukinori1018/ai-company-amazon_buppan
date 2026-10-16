---
name: knowledge-browser-price-and-frozen-sd-rows-20261017
description: 実画面 TSV のカート価格・404 の取り込み、#13 の実画面売価が採算に効かない理由、SD 卸価格だけ人が見た行が凍結される落とし穴、one_step の数え方（T-20260920-003・2026-10-17 夜間）
metadata:
  type: knowledge
---

# 実画面の価格・404・凍結行・one_step（2026-10-17 夜間）

## この依頼はこう処理した（再利用手順）
1. 証跡を置く前の台帳スナップショット（after_<日付>_stages_*.json）を基準にする
2. 証跡ごとに dry-run を分ける：A=サトルのセット数（ファイルは既に置かれていた）→ after_dryrun.json を after_<日付>_setcheck_dry.json にコピー／B=browser_results_import → dry-run → after_<日付>_browser_dry.json。行ごとに「対象 ASIN 以外で変わったセル0」を確認
3. 本番 `RUN_TAG=<tag> ledger_refresh.py` → 2回目 dry-run を本番の after_<tag>.json とセル単位で比較して0
4. one_step：UNKNOWN 行の判定理由の「【こう変えれば】」より前・「未達：」より後を「／」で割り、`#番号 … UNKNOWN|FAIL` を数える。**#18 採算 UNKNOWN（計算しません／等級 UNKNOWN／実績枠の候補）は他項目の派生なので数えない**。この規則で 10/16 の台帳を数え直すと 78行中75行一致（残りはスナップショットの時点差）。スクリプトは scratchpad で使い捨て（毎回ここから書けば足りる）

## 気づき
- **カズヨの TSV は商品名列の末尾に「カート4,870円」「過去1か月50点以上」を書いてくる。**importer で読む（parse_cart_price / parse_sold_label）。無い行は空欄のまま
- **#5 に「商品ページ404」が来る。**カートなし扱いにすると cart_gate が「相場に戻せば取れる」と書くので、404 を別の分岐にした（UNKNOWN・詳細ページが無ければ諦める）
- 🔴 **cart_check のカート価格は採算の売価に入らない。**採算の screen_price は score_20261004.SCREEN_PRICES（10/4 の固定 dict）だけ。§3.5 #13 は「現在価格で計算」を落とす条件にしているので、勝手に配線しない。配線するなら Keepa に価格履歴が無い行に限り、#13-14 は UNKNOWN のまま残す設計を秘書に決めてもらう
- 🔴 **needs_browser の #13 は引き直し前に集めていた。**今夜は26件中23件が既に #9/#10 FAIL で NO-GO＝人の確認が判定を動かさない。unknown_stages の to_browser を引き直し後の UNKNOWN に絞った
- 🔴 **確認者に「カズヨ（SD 卸価格のみ実画面）」と入った26行は 10/11 から凍結されている。**is_human は「カズヨ」を含めば凍結（screen_checks の証跡がある ASIN だけ例外）。人が見たのは卸値だけで判定は機械なのに、セット数の人の確認（B00H2E0JLW＝2点）まで効かなくなる。指示が「凍結行は上書きしない」だったので触らず秘書に返した。解除するなら is_human に「SD 卸価格のみ」を凍結しない条件を足すのが最小
- セット数は「決まれば GO が増える」ではない（10/11 と同じ結論）：確定35行のうち32行が C 等級で NO-GO、GO・実績枠は0。B0817SB56S（3/2）は利益率 -104%
- 分数 3/2（1 を超える分数）は既存の _num／set_label／order_plan で正しく扱えていた。テストを足して固定しただけ
