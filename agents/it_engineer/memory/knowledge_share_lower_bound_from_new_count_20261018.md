---
name: knowledge-share-lower-bound-from-new-count-20261018
description: 実画面の「新品n件」だけで #10 取り分を決める下限・上限の考え方と、実画面59件の書き戻し手順（T-20260920-003・2026-10-18 夜間）
metadata:
  type: knowledge
---

# 新品件数だけで #10 を決める（2026-10-18 夜間）

## この依頼はこう処理した（再利用手順・10/17 朝と同じ型）
1. 証跡を置く**前に** `ledger_refresh.py --dry-run` → after_dryrun.json を `after_<日付>_pre_<tag>_dry.json` にコピー（基準）
2. `browser_results_import.py <tsv> --tag <日付>_browser --checked-at "..."`（dry-run は秘書が済ませている）
3. dry-run → `after_<日付>_<tag>_dry.json`。基準とセル単位で比較し「TSV に無い ASIN の変化0」を確認（scratchpad の cmp.py：ASIN キーで突き合わせ）
4. `RUN_TAG=<tag> ledger_refresh.py`（before_*.json が退避）→ `cmp` で本番 after と事前 dry-run がバイト一致 → 2回目 dry-run も本番とバイト一致
5. one_step：UNKNOWN 行の判定理由を「【こう変えれば】」の前・「未達：」の後で「／」に割り、`#番号 … UNKNOWN|FAIL` を数える。#18 の派生（計算しません／等級 UNKNOWN／実績枠の候補）は数えない。**基準スナップショットで前回の one_step と件数が一致するか先に確かめる**（今回 19＝10/17 と一致）
- ledger_refresh は1回6〜7分。dry-run・本番・dry-run を1コマンドに繋ぐと Bash の10分上限を超える → 分けて打つ

## 気づき
- 🔴 **実画面で #7「新品n件」を取っても #10 は動いていなかった。**share_gate は Keepa の buyBoxEligibleOfferCounts か offer_check_*.csv（FBA／即納の自己発送の内訳）しか見ず、cart_check の「新品出品者数(出品一覧)」は列表示にしか使っていなかった。今夜の59件中35件が「出品者の内訳が取れない（Keepa 生データなし）」で止まっていた
- 直し方＝**上限と下限で挟む**。下限＝月販÷(n+1)（n件全部を競合とみなす）、上限＝月販÷1（競合ゼロ）
  - 下限で PASS → PASS
  - 上限でも基準3個未満 → 通常は確定 FAIL。ただし実績枠（月1個以上）は info["share"] で見るので、下限が1以上か月販が1未満のときだけ FAIL。その間（下限<1≦月販<3）は UNKNOWN
  - それ以外の FAIL（月販≧3）は UNKNOWN（取り寄せ型を除いた内訳を数えれば決まる）
- 台帳の列「新品出品者数(画面実数)」に「カート対象 FBA n」と書かないこと（人は内訳を数えていない）。info に bound=True・human=False を立てて列の書き方を分けた
- 結果：UNKNOWN 323→299（24行が #10 確定 FAIL で NO-GO）。どれも月販0.3〜2.7個（キーゾン再現値）で、競合ゼロでも基準3個に届かない
- キーゾン表が出ない3件（B00Z9I3H08・B017SK20A2・B078X35J1D）は再現式でも埋まらない：Keepa の3か月の売れ筋ランク観測が0回（10/4・10/11 取得とも）。キーゾンが表を出さない理由と同じ。0個とは書けないので #9 未確認のまま
- 「Amazon 上のスーパー（ライフ・成城石井）だけがカート」は TSV で #5 UNKNOWN（カートなし）として来るので、importer はそのまま N で取り込む。Amazon フレッシュは保持者 Amazon.co.jp＝本体 FAIL
