---
ticket_id: T-20260531-001
title: ローカル⇄GitHub⇄Notion 同期の破綻復旧と再発防止ワークフロー確立
status: doing
assignee: secretary
priority: high
created_at: 2026-05-31
updated_at: 2026-06-01
requires_approval: false
next_check_at: 2026-06-02
labels: [infra, git, notion, governance, incident]
parent: null
---

# T-20260531-001 ローカル⇄GitHub⇄Notion 同期の破綻復旧と再発防止

## 概要
社長が「自宅＝ローカルPCのClaude Code」「外出先＝GitHub上(Web/携帯)のClaude Code」を、手動clone/同期せずに併用していたため、ローカルとGitHubが別々に進行。Notionには両方から書き込まれ、チケット番号 `T-20260529-001` が衝突（リポジトリ=業務フロー図 / Notion=「Notion同期をマリエ責務化」）。

## 確定事実（2026-05-31 調査）
- 「Notion同期をマリエ責務化」(T-20260529-001) の実体 `.md` は GitHub の `main`・作業ブランチ双方に存在せず、Notion のみに存在 → 未pushのローカルセッション由来と断定。
- GitHub内部も `main` と `claude/nighttime-work-checkin-iTWEa` が 3:4 で分岐（全体フロー図 Phase1 が二重作成）。
- 制約: 本セッションはGitHub側コンテナ。社長Macのローカルフォルダには到達不可（ローカルのpush/pullは社長操作が必須）。

## ゴール
1. ローカル/GitHub/Notion の三者を一つの真実（GitHub `main`）に収束。
2. 番号衝突 T-20260529-001 を解消（Notion側の幽霊チケットを別番号にリナンバー＋実体ファイル化）。
3. 再発防止: セッション開始=pull / 終了=commit&push を運用とフックで強制。

## 復旧プラン（順序が重要）
1. **[社長Mac] ローカルの状態確認＆push** … 幽霊チケットを含むローカル未push分をGitHubへ。
2. **[秘書/GitHub] 分岐統合** … ローカル分＋作業ブランチ＋main を main に収束（衝突番号は解消）。
3. **[社長Mac] pull** … 統合済み main をローカルへ。
4. **[秘書] Notion再同期** … 真実(main)からNotionを正しい姿に。幽霊を別番号化。
5. **[秘書] 再発防止フック** … SessionStart=`git pull` / Stop=`git add&commit&push` を導入。

## ログ
- 2026-05-31 起票。調査で原因特定（ローカル/GitHub分離＋Notion二重書込）。Plan A（リポジトリ=真実）で社長合意。社長Mac操作の要否を確認中。
</content>
