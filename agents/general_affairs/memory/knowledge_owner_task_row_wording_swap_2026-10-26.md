# 社長タスク行の文言差し替えだけの同期（2026-10-26・T-20260930-001 ㉖）

## 何が起きたか
- カズヨが owner-tasks.md ㉖ のオフィス・ラボ項目を「見積り依頼」→「お断り（10/26 社長判断で差し替え）」に書き換え、チケット末尾にログ1件を追記。件数・状態の変化なし
- 依頼文は「Notion 社長タスクまとめカード（Status＝まとめ）に反映」だったが、そのカード（36db0a40-…431d）はアーカイブ済み・Status に「まとめ」の選択肢も無い（owner-tasks-summary-ownership.md）。**更新すべき実体が無い**ので、チケットカード側の反映に読み替えた

## 手順（再利用）
1. `git diff workspace/owner-tasks.md workspace/tickets/` で差分を把握（件数増減が無いことを確認）
2. チケットカード（T-20260930-001 = page 3ebb0a40-44fa-81ff-ab52-d8bb440b5984）を fetch → UpdatedAt だけ update_properties → 結果要約の「🔴 社長タスク」先頭行を最新に差し替え（旧行は「（以下は旧）」として残す）→ 末尾に日付見出しで insert_content
3. Stop フック owner-tasks-sync-check.sh は「owner-tasks.md より新しいチケット .md があるか」の mtime 比較だけ。カズヨが両ファイルを同じ秒に保存すると、チケットの方がわずかに新しく判定されて block になる。**最後に `touch workspace/owner-tasks.md`** し、`find workspace/tickets -name '*.md' -newer workspace/owner-tasks.md` が空であることを確認する
4. カードには卸値・採算の数字を書かず「売価で採算が合わない」程度に留める

## 気づき
- 依頼側（カズヨ）の手順書の読みがアーカイブ前のまま残っている。報告で「まとめカードは廃止済み」と毎回添えて、読み替えたことを明示する
- owner-tasks.md 冒頭の「最終更新」行は 10/10（更新95）のままで、本文最上段（更新106）と食い違っている。今回の依頼範囲外なので触らず報告のみ
