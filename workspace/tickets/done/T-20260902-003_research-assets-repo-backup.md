---
ticket_id: T-20260902-003
title: 自律リサーチ資産のリポジトリ内控えを作成
status: done
assignee: general_affairs
priority: medium
created_at: 2026-09-02
updated_at: 2026-09-02
requires_approval: false
labels: [tooling, research, ops]
parent_ticket: ""
related_tickets: [T-20260902-002, T-20260902-001]
---

## 要件

**T-20260902-002 の後続チケット。**

T-20260902-002 で導入した Claude Code の自律リサーチ資産（スキル `research` ＋ サブエージェント3体・計5ファイル）は、
インストール先 `~/.claude/` がリポジトリ外、inbox アーカイブも `.gitignore` 対象のため、
**どこにもバックアップが存在しない状態**だった。これは同チケットの完了報告でマリエが引き継ぎ事項として挙げた論点。

社長が **A 案（リポジトリ内に控えを置く）を採用**されたため、`docs/reference/claude-research-skill/` に控えを作成する。

## タスク分解

- [x] `~/.claude/` の**現行版**（アーカイブ側のスナップショットではない）5ファイルを `docs/reference/claude-research-skill/` へコピー
- [x] 元のディレクトリ構造を復元できる形に配置（`skills/research/...` ／ `agents/research-*.md`）
- [x] `cksum` でコピー元と5件すべて一致することを確認
- [x] `README.md` を作成（用途・由来チケット・復元先絶対パス・控えである旨・実体編集時は控えも更新する旨）
- [x] **PII / 公開可否チェック**（commit のゲート）→ 混入なし
- [x] `git add` → commit
- [x] Notion カンバンへ同期
- [x] `workspace/owner-tasks.md` の最新化（社長タスクの増減なし）

## コピー元と控えの対応

| 控え（リポジトリ内） | 実体＝正（リポジトリ外） |
|---|---|
| `docs/reference/claude-research-skill/skills/research/SKILL.md` | `~/.claude/skills/research/SKILL.md` |
| `docs/reference/claude-research-skill/skills/research/references/external-sources.md` | `~/.claude/skills/research/references/external-sources.md` |
| `docs/reference/claude-research-skill/agents/research-collector.md` | `~/.claude/agents/research-collector.md` |
| `docs/reference/claude-research-skill/agents/research-verifier.md` | `~/.claude/agents/research-verifier.md` |
| `docs/reference/claude-research-skill/agents/research-integrator.md` | `~/.claude/agents/research-integrator.md` |

`~/.claude/` 配下には**読み取り以外で触れていない**。実体は現状のまま。

## cksum 照合（5/5 一致）

| ファイル | cksum | bytes | 判定 |
|---|---|---|---|
| `SKILL.md` | 950465037 | 7269 | 一致 |
| `external-sources.md` | 1680549349 | 2497 | 一致 |
| `research-collector.md` | 2342105512 | 2983 | 一致 |
| `research-verifier.md` | 81074490 | 2158 | 一致 |
| `research-integrator.md` | 2923363647 | 2388 | 一致 |

**「現行版が正」の指示が効いた箇所:** `SKILL.md` は T-20260902-002 のアーカイブ側が
`3407526324 / 6612 bytes` だったのに対し、実体は `950465037 / 7269 bytes`。**657 バイト差**。
アーカイブ側をコピーしていたら、本日2回分の編集が失われた古い版を「控え」として保存していた。

## PII / 公開可否チェック（commit のゲート・結果＝混入なし）

対象は5ファイル＋ README の全文。このリポジトリは PUBLIC で、
`.claude/scripts/github-sync.sh` が30分ごとに自動 push するため、**commit ＝ 即公開**として判定した。

| # | 観点 | 手段 | 結果 |
|---|---|---|---|
| 1 | 個人名（社長の実名・家族・第三者） | 全文通読 ＋ `[一-龥ぁ-んァ-ヶ]{2,4}(氏|様|さん|社長|部長)` | なし |
| 2 | 住所・電話番号 | `0X-XXXX-XXXX` パターン ＋ 通読 | なし |
| 3 | メールアドレス | メールアドレス正規表現 | なし |
| 4 | 口座番号 | 7桁以上の連続数字 | ヒットは**チケットID（`20260902`）と cksum 値のみ**＝誤検知 |
| 5 | APIキー・トークン・シークレット | `sk-` / `AIza` / `ghp_` / `xox*-` / `Bearer` / `api_key=` / `secret` / `-----BEGIN` | なし |
| 6 | 取引先名・仕入先名・具体的企業名 | `株式会社|有限会社|合同会社|Inc.|Co., Ltd|LLC` ＋ 通読 | なし |
| 7 | ホームディレクトリ絶対パス中のユーザー名 | `/Users/` `/home/` `C:\Users` | **なし**（下記の設計判断による） |

