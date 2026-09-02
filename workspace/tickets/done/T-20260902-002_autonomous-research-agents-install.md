---
ticket_id: T-20260902-002
title: 自律リサーチ用エージェント/スキルの導入と inbox 退避
status: done
assignee: general_affairs
priority: medium
created_at: 2026-09-02
updated_at: 2026-09-02
requires_approval: false
labels: [tooling, research, ops]
parent_ticket: ""
related_tickets: [T-20260902-001, T-20260821-009, T-20260831-003]
---

## 要件

社長が 2026-09-02 に `_inbox_社長共有/files3/` へ投函された、Claude Code の自律リサーチ用資産
（サブエージェント定義3体＋スキル `research` 一式・計5ファイル）を導入し、
inbox の投函口を空にするところまでを完了させる。

導入作業は同日中に秘書カズヨが実施済み。本チケットは**その記録と、inbox の退避**を担う。

## タスク分解

- [x] 5ファイルを `~/.claude/` 配下へ設置（カズヨ実施・cksum 一致で検証済み）
- [x] マリエ側で cksum を再検証（5ファイルすべて一致・下表）
- [x] `_inbox_社長共有/_archive/2026-09/T-20260902-002_自律リサーチagent-skill/` へ5ファイルを**移動**
- [x] 同フォルダに `README.md`（中身一覧・バイト数・インストール先の絶対パス・原本控えである旨）を作成
- [x] `files3/.DS_Store` を削除し、空になった `files3/` を削除
- [x] inbox 直下の状態確認（`ls -la`）
- [x] Notion カンバンへ同期
- [x] `workspace/owner-tasks.md` の最新化（社長タスクは増減なし）
- [x] `git add` → commit

## 導入したもの

| 種別 | ファイル | インストール先（リポジトリ外） |
|---|---|---|
| サブエージェント | `research-collector.md` | `~/.claude/agents/research-collector.md` |
| サブエージェント | `research-verifier.md` | `~/.claude/agents/research-verifier.md` |
| サブエージェント | `research-integrator.md` | `~/.claude/agents/research-integrator.md` |
| スキル本体 | `SKILL.md` | `~/.claude/skills/research/SKILL.md` |
| スキル参照資料 | `external-sources.md` | `~/.claude/skills/research/references/external-sources.md` |

`external-sources.md` が `references/` 配下なのは、`SKILL.md` 本文 §B が
「`references/external-sources.md` を読め」と相対パスで参照しているため。

3体は収集（collector）→ 統合（integrator）→ 検証（verifier）の**役割分離**が肝で、
「自分が集めたものを自分で検証すると判定が甘くなる」ため verifier が独立している。
`research` スキルはこの3体を指揮するオーケストレーター側の規律（自分で検索しない・並列起動・
カバレッジを数値で判定する・報告文だけで終わらせない）を定義する。

### 同一性の検証（マリエによる再確認・2026-09-02）

`cksum`（CRC32 とバイト数）で inbox の原本と設置先を照合。5件すべて一致。

| ファイル | cksum | bytes |
|---|---|---|
| `research-collector.md` | 2342105512 | 2983 |
| `research-verifier.md` | 81074490 | 2158 |
| `research-integrator.md` | 2923363647 | 2388 |
| `SKILL.md` | 3407526324 | 6612 |
| `external-sources.md` | 1680549349 | 2497 |

## 現在地

**done。** 導入・退避・README 作成・Notion 同期・commit まで完了。

**この inbox アーカイブが実質的な原本控え。** 設置先の `~/.claude/` はリポジトリ外で
Git 追跡されないため、`~/.claude/` を初期化・移行した場合に復元できる控えは
`_inbox_社長共有/_archive/2026-09/T-20260902-002_自律リサーチagent-skill/` のみ。
ただしこのアーカイブ自体も `.gitignore`（24行目 `_inbox_社長共有/`）でリポジトリ追跡外＝
**バックアップされていない**。この点は README にも明記した。

## 削除の実行記録（監査用）

