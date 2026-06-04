---
ticket_id: T-20260603-005
title: 初回フル外注の実務設計（FBA納品代行業者調査＋卸→代行→FBA フロー＋損益織り込み）
status: waiting
assignee: researcher
priority: high
created_at: 2026-06-03
updated_at: 2026-06-03
requires_approval: false
parent_ticket: T-20260520-004
labels: [outsourcing, fba, prep-center, research, axis-b]
next_check_at: 2026-06-04
---

## 背景

社長が「初回からフル外注（A案）」を確定（2026-06-03）。1周目から検品・ラベル貼り・梱包・FBA納品を代行業者に任せ、卸→代行業者→FBA の物流で社長はPC上で発注・指示のみ＝完全PC完結。
これを実行可能にする実務設計（代行業者の選定・費用感・物流フロー・損益への織り込み）を作る。

## 参照

- memory: owner_pc_complete_outsourcing.md（PC完結・初回フル外注A確定）
- memory: knowledge_dennou_sedori_system.md（外注化・システム型物販）
- workspace/output/deliverables/T-20260603-001/step2-procurement-decision.md（B=NETSEA等の卸）
- workspace/output/deliverables/T-20260603-002/price-diff-research-guide.md（損益計算の型）

## 成果物（予定）

`workspace/output/deliverables/T-20260603-005/` に md＋html。
- FBA納品代行業者（プレップセンター）とは／主要業者の費用感・選定基準
- 卸(NETSEA等)→代行業者→Amazon FBA の物流フロー（社長=PC発注/指示のみ）
- 損益への織り込み（仕入値＋卸送料＋代行費＋FBA手数料＋保管料 vs 販売価格）
- 初回の具体段取り／注意点

## ログ

- 2026-06-03 社長「Aで初回からフル外注」確定で起票・着手。サトルに発注。
- 2026-06-03 **番号衝突を検知・解消**：起票時の T-20260603-004 は別セッションのロゴ制作チケットと衝突していたため、本チケットを **T-20260603-005 にリネーム**。deliverables も T-20260603-005/ へ分離（full-outsourcing-design.md/.html）。ロゴ成果物は 004 に残置。
- 2026-06-03 サトルが実務設計を md＋html で納品。**重要要確認**：サトル記述「FBA代行は大口契約必須・小口不可」は裏取り必要（Amazon FBA自体は小口でも利用可のはず＝業者固有条件か誤認の可能性）。カズヨが社長へ要確認として提示。
- 2026-06-03 カズヨが WebSearch で裏取り → **「小口でFBA不可」は誤り＝小口でもFBA利用可**（複数ソース）。ただし小口の制約あり（在庫保管0.28㎥・月49点・1点100円・出品/広告ツール不可・出品許可申請不可）。本質論点＝**フル外注は固定費が乗り少量だと激しく割高**（サトル試算 月20個で利益69円/率2.5% vs 月150個で306円/率11%）→「体験1周＝少量学習」と「フル外注＝要数量」がトレードオフ。数量確保（小さく本番）か、初回だけ自己納品にするかの判断を社長へ提示。

## 社長判断待ち

初回フル外注の実務設計を確認のうえ、**「少量でも割高を許容してフル外注を貫く」か「フル外注を活かすため初回からある程度の数量で小さく本番にする(大口切替も視野)」か**を判断。詳細フロー＝`deliverables/T-20260603-005/full-outsourcing-design.html`。
