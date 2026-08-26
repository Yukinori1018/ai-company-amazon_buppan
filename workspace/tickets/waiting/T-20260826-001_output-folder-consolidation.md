---
ticket_id: T-20260826-001
title: 成果物フォルダの一元化（散らばり4箇所→リポ内1箇所）
status: waiting
assignee: owner
priority: high
created_at: 2026-08-26
updated_at: 2026-08-26
requires_approval: true
labels: [整理, 運用ルール]
parent_ticket: ""
next_check_at: 2026-08-28
related_tickets: [T-20260821-009, T-20260601-001]
---

## 要件

社長ご指摘「Amazon物販事業に関するファイルの全てを `ai-company-amazon_buppan` フォルダ内で完結させたい」。
現状は成果物の置き場が4箇所に散らばり、同一チケットで内容が食い違う実害が出ている。リポ内 `workspace/output/deliverables/` を唯一の正とし、残りを畳む。

## 前提（社長ご判断・2026-08-26）

- **リポジトリは PUBLIC のまま継続**（2026-08-24 のご判断を再確認）。「現状は公開しても良い情報ばかり」との認識。
- したがって本チケットで**機微情報の一括除外はしない**。ただし以下2つは例外として除外を継続する:
  - **本人特定情報**（住所・電話番号・口座番号）＝ `.gitignore` の `公開用/` `会社概要_配布用/` を維持
  - **APIキー・シークレット** ＝ 既存の `.env` `.mcp.json` 除外を維持
- **大容量バイナリはリポに入れない**（GitHub の1ファイル100MB上限）。リポ外の素材置き場へ。

## 現状（2026-08-26 調査結果）

| | 場所 | 中身 | Git | 容量 | 判定 |
|---|---|---|---|---|---|
| A | `リポ/workspace/output/deliverables/` | 48チケット・385ファイル追跡 | 追跡 | 856M | **正とする** |
| B | `リポ/workspace/output/agent_output/` | 18チケット・途中経過 | 除外 | 138M | 現状維持 |
| C | `~/Documents/AI Company Outputs/Amazon物販事業/` | 21チケット・全件Aと重複・独自0件 | リポ外 | 8.9M | **畳む** |
| D | `~/Claude Code/AI Company Outputs/Amazon物販事業/` | 11チケット＋動画・7/6で更新停止 | リポ外 | 5.7G | **畳む** |

- C と A で内容が食い違うチケットあり（T-20260817-004 の2ファイル）＝二重管理の実害
- D のユニーク分は **T-20260520-005 のみ**
- D の 5.7G の正体は `画面収録 2026-06-10 11.11.48.mov`（5.6GB・メーカー仕入れセミナー録画）1本
- CLAUDE.md §6 は「最終納品物は `~/Documents/...`」と記載しているが、実態は A。ルールと実態が乖離

## タスク分解

- [x] C と A の全21チケットを突合し、差分ファイルを特定。新しい/正しい方を A に残す
- [x] C を `~/Documents/AI Company Outputs/_archive_20260826/` へリネーム退避（**削除しない**＝§4.1）
- [x] D のユニーク分 T-20260520-005 を A へ移送
- [x] D の 5.6GB 動画を `~/Documents/AI Company 素材/Amazon物販事業/` へ移動（素材置き場を新設・README添付）
- [x] D の残り（Aと重複）を `_archive_20260826/` へ退避
- [x] 社長の閲覧口を確保：`~/Documents/AI Company Outputs/Amazon物販事業` を A へのシンボリックリンクにする（Finderブックマークが従来どおり効く）
- [x] `.gitignore` に大容量バイナリ除外ルールを追記（50MB超は素材置き場へ）
- [x] CLAUDE.md §6「成果物の保管ルール」を実態に合わせて改訂（3層＝deliverables / agent_output / 素材置き場）
- [x] 成果物カタログCSVとの整合を確認・同期
- [ ] 退避した `_archive_20260826/` の削除可否を社長へ確認（§4.1・別途）

## 現在地

2026-08-26 **庶務マリエ 実作業完了**。C・D の両方を退避し、閲覧口をシンボリックリンクに置換。ルール（CLAUDE.md §3/§5/§6・SUBAGENT_PROTOCOL.md・`.claude/agents/*.md` 8本・`.gitignore`）を実態に合わせて改訂済み。カタログCSV +9行・シート同期済み。**失われたファイル 0件を全件ハッシュ突合で証明済み。**
残るは `_archive_20260826/` 2箇所（計18MB・266ファイル）の**破棄可否の社長ご判断**（§4.1・未実行）。

## ログ