inbox-intake スキル Step 4 に従い記録する。

1. **実行者**: マリエ（庶務）
2. **日時**: 2026-09-02
3. **対象**: `_inbox_社長共有/files3/.DS_Store`（1件・6148バイト・macOS Finder が自動生成する
   `Apple Desktop Services Store` バイナリ）と、空になった `files3/` ディレクトリ本体
4. **事前確認**: `ls -la` で `files3/` の全内容6件を目視、`file` で `.DS_Store` の種別を確認、
   5ファイルの移動完了を確認したうえで残存が `.DS_Store` 1件のみであることを確認
5. **事後確認**: `files3/` が存在しないこと、`_archive/.../` に5ファイルが揃っていることを確認

**根拠**: inbox-intake スキル §Step 4「破棄候補に挙げてよいもの」の筆頭
「`.DS_Store` 等の OS 自動生成ファイル」に該当。情報価値ゼロ。

**消さなかったもの**: `_inbox_社長共有/.DS_Store`（inbox 直下・6148バイト）。
今回の指示スコープは `files3/` 内に限定されていたため、対象外として残置した。
無害だが、inbox 直下を厳密に「`README.txt` と `_archive/` だけ」にしたい場合は
別途一次承認を得て消す（伝聞承認では実行しない＝スキル §Step 4 の3段表）。

## 判断者と根拠（done 化について）

- **判断者**: 秘書カズヨ（マリエへの発注時に「実作業は完了済みなので、退避まで終えたら `done/` に置いてよい」と明示指示）
- **実行者**: マリエ
- **根拠**: 導入・疎通は起票時点で既に完了しており、残作業は inbox 退避のみだった。
  その退避も本チケット内で完了したため、着手待ち・確認待ちの残件がない。
  社長のアクションを一切必要としない（§4.1 該当操作なし）ため `waiting/` にも該当しない。
- SUBAGENT_PROTOCOL §3-3「done に動かすのは秘書の責務」の例外扱い。
  状態を決めたのはカズヨであり、マリエはファイル配置を代行しただけである。

## 成果物

- `_inbox_社長共有/_archive/2026-09/T-20260902-002_自律リサーチagent-skill/`（5ファイル＋README.md／Git 追跡外）
- 実体は `~/.claude/agents/` と `~/.claude/skills/research/`（リポジトリ外・Git 追跡外）

> `workspace/output/deliverables/` への納品は**なし**。本チケットの成果は
> 「社長から預かったファイルを正しい場所に設置し、原本を控えとして整理したこと」であり、
> 新規に作成した納品物が存在しないため。成果物カタログへの追記も同じ理由で不要。

## ログ

- 2026-09-02 社長が `_inbox_社長共有/files3/` へ5ファイルを投函
- 2026-09-02 カズヨが `~/.claude/agents/`（3体）と `~/.claude/skills/research/`（SKILL.md ＋ references/external-sources.md）へ設置。内容は無改変・cksum 一致で検証
- 2026-09-02 マリエが cksum を再検証（5件一致）→ `_archive/2026-09/` へ移動 → README.md 作成 → `.DS_Store` と `files3/` を削除
- 2026-09-02 Notion 同期・owner-tasks.md 更新・commit。done へ

## 完了報告

完了しました。5ファイルは無改変のまま `_archive/2026-09/T-20260902-002_自律リサーチagent-skill/` に退避済み、
inbox 直下は `README.txt` / `_archive/` / `.DS_Store`（直下の1件・スコープ外のため残置）の状態です。

**引き継ぎ事項が1つあります。** このアーカイブは `.gitignore` 対象＝バックアップされていないのに、
`~/.claude/` 側も Git 追跡外です。**5ファイルが「どこにもバックアップされていない資産」になっています。**
リポジトリ内（例: `docs/reference/claude-research-skill/`）へ控えを1部置くかどうかは、
社長のご判断が要る論点としてカズヨへ引き渡します（内容に PII・第三者著作物は含まれないため、
公開リポジトリに置いても差し支えないことは確認済み）。