### 判定の根拠（グレーに見えるものの扱い）

- **登場する固有名詞はすべて一般公開サービス／ツール名**：e-Stat、経産省、EDINET、J-STAGE、CiNii、
  Google Scholar、X、YouTube、Gemini API、Google AI Studio、Antigravity CLI、yt-dlp、Exa。
  いずれも本事業の取引先ではなく、公開情報の入口として名前が出ているだけ。指示にある「一般的なサービス名やツール名は除く」に該当。
- **`external-sources.md` の金額表記**（X の従量課金 約$0.005/件 等）は**各社が公開している一般価格**であり、
  当社の契約内容・支払額ではない。
- **`research-collector.md` の「新規お取引先募集」「最低発注ロット」**は、クエリに使う**語彙の例**であって、
  特定の仕入先名ではない。
- **ユーザー名を含む絶対パス**：README の復元先は `~/.claude/...` の**チルダ表記**で記載した。
  復元先として一意に定まり、かつユーザー名の新規露出を作らないため。
  なお `/Users/yukinori` は**既に追跡済みファイル77件で公開済み**（`.claude/hooks/session-start.sh`、
  `docs/owner-playbook.md`、`workspace/handover.md` 等）であり、本件が新たな露出を作ったわけではない。
  **既存77件の扱いを見直すかどうかは本チケットのスコープ外**として、判断材料のみカズヨへ引き渡す。

## 判断者と根拠（done 化について）

- **判断者**: 秘書カズヨ（マリエへの発注時に「作業完了後 `done/` へ」と明示指示）
- **実行者**: マリエ
- **根拠**: 社長が A 案を承認済みで、残作業はコピー・検証・commit のみだった。
  それらが本チケット内で完了し、社長のアクションを必要とする残件がない（§4.1 該当操作なし）ため `waiting/` にも該当しない。
- SUBAGENT_PROTOCOL §3-3「done に動かすのは秘書の責務」の例外扱い。状態を決めたのはカズヨ。

## 現在地

**作業完了。** コピー・cksum 照合・README 作成・PII チェック（混入なし）・commit・Notion 同期・owner-tasks 確認まで済み。

## ログ

- 2026-09-02 起票（T-20260902-002 の後続・社長が A 案採用）
- 2026-09-02 `~/.claude/` 現行版5ファイルを `docs/reference/claude-research-skill/` へコピー。cksum 5件一致
- 2026-09-02 README.md 作成（控えである旨・復元手順・実体編集時の追随義務を明記）
- 2026-09-02 PII / 公開可否チェック実施 → **混入なし**。ゲート通過につき commit
- 2026-09-02 Notion 同期・owner-tasks.md 確認（社長タスク増減なし）。done へ

## 成果物

- `docs/reference/claude-research-skill/`（README.md ＋ 控え5ファイル／**Git 追跡対象**）

> `workspace/output/deliverables/` への納品は**なし**。本チケットの成果は
> 「リポジトリ外の資産をリポジトリ内へ控えとして保全したこと」であり、新規に作成した納品物は README のみ。
> 参照資料の位置づけのため `docs/reference/` が正しい置き場（成果物カタログへの追記も不要）。

## 完了報告

完了しました。5ファイルは無改変のまま `docs/reference/claude-research-skill/` に控えられ、
cksum 5件すべて一致、PII 混入なしを確認のうえ commit 済みです。これで
「`~/.claude/` を初期化しても復元できる」状態になりました。

**引き継ぎ事項が2点あります。**

1. **控えは自動追随しません。** `~/.claude/skills/research/` または `~/.claude/agents/research-*.md` を
   今後編集したら、同じ turn 内でこの控えも更新する必要があります。README に明記しましたが、
   運用ルールとして CLAUDE.md やフックに乗せるかはカズヨのご判断で。
   （古い控えが残ると「バックアップがある」と誤認する分、バックアップ無しより危険です）
2. **`/Users/yukinori` が追跡済みファイル77件で既に公開されています。** 本件の成果物には含めませんでしたが、
   既存分をどうするかは別途ご判断が要る論点です（実害は「Mac のユーザー名が分かる」程度で緊急性は低い）。
