---
ticket_id: T-20260824-003
title: Keepa monthlySold のメモリ記述を公式定義＋保存済み実データで突合・補足
status: done
assignee: it_engineer
priority: low
created_at: 2026-08-24
updated_at: 2026-08-24
requires_approval: false
labels: [keepa, memory, data-quality]
parent_ticket: T-20260824-001
related_tickets: [T-20260824-001, T-20260817-005, T-20260803-001]
---

## 要件

IT エンジニア タカシの memory `agents/it_engineer/memory/knowledge_keepa_product_finder_fields.md` にある
`monthlySold` の実測観察（「月50個以上の商品にしか出ない」等）を、T-20260824-001 で確定した Keepa 公式定義
（bought past month の実測値・推定値ではない／"10+" 等の階級値／大半のASINで欠測／バリエーション単位）と突合し、
保存済み raw JSON の実データで裏を取ったうえで、**上書きではなく補足・明確化**する。

## タスク分解

- [x] memory の `monthlySold` 関連記述を読む
- [x] T-20260824-001 の keepa-glossary.md / discrepancies.md(D6) の公式定義と照合
- [x] T-20260817-005/raw/ の保存済み JSON で monthlySold の値の分布を集計（**消費トークン 0**）
- [x] 「月50個以上にしか出ない」が階級値のどの下限に対応するか実データで判定
- [x] 整合するなら補足追記／食い違うなら実データ根拠つきで修正 → **一部要修正だったため根拠つきで修正**
- [x] 集計スクリプトと結果を deliverables に残す

## 現在地

**タカシ完了。秘書レビュー待ち。** 公式定義（階級値・大半欠測・推定値ではない）は実データと完全に整合。
一方で memory の「月50個以上にしか出ない」は**実データが否定**したため、根拠つきで修正済み。

## ログ

- 2026-08-24 doing 起票（社長指示。T-20260824-001 の派生・緊急性低）
- 2026-08-24 タカシ着手。`T-20260817-005/raw/*.json.gz`（4,002 ASIN）を集計。**Keepa API は未使用＝0トークン**
- 2026-08-24 現在値は 11 種類の階級値のみ・欠測 66.5% を確認 → 公式定義と一致
- 2026-08-24 `monthlySoldHistory` に 10/20/30/40 と `-1`（欠測マーカー）が実在することを発見 → 「50未満は出ない」は誤りと判定
- 2026-08-24 memory `knowledge_keepa_product_finder_fields.md` を修正・成果物を deliverables に直納・commit

## 成果物

- workspace/output/deliverables/T-20260824-003/README.md
- workspace/output/deliverables/T-20260824-003/monthly-sold-distribution.md
- workspace/output/deliverables/T-20260824-003/monthly-sold-distribution.html
- workspace/output/deliverables/T-20260824-003/analyze_monthly_sold.py
- workspace/output/deliverables/T-20260824-003/analyze_output.md
- agents/it_engineer/memory/knowledge_keepa_product_finder_fields.md（更新）

## 完了報告

カズヨさん、完了しました。**Keepa API の消費トークンは 0** です（保存済み raw JSON のみ）。

**結論は3つです。**

1. **公式定義は実データと完全に整合しました。** 4,002 ASIN の現在値に出た `monthlySold` は
   `50/100/200/300/400/500/600/700/800/900/1000` の **11 種類だけ**。連続値はゼロで、
   公式の「区切られた範囲でしか提供しない」どおりでした。欠測も **66.5%**（2,663件）で
   「大半のASINには値が無い」も一致。**D6 の指摘は正しかった**とデータ側から確認できました。

2. **一方で、私の memory の「月50個以上の商品にしか出ない」は誤りでした。** 現在値の最小は
   確かに 50 でしたが、**同じ商品の `monthlySoldHistory` に 10/20/30/40 が実在**します
   （1〜49 を履歴に持つ ASIN が **1,732/4,002**）。しかも 1〜49 は **2025-04〜05 と 2026-02〜03
   に集中して現れ、その前後では完全に消えます**（最終観測 2026-04-28）。つまり 50 は Keepa の
   仕様上の下限ではなく、**スキャンした時期のたまたまの下限**でした。`>= 50` を前提にした
   コードを書くと、Amazon の表示ポリシーが戻った瞬間に壊れます。

3. **「値が無い＝売れていない」ではありません。** ドロップ数49で欠測、ドロップ数9で値50、という
   実例が両方ありました。欠測を足切りに使うと誤判定します。

**memory は上書きではなく、経緯を残す形にしました。**「以前はこう書いていた／実データで再検証した
結果こうだった」を表で並べ、出典として T-20260824-001 の公式定義と本チケットの実測ファイルを
両方入れています。

**1件、本チケットの範囲外の申し送りがあります。** 同じ memory の別の行に
「`stats.min[i]` は `stats=N` の **N日間**の最小値」という記述が残っていますが、
T-20260824-001 の `keepa-glossary.md` は「`min` は**全期間**の最安値。期間内は `minInInterval`」と
確定させています。**ここは未修正です**（スコープ外のため手を付けませんでした）。
`scan_v13.py` の「過去1年最安値」列と損益分岐の全行に効く話なので、別チケット化を推奨します。
- 2026-08-24 doing タカシに発注
- 2026-08-24 done 完了。4,002 ASIN を保存済み raw JSON で集計（Keepa 0トークン）。
  公式定義（階級値・大半欠測）は実データで裏取り成功。一方「月50個以上にしか出ない」は
  **要修正**と判定（履歴に 10/20/30/40 が実在・1,732/4,002）。「300件中233件=78%」も
  母集団全体では 33.5% に修正。memory に経緯を残す形で反映。commit 2ccba5e。
  カズヨが同じ raw JSON を独立集計して数値一致を確認。
- 2026-08-24 申し送り: `stats.min` の期間解釈の取り違え疑いを T-20260824-004 として分離起票。