- 2026-08-26 todo 起票 → 同日 doing（カズヨ）。社長ご指摘を受け現状調査を実施、置き場4箇所の散らばりと二重管理の実害を確認。PUBLIC継続のご判断を受けて案B（3層分離の厳格運用）で確定。
- 2026-08-26 マリエ実作業。**着手前に A/C/D 全1,128ファイルのSHA-1台帳を取得**し、作業後に突合して消失0件を証明。
  - **C（~/Documents・206件）**: 全件を「A に同内容あり(116) / Git履歴に保全(90) / 孤児(0)」に分類してから退避。チケット記載の「独自0件」は**不正確**で、実際は C 側にしか無いファイルが140パス・うち内容が真にユニークなものが82件あった。ただし79件は T-20260817-006 サイトの日付スナップショット（`最新版_0817夜`〜`0821e`）で **Git 履歴に blob として現存**を確認。残る3件（T-20260715-001 の HTML 2件・T-20260812-002 の HTML 1件）だけが本当に失われうる状態だったため deliverables へ移送。
  - **食い違い2チケット**: T-20260817-004 は A が v1.2（2026-08-24 サトルの公式API突合による是正版）、C が v1.1（08-17）→ **A 採用**。T-20260817-006 は差分12ファイルすべて A が 08-21〜08-23、C が 08-17 → **A 採用**。
  - **D（~/Claude Code・117件）**: 5.6GB の画面収録＋スクショ56枚（81MB）を新設の素材置き場へ。ユニーク成果物6件（T-20260520-005 の2件、T-20260520-003 の初版レポート2件、T-20260527-002 usage-guide.md、T-20260703-001 の PDF）を deliverables へ移送。
  - **閲覧口**: `~/Documents/AI Company Outputs/Amazon物販事業` → `workspace/output/deliverables` のシンボリックリンクを作成。Spotlight/LaunchServices が `public.folder`「フォルダ」と判定＝Finder は透過的に辿れることを確認（Finder への AppleScript 直接照会は自動化権限ダイアログでタイムアウトしたため、権限不要の方法で検証）。
  - **`.gitignore`**: 当初 `*.mp4` を一律禁止にしたが、T-20260817-006 のモック用 92KB 動画まで除外してしまうことに気づき、**`.mov` `.dmg` `.iso` `.tar` `.tgz` のみ**に絞り込み。サイズ判断は拡張子でなく実サイズで行う旨を明文化。
  - **横展開**: CLAUDE.md だけでなく、サブエージェントの保存先を直接規定する `workspace/SUBAGENT_PROTOCOL.md` と `.claude/agents/*.md` 8本の旧パス記述も同時に改訂（放置すると次の発注で即再発するため）。

## 成果物

- workspace/output/deliverables/T-20260520-005/report.md ／ report.html（D から移送・新規チケットフォルダ）
- workspace/output/deliverables/T-20260520-003/report_v1_20260520.md ／ .html（D から移送・初版）
- workspace/output/deliverables/T-20260527-002/usage-guide.md（D から移送）
- workspace/output/deliverables/T-20260703-001/PDCA実績サマリ_電脳せどり一周.pdf（D から移送）
- workspace/output/deliverables/T-20260715-001/reactivation-steps.html ／ video-verification-checklist.html（C から救出）
- workspace/output/deliverables/T-20260812-002/無在庫_既存ツール調査_2026-08-12.html（C から救出）
- workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv（+9行・シート同期済み）
- CLAUDE.md §3/§5/§6 ／ workspace/SUBAGENT_PROTOCOL.md ／ .claude/agents/*.md 8本 ／ .gitignore（ルール改訂）
- ~/Documents/AI Company 素材/Amazon物販事業/README.md（素材置き場を新設・リポ外）

## 完了報告

カズヨさん、成果物の置き場を deliverables 1箇所にまとめ終えました。**失われたファイルは0件**です（作業前に1,128ファイルのハッシュ台帳を取り、作業後に全件突合しました）。

**社長のご判断をいただきたい点が2つあります。**

1. **`_archive_20260826/` 2箇所（計18MB・266ファイル）の破棄可否** — §4.1（不可逆な削除）のため私は実行していません。中身はすべて deliverables か Git 履歴に保全済みで、**破棄しても失われる情報は実質ありません**。唯一の例外は T-20260705-001 の旧版PDF 2本ですが、A 側に4時間後に再生成された同名・同サイズの新版があり、内容は同一です。
2. **セミナー素材の著作権の扱い** — 素材置き場に移した EC STARs Lab. の**有料セミナー録画とスクリーンショット56枚**は第三者著作物です。リポジトリは PUBLIC なので取り込みませんでした。ただし `docs/reference/maker-shiire/パーフェクトマニュアルサンプル_EC-STARs-Lab.pdf` は**既にコミット済み＝公開中**です。ハルオさんに要確認かと思います。

**積み残し（別チケット推奨）**: カタログCSVには着手前から T-20260601-001 / T-20260804-001 の2チケットが未登録です（私が触った4チケットは埋めました）。また T-20260527-002 の `sato-scope-lite/` は中身が `.pytest_cache` だけになっており、コード本体が見当たりません。


## 社長ご判断待ち（2026-08-26 waiting へ）

1. **`_archive_20260826/` 2箇所（計18MB・266ファイル）の破棄可否** — §4.1（不可逆な削除）。**時間の経過では可決されない。**
2. **第三者著作物の公開範囲** — `docs/reference/maker-shiire/パーフェクトマニュアルサンプル_EC-STARs-Lab.pdf`（EC STARs Lab. の有料教材）が 2026-05 のコミット 1bf015a 以降 PUBLIC リポで公開中。同ディレクトリの `seminar-20260610-realtime-notes.md`（有料セミナーの内容記録）も同様。法務ハルオへレビュー発注済み。

## ログ

- 2026-08-26 doing → waiting（カズヨ）。マリエが一元化を完了（消失0件・移送9件・シンボリックリンク作成・CLAUDE.md 他18ファイル改訂）。社長ご判断2件のため waiting へ。カズヨ側で実在確認済み（リンク経由で49チケット参照可・移送9件すべて実在・素材置き場5.7G）。
