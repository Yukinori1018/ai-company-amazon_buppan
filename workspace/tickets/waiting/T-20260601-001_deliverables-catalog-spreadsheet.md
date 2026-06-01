---
ticket_id: T-20260601-001
title: 成果物カタログ（Googleスプレッドシート）作成＋成果物のたび自動更新する運用の確立
status: waiting
assignee: general_affairs
priority: high
created_at: 2026-06-01
updated_at: 2026-06-01
requires_approval: false
labels: [catalog, index, spreadsheet, google-sheets, ops, local-only]
related_tickets: [T-20260531-002, T-20260520-010]
next_check_at: 2026-06-02
environment: local-only
---

## 要件（社長依頼・2026-06-01）

成果物が各チケットのフォルダに散らばっていて「どこに何があるか」が分からない。あとで読み返しにくい。
→ **ToDo（チケット）に対応づけて、成果物のタイトル・内容・アウトプットURL が一覧で分かる「スプレッドシート（まとめ表）」を作る。**

- 社長の言葉:「スプレッドシートで管理するのが一番いい」「ToDoに合わせて横にURLをくっつけてほしい」「タイトルと内容とアウトプットが並んでいる状態に」「必要だと思うものは足してOK」
- **重要な運用条件: 成果物ができるたびに、こちら（私）が自動でこの表を更新する。**

## なぜ local-only か（このチケットの前提）

- 社長の希望は **本物の Google スプレッドシート**。クラウド実行環境では Google Sheets に繋げない（ブラウザOAuth不可・Google APIへのネット接続不可）。
- → **ローカル（社長Mac）のセッションで実施**。社長判断（2026-06-01 A/B/C で「ローカルでGoogleスプレッドシート」を選択）。

## 担当の分担（ルーティング）

- **タカシ（IT エンジニア）**: ローカルで Google Sheets 連携をセットアップ（下記いずれか）。OAuth のクリックだけ社長に依頼。
  - 案1: Google Sheets MCP サーバを `.mcp.json` に追加（OAuth）
  - 案2: サービスアカウント or OAuth credentials ＋ `gspread`（Python）で読み書きするスクリプト
  - → 初心者の社長負担が最小な方をタカシが判断して提案（A/B＋推奨）
- **マリエ（庶務）**: 連携が通ったら、下記の列設計でスプレッドシートを構築＋既存成果物を流し込み。以後の更新運用も担当。
- **カズヨ（秘書）**: 起票・統合・社長報告。成果物が出るたびに「カタログ更新」をマリエに発注（または運用フック化をタカシに相談）。

## 列設計（カズヨ案・社長の「必要なら足して」を反映）

| 列 | 内容 |
|---|---|
| チケットID | 紐づくチケット（T-2026...） |
| ToDo / タスク名 | そのチケットの目的 |
| 成果物タイトル | 個別アウトプット名 |
| 内容（要約） | 何が書いてある資料か 1〜2行 |
| 種別 | 図 / レポート / CSV / HTML / コード / テンプレ |
| アウトプット（リンク） | GitHub該当ファイルURL ＋ リポジトリ相対パス（両方。後者はブランチ削除に強い） |
| 担当 | 作成したエージェント |
| 形式 | md / png / csv / html / py |
| 作成日 / 更新日 | — |
| 社長レビュー | 済 / 一読 / 未 |
| 備考 | 補足・関連 |

> 必須3列（タイトル・内容・アウトプット）は社長指定。残りはカズヨ追加分。ローカルで社長と最終確認のうえ確定。

## 自動更新の運用（このチケットの肝）

- 「成果物カタログは成果物が出るたびに更新する」を**ルール化**し、CLAUDE.md / 庶務スキルに追記する（マリエの定常責務）。
- 可能なら **`workspace/output/deliverables/` への新規ファイル追加を検知してリマインドするフック**をタカシが作る（ticket-notion-sync-reminder.sh の類似実装）。
- 真実＝リポジトリの成果物ファイル。スプレッドシートはその可視化（片方向ミラー）。

## 既存成果物の棚卸し（2026-06-01 時点・流し込みの種）

> マリエはこれをベースに「主要成果物」を選び、材料ファイルはグルーピングして整理する。

- **T-20260520-003 ツール網羅調査（軸A）**: README, 01_keepa, 02_sellersprite, 03_amasearch, 04_fba-calculator＋ `v2_ai-integration/`（AIネイティブ5本）
- **T-20260520-012 仕入れ先・方法 調査**: README, 01_procurement-methods-comparison, 02_beginner-10man-shortlist, 03_suppliers-by-method, 04_issues-for-planner
- **T-20260521-001 用語集**: glossary.md / glossary.csv（150語）
- **T-20260521-002 仕入れ〜販売シミュ(FBA)**: playbook-final.md/html, accounting-simulation, legal-fba-compliance, simulation-numbers.csv, purchase-log-template.csv, restricted-categories.csv, **suppliers-list.md/csv（30社）**
- **T-20260521-003 Ama-Jack 評価**: integrated-summary, legal/accounting/general-affairs-amajack-review, owner-supplementary-info
- **T-20260521-005 Sato-Scope（Phase2中止）**: README, 01_tool-overview, 02_mockup.html, 03_research-and-strategy, 04_api-key-setup-guide, code/
- **T-20260522-004 Sato-Scope ROI**: roi-analysis.md, roi-numbers.csv
- **T-20260522-005 API ToS最終確認**: README, 01_official-api-tos, 02_affiliate-asp-tos, 03_implementation-requirements
- **T-20260531-002 業務フロー図**: 01_overview-flow(.md/.html/.png), 02_sourcing-flow.png/02_sourcing-todo.md, 03_restriction-release-flow.png, 04_listing-fba-flow.png/04_listing-fba-todo.md, 05_setup-flow.png/05_setup-todo.md, 99_reference_listing-restriction-release-manual.md, draw_*.py/flow_lib.py

（フルパス一覧はこのコミット時点で `find workspace/output/deliverables` で再取得可能）

## 社長アクション待ち（waiting 理由）

1. **このセッションを終了し、ローカルで Claude Code を開く**
2. 「**成果物カタログ（スプレッドシート）を作って**」と再依頼（このチケット T-20260601-001 を指す）
3. タカシが提示する Sheets 連携の **OAuth 認証クリック**（数十秒）だけ対応
→ 以降はマリエが構築・社長と列の最終確認 → 自動更新運用へ

## ログ

- 2026-06-01 起票。社長依頼を受領。クラウドでは Google Sheets 不可のため local-only と判定、社長が「ローカルでGoogleスプレッドシート」を選択。ローカル再開用に要件・列設計・棚卸し・分担を整備して waiting（社長のローカル再依頼＋OAuth待ち）
