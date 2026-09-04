---
ticket_id: T-20260904-001
title: owner-tasks.md の逆方向ドリフト一括棚卸し（32件）
status: todo
assignee: general_affairs
priority: medium
created_at: 2026-09-04
updated_at: 2026-09-04
requires_approval: false
labels: [maintenance, notion-sync]
parent_ticket: ""
next_check_at: 2026-09-07
related_tickets: [T-20260822-001]
---

## 要件

`workspace/owner-tasks.md` の「社長アクション」欄に、waiting 以外のチケット（done / doing / todo）が混ざっている件を一括で片付ける。マリエが 2026-08-24（6件）→ 08-31（13件）→ 09-04（32件）と3回連続で報告しているが、3回とも「提案」で止まり起票されていなかった。今回起票する。

取りこぼし方向（waiting なのに owner-tasks に無い）は 0 件なので、社長が見落とすリスクは無い。実害は「waiting 列＝社長タスク一覧」という設計の価値が薄まること。

## タスク分解

- [ ] 32件を機械抽出し直す（前回はざっくり grep で本文中の言及も拾っている。実数はこれより少ない見込み）
- [ ] 3分類に仕分ける：①done なのに `- [ ]` のまま ②doing なのに社長アクション欄 ③todo なのに社長手作業として記載
- [ ] ①は owner-tasks.md 側でチェック済みに更新
- [ ] ②③は「社長が次に手を動かす必要があるか」で再判定し、Yes なら waiting へ状態遷移（**遷移の判断はカズヨ**／マリエは候補リストまで）、No なら owner-tasks から除去
- [ ] Notion「社長タスクまとめ」カードへ反映
- [ ] 再発防止：同期スクリプトに逆方向チェックを組み込めるかタカシに相談するか判断

## 現在地

未着手。マリエの 2026-09-04 同期報告（T-20260903-001 の完了処理）で A 案として提示された内容をそのまま起票。

## ログ

- 2026-09-04 todo 起票（マリエの3回目の報告を受けて、提案ではなく起票に切り替え）
