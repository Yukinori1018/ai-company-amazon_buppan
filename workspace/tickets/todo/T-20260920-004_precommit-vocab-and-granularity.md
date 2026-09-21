---
ticket_id: T-20260920-004
title: pre-commit フックの穴3つを埋める（会員限定の取引条件・2列時系列・散文中の金額）
status: todo
assignee: it_engineer
requires_approval: false
created_at: 2026-09-20
updated_at: 2026-09-20
next_check_at: 2026-09-22
priority: high
labels: [ops, security, tooling]
related_tickets:
  - T-20260920-003
---

## 背景

2026-09-20、SD 会員限定の取引条件（卸値・SD品番・上代・ロット・卸価格の分布）が PUBLIC リポに push された（T-20260920-003 の是正記録を参照）。pre-commit フックは通り抜けた。ハルオの [08_Keepa由来データの公開基準](../../output/deliverables/T-20260920-003/08_Keepa由来データの公開基準.md) §5-4 が穴を3つ特定している。

## タスク

- [ ] 検出語彙に `90日平均` `在庫切れ率` `上代` `卸単価` `SD品番` `最小ロット` `卸率` を追加
- [ ] md の表判定が「5列以上の表ヘッダ」しか見ておらず、**2列の時系列表**（項目｜値）が通る問題を直す
- [ ] 散文中の「卸値 ◯◯◯円」のような**金額つきの文**を捕まえる（現在は表のみ判定）
- [ ] ハルオの ABCD 分類（A=Amazonの現在スナップショット可／B=Keepa固有の履歴・派生／C=会員限定の取引条件＝Hard NO／D=認証情報）を、フックの判定と1対1に対応させる
- [ ] **ゲートを緩める方向の変更はしない。**語彙と粒度の問題として直す
- [ ] **4つ目の穴（2026-09-20 タカシ申し送り）**: `.githooks/pre-commit` が `monthlySold` をブロックするが、ハルオ 08 §55 はこれを **A クラス＝公開可（社長決定済み）** としている。語彙のズレで、成果物を書く側が列名を言い換えて通す運用になっている（実際に「購入数/月(Amazon表示)」へ改名して通した）。**group B から `monthlySold` を外す**のが推奨
- [ ] 誤検知時の逃げ道（`--no-verify`）に頼らず通せるか、法務の成果物自身で回帰テストする

## 参照

- [08_Keepa由来データの公開基準.md](../../output/deliverables/T-20260920-003/08_Keepa由来データの公開基準.md)
- `agents/legal/memory/knowledge_public_data_release_standard_ABCD.md`

---

## 現在地（2026-09-21 タカシ）

実装・テストとも完了。**チケットは `todo/` のまま置いてあります**（状態遷移は秘書の責務）。

### スコープ（宣言）

**入れたもの**
- 新設: `.claude/hooks/source-terms-guard.py`（PreToolUse: Write|Edit|MultiEdit）。`deliverables/` と `tickets/` 配下への書き込みを、書く前に exit 2 で止める
- 新設: `workspace/source-ledger.md`（出所台帳。法務 16 §5 対策1）
- 修正: `.githooks/pre-commit` の語彙（A クラスを通す／C クラスと時系列を止める）
- 新設: `.claude/hooks/tests/test_source_terms_guard.sh`（40ケース・全 pass）
- 登録: `.claude/settings.json` の PreToolUse（JSON 妥当性を確認済み）

**入れなかったもの（理由つき）**
- **git 履歴の書き換え** — §4.1・社長判断待ち。触っていません
- **pre-commit の差分範囲の拡張**（変更ファイルも見る／法務 16 §5 対策3-1・3-2） — 依頼が「不整合を1件直す」だったため別件に切り出します。書き込み経路は新フックで塞がっているので穴は残りません
- **週次の棚卸し**（法務 16 §5 対策4） — 別チケット向き。過去に入り込んだ分は commit 時のゲートでは永久に見つからないので、これは必要です
- **`卸率` を pre-commit の語彙に足すこと** — 本チケット起票時のタスクに入っていましたが、翌日の法務判定で「率は可・実額のみ不可」と確定したため足していません

### ログ

- 2026-09-21 タカシ：法務判定 16 の §4／§5 を仕様として実装。既存追跡ファイル1,242件を同じ判定で走査したところ61ファイルで発火（＝過去分の棚卸し規模の実測）。テストは `git clean -fd` が未追跡の `.githooks/` を消して「全部 pass」に見える罠を踏んだため、後片付けの方法を変えて再測定
- 2026-09-21 タカシ：`monthly_sold_real` のフィールド定義を追跡。`T-20260804-001/monthlysold_refetch.py` で Keepa の `monthlySold` をそのまま書いている列＝A クラス相当と判明。ただし**判定の変更は法務の領分なので pre-commit からは外さず残置**し、確認結果のみ報告

- 2026-09-21 タカシ：カズヨの抜き打ち8ケースで2件落ちた（どちらも当日実際に漏れた形）。①「送料無料」と書かれていない送料の境目（言い換え）②`卸`＋税抜/税込＋金額。ラベルを「語幹×修飾」の掛け合わせに作り直し、閾値の印を必須にして Amazon 側の公開情報を巻き込まないようにした。`〔` を伏せ字の印として信用する設計も外した（記号の中に実額を書く形が実在）。テストは50ケースに増やし全 pass

## 成果物

- `.claude/hooks/source-terms-guard.py`
- `.claude/hooks/tests/test_source_terms_guard.sh`
- `workspace/source-ledger.md`
- `.githooks/pre-commit`（修正）
- `.claude/settings.json`（修正）
- `agents/it_engineer/memory/knowledge_leak_detection_hook_design.md`

## 完了報告

機構は動いています。テスト40ケース全 pass（陽性: 今回漏れた4形＋全角・ロット・品番・チケット本文、陰性: 件数・Amazon の売価と手数料・率・code 引用・伏せ字済み・agent_output・法務判定書）。

**秘書への引き継ぎ2件**
1. `workspace/source-ledger.md` の「公開」区分が**空**です。T-20260903-001 で公開可と判定された2サイトのホスト名を庶務に追記させてください。ここが埋まるまで、公開ページ由来の正当な金額を書く出口が開きません
2. `monthly_sold_real` は A クラス相当だとフィールド定義で確認できました。外すかどうかはハルオの判定事項なので、判断を回してください
