---
name: 実画面の注記を証跡ファイルに落とす型（2026-10-19 br1019）
description: カズヨの注記（メーカー本人確定・セット数の食い違い・Amazon上のスーパーの販売数）を TSV 外の証跡ファイルで判定に効かせる方法と、one_step の数え方の再確認（T-20260920-003）
type: knowledge
---

# 実画面の注記を証跡ファイルに落とす（2026-10-19 夜間・32件）

browser_results_import.py は TSV の列しか読まない。カズヨが依頼文に書いてくる「注記」は、
次の証跡ファイルに置けば ledger_refresh が毎回合流させる（台帳セルに直書きしない）。

| 注記 | 置き場 | 効き方 |
|---|---|---|
| カートはブランド本人（確定） | `ledger20261010/cart_maker_flags_<日付>_human.csv`（ASIN,区分=確定,根拠） | #5 FAIL → NO-GO。import の maker_suspect は「疑い」止まり（UNKNOWN）なので、人が確定と言ったらここに書く |
| Amazon と台帳のセット数が食い違う | `ledger20261010/set_check_<日付>_amazonpage.csv`（Amazon1個＝卸◯点=未確定・確度=—） | #15 UNKNOWN「人の確認で未確定」・採算は計算しない。数字は直さない（§3.3-17） |
| 「過去1か月◯点以上」が Amazon 上のスーパー（LIFE 等）の売上を含む | 生成された cart_check の「過去1か月(実画面・下限)」を空欄にし注意欄に理由 | 第三者の実売の根拠にしない |

- set_check は score_20261004.set_count_of が最優先で読む（NETSEA 行でも効く）。cart_maker_flags は screen_checks.load_cart が cart_check より後に上書きする
- 注記を足したら **dry-run をもう1回**挟む（取り込みだけの dry-run と比べて、動いたのが狙いの行だけか確認）。本番はその dry-run とバイト一致を見る

## one_step の数え方（3回目の確認）
- 「【こう変えれば】」より前・「未達：」以降を「／」で割り、`(#[\d-]+)[^：／]*? (UNKNOWN|FAIL)` を数える。#18 の派生（計算しません／計算できません／等級 UNKNOWN／実績枠の候補）は除く
- unknown_stages.outstanding() をそのまま使うと #18 を数えてしまい 10/18 が 20→10 行になる。**使わない**
- 先に前夜の台帳（after_<前夜>.json）で前夜の one_step と一致するかを確かめてから今夜分を出す（今回 20行一致）

## 所要
- ledger_refresh の dry-run は1回 6〜9分。基準・取り込み後・注記後・本番・2回目で計5回＝約40分
