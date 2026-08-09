---
ticket_id: T-20260806-003
title: 就労支援施設向け 作業業務マニュアル（Amazon FBA梱包・ラベル貼り／編集可能テンプレ）
status: waiting
assignee: content_creator
priority: high
created_at: 2026-08-06
updated_at: 2026-08-09
requires_approval: false
parent_ticket: T-20260806-001
labels: [outsourcing, shurou-shien, manual, fba, content, editable]
next_check_at: 2026-08-12
---

## 背景

社長依頼（2026-08-09）：就労支援施設（大田区。候補は T-20260806-001 参照）へ委託する梱包・ラベル貼り作業の**業務マニュアル**を作る。施設の作業員さん・支援員さんが読んで作業できるもの。
社長が今後修正する前提のため、**編集しやすい形式**で納品する。

## 要件

- 読み手＝就労支援施設のスタッフ／作業員（Amazon物販の専門知識ゼロ前提。専門用語は避ける or 図解）。
- 社長が実運用に合わせて直せる**テンプレート形式**：確定していない項目は `【要記入】` プレースホルダーで明示（数量・資材の支給方法・受け渡し方法・連絡先など）。
- 内容：①作業の目的と全体像 ②用意するもの/資材 ③作業の流れ（受取→検品→梱包→ラベル貼り→保管→引き渡し）④各手順の詳細（写真差し込み枠つき）⑤品質基準（OK/NG例）⑥FBA特有の注意（バーコード=ASIN/FNSKUラベル、バーコード隠し、セット/危険物の扱い等を平易に）⑦数量・納期・受け渡し ⑧記録表（作業数・不良数）⑨困った時の連絡。
- セミナー(2026-06-10)の外注化パート・§8.5、および T-20260603-005 のフル外注設計に準拠。

## 参照

- workspace/output/deliverables/T-20260603-005/full-outsourcing-design.md（フル外注・FBA納品前準備の設計）
- workspace/output/deliverables/T-20260806-001/（候補施設・打診テンプレ・訪問チェックリスト）
- docs/reference/maker-shiire/seminar-20260610-realtime-notes.md（外注化・池田さんの委託マニュアル事例）

## 成果物（予定）

- `workspace/output/deliverables/T-20260806-003/facility-work-manual.md` / `.html`（編集可能な素・印刷可能なHTML）
- Google ドキュメント版（社長が直接編集・施設へ共有できる形）※カズヨが Drive に作成

## 編集可能性の担保

- md＝真実（Git管理で改訂履歴が残る）。HTML＝配布/印刷用。Google Doc＝社長が直接手を入れて施設へ渡す用。
- 改訂時は md を直す→HTML/Doc に反映、の一方向運用。

## 現在地

ヒデアキ（コンテンツ制作）が md／html の初版を作成し deliverables に配置完了。カズヨの社長レビュー待ち（＋Google Doc 版作成の素として利用可能）。

## ログ

- 2026-08-09 ヒデアキ着手。参照3件（T-20260603-005 フル外注設計／T-20260806-001 候補・打診・訪問CL／セミナー§8.5）読了。
- 2026-08-09 全10章の編集可能マニュアルを作成。md（素）＋ A4印刷用HTML（写真枠=点線、OK/NG=色分け、記録表・改訂履歴つき）を deliverables に配置。【要記入】プレースホルダーは md／html とも34箇所で一致。doing のまま留置（done移動は秘書）。

## 成果物

- workspace/output/deliverables/T-20260806-003/facility-work-manual.md（編集の素・真実。改訂履歴表を含む）
- workspace/output/deliverables/T-20260806-003/facility-work-manual.html（印刷・配布用。A4想定・インラインCSS）

> ※本セッションはクラウド想定のため deliverables（リポ内）に配置。PC復帰時に `~/Documents/AI Company Outputs/Amazon物販事業/T-20260806-003/` へ移し替え、Google Doc 版はカズヨが Drive に作成。

## 完了報告

カズヨさんへ。就労支援施設向けの梱包・ラベル貼り作業マニュアル（第1版）を md／html で納品しました。読み手は「Amazon物販の知識ゼロの支援員・作業員」を最優先に、短文・箇条書き・ふりがな・OK/NG対比で組んでいます。確定していない項目は全て `【要記入】`（34箇所）で残し、社長が実運用に合わせて埋められる形です。完成度は初版として自信を持って出せる水準ですが、「写真差し込み（現状は点線枠のみ）」と「危険物・セット商品の個別指示」は社長の実商品が決まらないと埋まらない箇所として意図的に空けています（妥協点として明示）。完了しました。確認お願いします。

## Google Doc 版（社長が直接編集・施設へ共有できる形）

- タイトル「【就労支援施設むけ】梱包・ラベル貼り 作業マニュアル（第1版・編集用）」
- URL: https://docs.google.com/document/d/1xnhzsLCqcDryR_UG1TnG2FT19axjxnFRrqp2ynMP15I/edit
- 2026-08-09 カズヨが md をベースに Drive 化。社長が【要記入】34箇所を埋め、施設へ共有。改訂は md（真実）を直す→HTML/Doc に反映の一方向運用。

## waiting の理由（社長の番）

社長レビュー＋【要記入】34箇所の記入待ち（資材の支給方法・数量/納期・受け渡し・連絡先・商品別の個別指示など、実運用に合わせて社長が確定）。写真は実商品が1つ決まったら差し込み枠6箇所に撮影・挿入。
