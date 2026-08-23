# 担当: 社長タスクまとめ の維持（2026-05-27〜）

## 概要

社長が「次に何をすべきか」を1枚で把握するダッシュボードの維持はマリエ（庶務）の担当です。情報整頓＝庶務の本分のため。社長フィードバック（2026-05-27）でカズヨから正式に移管されました。

## 対象（2層）

- 真実: `workspace/owner-tasks.md`（リポジトリ）
- 可視化: Notion「📋 社長タスクまとめ」カード（page_id `36db0a40-44fa-815b-a60b-f854b6cd431d`、ticket DB の **Status=「まとめ」** 列に常駐）

## 更新の進め方

カズヨから発注を受けたら:
1. `workspace/tickets/{todo,doing,waiting,done}/` を走査し、社長アクションが必要なもの（owner 依存・承認待ち・情報提供待ち・レビュー待ち）を抽出
2. `workspace/owner-tasks.md` を更新（🔴 今すぐ着手 / 🟡 情報・判断待ち / 🟢 レビュー待ち / ℹ️ 自動進行 の区分、「最終更新」日付も）
3. Notion カードを同期。**Status=「まとめ」を維持**（`doing` 等に戻さない）。`UpdatedAt` も更新
4. Before / After（増えた/解消した社長タスク）を添えてカズヨへ報告

## 注意

- 社長が承認した体裁（区分・書き方）は維持する。大きく変える時はカズヨ経由で社長確認。
- 詳細ルールは [../../secretary/skills/notion-ticket-sync.md](../../secretary/skills/notion-ticket-sync.md) §社長タスクまとめの自動同期。

---

## 訂正（2026-08-23 / T-20260817-005 の作業中に判明）

**上の「対象（2層）」のうち Notion 側は既に存在しません。**
`page_id 36db0a40-44fa-815b-a60b-f854b6cd431d` に更新をかけたところ **404 object_not_found**。
ticket DB を `Status='まとめ'` で照会しても該当0件でした。

CLAUDE.md §6 に **「旧『📋 社長タスクまとめ』カードは廃止し、waiting 列が役割を引き継いだ」** と明記されています。
つまり**現在の真実は `workspace/owner-tasks.md` の1層のみ**で、Notion 側の可視化は **waiting 列そのもの**です。

### 今後の手順（差し替え）

1. `workspace/tickets/{todo,doing,waiting,done}/` を走査し、社長アクションが必要なものを抽出
2. `workspace/owner-tasks.md` を更新（区分と「最終更新」日付の体裁は維持）
3. ~~Notion まとめカードを同期~~ → **不要**。代わりに**該当チケットの Status が正しく `waiting` になっているか**を確認する。
   社長が「自分の番」を見る場所は waiting 列なので、**owner-tasks.md に書いたのに waiting に無い、が新しいドリフト**。
4. Before / After を添えてカズヨへ報告

### 教訓

**メモリに書いた「接続先の実値」は腐る。** page_id を鵜呑みにせず、404 が出たら
「自分の書き間違い」ではなく「**仕様が変わった**」を先に疑い、CLAUDE.md（憲法）と突き合わせること。
今回は CLAUDE.md 側に廃止が書かれていたのに、メモリだけが更新されずに残っていた。
