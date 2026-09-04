---
ticket_id: T-20260904-002
title: ホームページ制作事業リポジトリの雛形生成（本リポの運用ルールを転用）
status: doing
assignee: it_engineer
priority: high
created_at: 2026-09-04
updated_at: 2026-09-04
requires_approval: false
labels: [ops, foundation]
parent_ticket: ""
next_check_at: 2026-09-05
related_tickets: []
---

## 要件

社長から「このリポで決めたルール・運用方法をコピー（必要に応じて修正）して、別プロジェクトに転用できる専用フォルダを作れ」との依頼。作成後は社長が手動でフォルダごと移設する。

- **転用先事業:** ホームページ作成のためのリサーチ・制作事業
- **持ち出す範囲:** 骨格ルール ＋ 汎用ナレッジ（Amazon/Keepa/物販固有のメモリ・成果物・チケットは除外）
- **生成先:** `/Users/yukinori/Claude Code/ai-company-homepage/`（**本リポの外**。本リポは PUBLIC かつ30分毎に `git add -A` → push するため、内側に作ると巨大な複製が公開される）

## タスク分解

- [x] 生成先フォルダを本リポ外に作成し、ディレクトリ骨格を敷く
- [x] CLAUDE.md を新事業向けに書き換えて配置（§1 を HP 制作事業に、Amazon 固有の記述を除去）
- [x] agents/ 9職種の agent.md を移植（Amazon 固有の例示のみ差し替え）
- [x] 汎用ナレッジのみメモリを選別移植（残 69 / 元 112）
- [x] .claude/（hooks / commands / agents / settings）を移植・パス依存の修正
- [x] workspace/ 骨格を移植し中身は空に（handover.md / owner-tasks.md は空の雛形として作り直し）
- [x] docs/（notion スキーマ・セットアップ・playbook）と scripts/ を移植
- [x] .gitignore / .mcp.json.example / README.md を新事業向けに調整
- [x] 引き継ぎメモ SETUP.md を新フォルダ直下に置く
- [ ] 秘書が受け入れ確認 → 社長へ報告

## 現在地

2026-09-04 タカシ作業完了。`/Users/yukinori/Claude Code/ai-company-homepage/` に163ファイルを生成。
検証（bash -n 7本 / フック実行 5本 / Python 3本 / JSON 4本 / リンク切れ0 / 秘密スキャン）すべて通過。
**秘書の受け入れ確認待ち。** 社長判断が必要な論点は4件（下記「完了報告」）。

## ログ

- 2026-09-04 doing 起票（社長依頼を受け即着手）
- 2026-09-04 マリエ：Notion カード作成（Status=doing）。labels を [ops, template] → [ops, foundation] に修正。Notion の Labels に `template` オプションが無く、新規オプションを勝手に作らない方針（T-20260904-001 と同じ）に従い、既存の `foundation`（骨格・基盤）へ寄せた。owner-tasks.md も ℹ️ 欄に追記（社長タスクの純増ゼロ）
- 2026-09-04 タカシ: 生成先の骨格作成 → 汎用ファイル移植 → メモリ選別（69/112）→
  スクリプト/フックのパス依存を除去 → CLAUDE.md/README.md/SETUP.md 執筆 → 全検証通過。
  コピー元リポは読み取りのみ（1ファイルも変更していない）。

## 成果物

- **本体:** `/Users/yukinori/Claude Code/ai-company-homepage/`（163ファイル。**本リポ外**。`git init` 未実施）
- **引き継ぎメモ:** `/Users/yukinori/Claude Code/ai-company-homepage/SETUP.md`
- **作業ログ:** `workspace/output/deliverables/T-20260904-002/README.md`

## 完了報告

雛形を生成しました。**本リポの外**に置いてあります（本リポは PUBLIC で30分ごとに `git add -A` push するため、
内側に作ると163ファイルの複製がそのまま公開されます）。

**完成度:** 移設してすぐ動く状態です。フック5本・スクリプト7本は構文チェックに加えて実際に叩いて
JSON が返ることまで確認しました。相対リンク切れ0件、秘密の混入なし。

**妥協点・意図的に残したもの:**

- **memory 本文の「Amazon」「Keepa」等の固有名詞は書き換えていません。** memory は過去の判断の記録であり、
  後から固有名詞を消すと「いつ・何を見てそう判断したか」が失われるためです。書き換えたのは規範側
  （CLAUDE.md / agent.md / skills / docs）だけです。
- **CLAUDE.md §1 の4項目（ミッション/KPI/主力サービス/想定顧客）はプレースホルダーのまま**です。
  社長未決定のため。空のまま戦略立案を走らせると評価軸のない案が出て手戻りになる旨を明記しました。
- 指示では `docs/reference/` は一律除外でしたが、**`web-site-build/`（サイト制作の6工程プレイブック）だけは
  持ち出しました。** 転用先事業の中核オペそのもので、機械的に従うと最も価値の高い資産を落とすためです。
  社長提供の外部資料なので、PUBLIC 運用時の第三者著作物判定は要判断として SETUP.md に明記しています。

**移設中に見つけた元リポ側の不備3件**（雛形側でのみ修正。元リポは指示通り無変更）:

1. `workspace/README.md` が旧ルール「最終納品物はリポ外」のまま更新漏れ（CLAUDE.md §6 は3層ルールに移行済み）
2. `docs/notion-setup-guide.md` の Assignee 選択肢が5職種のまま（実態は9職種＋owner）
3. `agents/general_affairs/agent.md` のリンク切れ（`skills/owner-tasks-summary-ownership.md` → 実体は `memory/` 配下）

→ **元リポ側の修正は別チケットの起票を推奨します**（本チケットの制約で触っていません）。

**社長判断が必要な論点（4件・詳細は SETUP.md §5）:**

| # | 論点 | 推奨 |
|---|---|---|
| 1 | リポジトリを PUBLIC / PRIVATE どちらにするか | **PRIVATE 推奨**。クライアントの未公開情報・支給素材・問い合わせ経由の個人情報を扱うため、先行事業よりリスクが高い |
| 2 | `docs/reference/web-site-build/` の掲載可否 | PRIVATE なら問題なし。PUBLIC にするならハルオに第三者著作物判定を依頼 |
| 3 | 成果物カタログを使うか | 使うなら移設後にシートを1枚作る。**使わないならコマンドとマリエの責務ごと外す**（更新されないカタログは無いより悪い） |
| 4 | インボイス（適格請求書）をどうするか | HP 制作は B2B なので、免税事業者のままだとクライアント側の仕入税額控除に直撃。**物販より重い論点**。ハジメへ発注を推奨 |

**引き継ぎ事項:** 移設後の最初の発注は **ハルオ（法務）** を推奨します。事業が変わると法務 memory が
ほぼ全滅し（17本 → 8本、うち HP 制作の知識は0本）、規範だけ新しくて知識がゼロの状態で走り出すためです。

完了しました。確認お願いします。
