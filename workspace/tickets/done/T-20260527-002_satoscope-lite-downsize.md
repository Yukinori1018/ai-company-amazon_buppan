---
ticket_id: T-20260527-002
title: Sato-Scope Lite 縮退（Phase 2中止・独自2軸のみ）
status: done
assignee: it_engineer
priority: high
created_at: 2026-05-27
updated_at: 2026-06-01
requires_approval: false
labels: [dev, tooling, satoscope, hybrid-strategy]
related_tickets: [T-20260521-005, T-20260527-001]
parent: T-20260521-005
restored_from: notion
---

> **2026-06-01 復元メモ:** 本チケットは Notion 側にのみ存在していた「幽霊チケット」（ローカル/Web セッション分裂による push 漏れ）。社長承認のもと Notion 本文を正としてリポジトリへ復元（T-20260531-001 同期復旧の一環）。納品コード本体（sato-scope-lite/）は当時のセッションでローカル/別worktreeに生成されており、リポジトリへの取り込みは要確認（下記「復元時の留意」参照）。

## 背景
社長承認の **B案ハイブリッド戦略**（2026-05-27）により、Sato-Scope は ERESA PRO で代替不可な独自2軸だけを保持する形に縮退。

## 残す独自価値（ERESA で代替不可）
- **D4 真の利益計算（MSS = 自己発送最低許容販売価格）** — calc/profit.py
- **D8 コンプラ警告（11ブランド警告マスタ）** — compliance/brand_warnings.py
- **D3 ポイント還元込み実質価格（楽天 SPU・PayPay）** — calc 内一部

## 捨てる範囲（ERESA で代替可）
- Discovery 系（/search API、抽出ロジック、HTML モック）
- Keepa／楽天／Yahoo! アダプタ（ERESA が内包）
- 独自おすすめスコア（D5）

## 作業内容（タカシ担当、約2日）
1. **archive 退避**: Phase 1 コードを archive/satoscope-phase1/ へ退避
2. **sato-scope-lite/ 新設**: ERESA CSV → MSS／実質価格／コンプラ警告を付与する薄い CLI
3. **テスト全通過**: pytest で動作確認
4. **使い方ガイド納品**: 副業初心者にも分かる平易な日本語で説明

## ✅ 2026-05-27 完了報告（タカシ）
pytest 12/12 PASS、サンプル CSV で CLI 実動作確認済み（Sony 警告・MSS 最適判定も発動）。

**納品物（当時の記録）**
- Phase 1 退避: `workspace/output/deliverables/T-20260521-005/archive/satoscope-phase1/code/`
- Lite 本体: `workspace/output/deliverables/T-20260527-002/sato-scope-lite/`
  - cli.py / calc/profit.py / calc/effective_price.py / compliance/brand_warnings.py
  - tests/test_profit.py / sample_eresa.csv / README.md / requirements.txt
- 社長向け使い方ガイド: `~/Documents/AI Company Outputs/Amazon物販事業/T-20260527-002/usage-guide.md`
- ERESA 実 CSV のスキーマ判明時は `cli.py` の `COLUMN_ALIASES` 差し替えで対応可能

## 復元時の留意（2026-06-01）
- 本チケットは done として復元したが、**コード本体 `sato-scope-lite/` がリポジトリに未取り込みの可能性**がある（生成セッションが push 漏れしていたため）。
- 対応: 次にローカル Mac セッションを開いた際、`workspace/output/deliverables/T-20260527-002/` の有無を確認し、無ければ再生成 or ローカルから push する（T-20260531-001 の残課題に紐づけ）。

## ログ
- 2026-05-27 起票・即着手・done（タカシ、pytest 12/12 PASS）
- 2026-06-01 Notion からリポジトリへ復元（同期破綻の復旧）。コード本体の取り込みは要確認として明記
