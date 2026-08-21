---
ticket_id: T-20260706-002
title: Sato-Scope に brand/manufacturer を恒久搭載（メーカー抽出の再実行不要化）
status: done
assignee: it_engineer
priority: medium
created_at: 2026-07-06
updated_at: 2026-07-06
completed_at: 2026-07-06
renamed_from: T-20260706-001
requires_approval: false
labels: [dev, sato-scope, maker-shiire]
parent_ticket: T-20260521-005
related_tickets: [T-20260705-002]
---

## 背景

T-20260705-002（メーカー仕入れワークフロー）で、サトルは raw Keepa product から brand→manufacturer を
直読みしてメーカー名を得た（`research/extract_maker_candidates.py`）。理由は Sato-Scope の
`adapters/amazon_data._product_to_amazon()` が Keepa raw の brand/manufacturer を捨てており、
`AmazonProduct` に該当列が無かったため。これを恒久策として本体に取り込み、メーカー仕入れ用の
抽出を「リサーチ再実行なし」で discover_by_finder 出力から取れるようにする。

## タスク分解

- [x] `AmazonProduct` dataclass に `brand` / `manufacturer` フィールド追加（既定 None）
- [x] `AmazonProduct.maker` プロパティ（brand > manufacturer の優先。サトル `_brand_of` と同順）
- [x] `_product_to_amazon()` で Keepa raw の brand/manufacturer をマッピング（追加トークン0）
- [x] `SampleBackend._load()` も brand/manufacturer を拾う（サンプル経路でも整合）
- [x] `DiscoveryRow` に `maker` フィールド追加（既定 ""）、全構築5箇所で `ap.maker` を付与
- [x] `discover_by_finder` の出力（DiscoveryRow.maker）にメーカー名が乗ることを確認
- [x] app_discovery のランキング表に「メーカー」列を追加（社長が一目で見える）
- [x] 既存 pytest を壊さない（せどり用フローは brand/manufacturer 未使用でも動く）
- [x] 新規テスト追加（brand優先／manufacturerフォールバック／DiscoveryRow.maker伝播）

## 完了条件

- 既存テスト全通過 ＋ 新規テスト通過
- メーカー抽出が Keepa 再クエリなしで DiscoveryRow から取得可能

## アウトプット

`workspace/output/deliverables/T-20260521-005/code/` 配下を直接改修（Sato-Scope 本体）。
- 2026-08-21 **番号衝突を解消し T-20260706-001 → T-20260706-002 へ改番**（マリエ実施・カズヨ承認）。買い候補ショートリスト（`waiting/T-20260706-001_gem-vetting-and-buy-shortlist.md`）と ID が衝突していた。Notion カードが買い候補側のものであるため、**買い候補が旧IDを保持**し、本チケットを改番した。
  過去の会話・成果物・Notion 履歴に旧ID **T-20260706-001** が残っている場合は本チケットを指す。
