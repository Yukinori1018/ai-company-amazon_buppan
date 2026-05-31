---
ticket_id: T-20260529-001
title: Amazon物販 業務フロー図の作成（全体→詳細→仕入れ深掘り）
status: doing
assignee: secretary
priority: high
created_at: 2026-05-29
updated_at: 2026-05-29
requires_approval: false
labels: [flowchart, process, sourcing, onboarding]
related_tickets: [T-20260520-004, T-20260521-002, T-20260520-012]
next_check_at: 2026-05-30
---

## 要件

社長依頼（2026-05-29）: Amazon物販事業の業務フローを図で可視化する。

1. **まず大きな流れ**をフロー図にして共有する（社長確認のうえ次へ）
2. その後、各段階を**ToDo レベルまで細分化**して図で表す
   - 例: 仕入れ段階なら「どんな準備が必要か」「どこに登録が必要か」まで
3. 対象は **Amazon物販に限定**
4. 社長が最も迷っているのは **「仕入れ」** の部分 → ここを最も詳しく
5. 仕入れの深掘りから発展させ、**仕入れ先リストをスプレッドシート化**（連絡先・取扱商品をまとめる）
6. 販売規制（出品制限）の解説資料（社長提供）を参照に組み込む

## 社長提供インプット

- **出品制限解除マニュアル**（動画分析テキスト）→ `99_reference_listing-restriction-release-manual.md` に保存
- 既存資産: `T-20260521-002/suppliers-list.md`（庶務マリエ作「仕入れ先カタログ30件」）を仕入れ先リストの土台に流用

## 進め方（フェーズ）

- [x] Phase 0: 既存仕入れ資料の棚卸し・規制マニュアル保存
- [ ] **Phase 1: 大きな流れのフロー図**（全体像）← 社長確認ポイント①
- [ ] Phase 2: 各段階の ToDo 細分化フロー図（準備・登録先まで）
- [ ] Phase 3: 仕入れ段階の最深掘り（出品制限確認→解除→発注の判断フロー）
- [ ] Phase 4: 仕入れ先リストのスプレッドシート化（連絡先・取扱商品・条件）

## 成果物の置き場

- 作業中: `workspace/output/deliverables/T-20260529-001/`
- 形式: Markdown（Mermaid 図、GitHub で描画）＋ HTML（ブラウザ描画）の併出（社長プロファイル準拠）

## ログ

- 2026-05-29 起票。社長依頼受領。規制解除マニュアルを reference 保存。Phase 1（全体フロー）に着手
- 2026-05-29 全体フロー初版を Mermaid(md/html) で作成 → 社長環境で描画されず。matplotlib+IPAGothic で確実表示の PNG に作り替え（`01_overview-flow.png`）
- 2026-05-29 社長指摘で改訂: クレーム対応・評価確認を独立並走フロー「12. アフターフォロー」＋「アカウントヘルス」として追加（PNG/md 反映）。Phase 2 着手待ち（仕入れ周りから細分化が有力）
- 2026-05-31 社長選択で「仕入れ周りから」着手。②仕入れ判断フロー(`02_sourcing-flow.png`)・③出品制限の3段階解除フロー(`03_restriction-release-flow.png`)・ToDoチェックリスト(`02_sourcing-todo.md`)を作成。描画共通ライブラリ `flow_lib.py` 化。仕入れ先スプレッドシートは既存 `T-20260521-002/suppliers-list.csv`（30社）を参照する形に統合（重複作成回避）
</content>
