---
ticket_id: T-20261026-002
title: 秘書のサブエージェント発注が減った原因の調査
status: doing
assignee: it_engineer
priority: high
created_at: 2026-10-26
updated_at: 2026-10-27
requires_approval: false
labels: [process, root-cause, delegation]
next_check_at: 2026-10-28
related_tickets: []
---

## 要件

CLAUDE.md §5「原則すべて振る」があるのに、秘書の発注が減った理由を突き止める（2026-10-26 社長指示「ルールに組み込んでいたはずなのにそれが抜けた理由が知りたい」）。

## 前提（同日に秘書が集計済み）

- 1日の Agent 発注回数：10/10〜11 は約35回 → 10/19〜25 は2〜8回 → 10/26 は1回
- 10/19 以降の発注先は IT とリサーチャーだけ。経理・法務・制作・戦略・シミュレーターは7日間0回
- 呼び出しの失敗は直近で0件（仕組みは正常）
- 実害：10/26 の桝田屋食品の試算を秘書が自分で作り、おりおん代行費を落とした

## タスク分解

- [x] 発注が減った時期と、その間に秘書が代わりに何をしていたかをセッション履歴で特定（タカシ）
- [x] CLAUDE.md・agent.md・routing.md・フック・予約タスクの変化と突き合わせ、原因を根拠つきで特定（タカシ）
- [ ] 秘書が結果を検算し、社長に報告

## 現在地

タカシの再調査と是正の道具が完了（報告書 02）。日本語チェック・フォルダなし会話への橋渡しは作成・試験済みだが**未登録**。登録（settings.json・~/.claude/settings.json）と CLAUDE.md §A1 の1行は社長承認待ち（秘書が承認を取って `install_language_and_bridge_hooks.py --apply` を実行）。

## ログ

- 2026-10-26 起票。タカシへ発注
- 2026-10-26 タカシ：原因分析を納品。①10/19午後から社長の会話がフォルダなしで始まり CLAUDE.md §5・担当一覧が読まれない ②委譲チェックを含むフック9本が 8/21 から全件 exit 127（パスの空白）③CLAUDE.md 肥大は相関のみ。対策案 A〜C（未実装）
- 2026-10-27 社長指摘「全然直ってなくないですか？サブエージェントが動いている気がしない」「英語で質問してくることが多い。日本語のルールが徹底できていない」。対策A〜Cが未実装のままだったことを含め、タカシに再調査と是正を発注（委譲回数の推移・フック実行確認・フォルダなし会話への対策・英語の質問の抽出と是正）
- 2026-10-27 タカシ：再調査を納品（02）。社長の会話から8職への発注は 10/19〜25 に0回、10/27 は15回（うち14回はリポで始めた1本）。フック exit 127 は 10/27 朝に解消済み（a5a15360）だが、フォルダなしの会話（10/20〜27 の25本中22本）ではリポのフックが1本も動かない。英語の問い7件（フォルダなし6・夜間1）、原因は「日本語で書く」の決まりが CLAUDE.md・agent.md に無いこと＋フォルダなしでは指示が届かないこと。japanese-only-guard.py・global-buppan-bridge.py・登録スクリプト・試験25件を追加（未登録）

## 成果物
- workspace/output/deliverables/T-20261026-002/02_再調査と是正.md
- .claude/hooks/japanese-only-guard.py・.claude/hooks/global-buppan-bridge.py・.claude/hooks/install_language_and_bridge_hooks.py・.claude/hooks/tests/test_japanese_and_bridge.sh
- workspace/output/deliverables/T-20261026-002/01_発注減少の原因分析.md（2026-10-27 時点で deliverables に追跡済み）
  - deliverables に置いて commit したところ、pre-commit の発注ゲート（scripts/sourcing_gate/gate.py）がパス中の「発注」で発注案と誤判定して止めた。改名して通すのは回避にあたるため行わず、30分ごとの自動同期を巻き込んで止めないよう agent_output に退避した。置き場（改名で納品するか、ゲートの判定を直すか）は秘書判断

## 完了報告
完成度：原因1・2は記録と再現で確定、原因3は相関のみ（反証あり）。妥協点：10/19 からフォルダなしで始まった理由（アプリ既定か社長の開き方か）は記録から特定できない。引き継ぎ：対策A（settings.json のフック9本の引用符修正）は実装していない。秘書の判断で IT に発注すれば数分で済む。中間データ・集計スクリプトは agent_output/T-20261026-002/。

### 完了報告（2026-10-27 再調査）
完成度：集計（委譲・フック・フォルダなし・英語）は会話記録から確定。是正の道具は試験25件・実データ再生で確認済み。妥協点：登録と CLAUDE.md の変更は担当の権限外なので未実施＝社長が見る挙動はまだ変わっていない。アプリの実画面で deny が効くかは未確認。引き継ぎ：社長承認後に秘書が `python3 .claude/hooks/install_language_and_bridge_hooks.py --apply` と CLAUDE.md §A1 の1行（02 §5 に前後）。worktree 3本の settings.json が古い（引用符なし）。
