---
ticket_id: T-20260817-007
title: GitHub 同期の常設自動化（未push解消＋定期オートコミット/プッシュ）
status: done
assignee: it_engineer
priority: high
created_at: 2026-08-17
updated_at: 2026-08-17
completed_at: 2026-08-17
requires_approval: false
next_check_at: null
labels: [infra, git, automation]
parent: T-20260531-001
---

# T-20260817-007 GitHub 同期の常設自動化

## 概要
社長指示（2026-08-17）「GitHub と同期させておいて。また、同期は定期的に自動で行うように」。
親チケット T-20260531-001 の復旧プラン手順5「再発防止フック」の実装にあたる。

## 着手時点の状態（2026-08-17 調査）
- カレントブランチ `claude/nighttime-work-checkin-iTWEa` が origin より **40 コミット ahead**（未 push）。
- 未コミットの作業ツリー変更 4 件＋未追跡 6 ファイル（T-20260814-004 / T-20260817-006 の納品物など）。
- ローカル `main` は origin/main より 14 behind（GitHub 側が先行。害なし）。
- 認証: repo 単位で `credential.helper=osxkeychain`、`gh` も Yukinori1018 でログイン済み → 非対話 push 可能。
- **付随して検出した不具合**: launchd `com.aicompany.amazon-buppan.night-shift` が参照する
  `.claude/scripts/night-shift.sh` が**存在せず**、毎回 30 分おきに `No such file or directory` を
  `workspace/.night-shift/stderr.log` へ書き込み続けていた（＝夜間自走 launchd は死んでいる）。
  ログ 2 本が Git 追跡下にありノイズ源になっていたため untrack ＋ gitignore 化。

## ゴール
1. 未 push 分をすべて GitHub へ反映（immediate sync）。
2. 以後、社長が意識しなくても定期的に自動で commit & push される仕組みを常設。
3. 安全性: force push / ブランチ削除 / reset は**絶対にしない**（CLAUDE.md §4.1 不可逆操作）。
   分岐（diverge）を検知したら push せずログに残して停止する。

## 実装
- `.claude/scripts/github-sync.sh` … 自動同期スクリプト（ロック付き・非破壊）
- `~/Library/LaunchAgents/com.aicompany.amazon-buppan.github-sync.plist` … 30 分間隔で起動
- ログ: `workspace/.sync/github-sync.log`（1MB でローテート、Git 非追跡）

## 検証（2026-08-17）
| 確認項目 | 結果 |
|---|---|
| 未 push 分の解消 | 42 コミットを `origin/claude/nighttime-work-checkin-iTWEa` へ push 済み |
| スクリプト構文 | `bash -n` OK |
| ロック／編集中検知 | 別セッションが編集中のファイルを検知し `HOLD` で見送り（意図どおり） |
| launchd 登録 | `launchctl bootstrap` 成功／`RunAtLoad` で即時1回実行・exit 0 |
| commit → push 経路 | `QUIET_MIN=0` でエンドツーエンド実行 → `COMMIT 1ファイル` → `PUSH` → 作業ツリー clean・origin と一致 |

## ログ
- 2026-08-17 起票。未 push 40 コミット＋作業ツリー変更を検出し同期に着手。
- 2026-08-17 即時同期完了（42コミット push）。`github-sync.sh` ＋ launchd（30分間隔）を常設。
  プレイブック [docs/owner-playbook.md](../../../docs/owner-playbook.md) §GitHub 自動同期 に社長向け手順を追記。
  検証まで完了したため **done**。
- 2026-08-17 **未解決の付随事項（別件）**: 夜間自走の launchd
  `com.aicompany.amazon-buppan.night-shift` が参照する `.claude/scripts/night-shift.sh` が不在で、
  少なくとも 2026-08-17 05:00 時点まで毎回起動失敗していた（＝夜間自走は動いていない）。
  復旧の要否は社長判断待ち。
