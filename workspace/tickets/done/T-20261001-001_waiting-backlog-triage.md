---
ticket_id: T-20261001-001
title: waiting 35件の棚卸し（A 社長の一手／B 秘書が進める／C done）
status: done
assignee: general_affairs
priority: high
created_at: 2026-10-01
updated_at: 2026-10-01
requires_approval: false
labels: [ops, triage]
parent_ticket: ""
next_check_at: 2026-10-02
related_tickets: []
---

## 要件

社長指示（2026-10-01）：「質問ばかりで私が手足になっている。社長マターで止まっているものが多い」→ CLAUDE.md §4.5 新設。
その最初の適用として、waiting 35件を3分類し、B は doing へ戻して担当に振り、C は done にする。計画は社長承認済み（2026-10-01）。

## 判断基準（承認済み計画の論点）

- A：社長にしかできない一手（ログイン/決済/規約同意/§4.1承認/手作業）が残る
- B：秘書が決めて進められる
- C：中身が後続チケットに引き継がれた古い調査・手引き → done（理由1行）
- §4.1 が絡むものは必ず A

## 現在地

完了（2026-10-01）。waiting 35件 → waiting 3／doing 3／done 29。結果表は deliverables/T-20261001-001/01_waiting棚卸し.md。Notion は5件が権限で未同期（下記ログ）。

## ログ

- 2026-10-01 起票・計画承認。マリエへ一次分類を発注。
- 2026-10-01 マリエ：waiting 35件を一次分類（A=3・B=5・C=27・迷い7件）。読むだけで移動・Notion 操作なし。
- 2026-10-01 カズヨが一次分類を確定（C27＋T-20260915-001 → done、T-20260806-002 → done、B3件 → doing、A3件 → waiting 据え置き）。
- 2026-10-01 マリエ：35件の frontmatter 更新・ログ追記・git mv を実施。T-20260806-002 は Drive に書かず memory 参照で done（外部書き込みを避けた）。
- 2026-10-01 マリエ：**未処理の申し送り（T-20260831-003 から移管）**＝CLAUDE.md §6「3層」表の③を「リポジトリに置けないもの」に改め、判定に「PII を含む」を追加する提案。CLAUDE.md は憲法のため庶務では書き換えない。カズヨ／社長判断待ち。
- 2026-10-01 マリエ：Notion 同期。29件成功。**権限分類器に拒否された5件は未同期（Notion 上は waiting のまま）**：T-20260804-001・T-20260816-003・T-20260912-002・T-20260925-001（→done 予定）、T-20260927-002（→doing 予定）。リトライはしていない。あわせて T-20260927-002 の requires_approval を false にする編集も拒否されたため true のまま。

## 成果物

- workspace/output/deliverables/T-20261001-001/01_waiting棚卸し.md

## 完了報告

waiting 35件を 3／3／29 に仕分けた。社長への依頼は A の3件＋T-20260920-003 の既存3件のみ。削除は一切なし。Notion 未同期5件と PII 基準の申し送り1件が残課題。
