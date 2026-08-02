---
description: Notion カンバンとチケットを突合し、ドリフトを非破壊で修復（庶務マリエ実行）
---

# /sync-notion — Notion リコンサイル

`workspace/tickets/` の全チケットと Notion カンバン「Amazon物販事業 Tickets」を突合し、ズレを修復します。**庶務マリエの責務**として実行してください（運用詳細は `agents/general_affairs/skills/notion-ticket-sync.md`）。

## 手順

1. `workspace/tickets/{todo,doing,waiting,done}/*.md` を全走査し、各 frontmatter（`ticket_id`/`title`/`status`/`assignee`/`priority`/`requires_approval`/`created_at`/`updated_at`/`parent_ticket`/`labels`）を読み取る。
2. `notion-query-database-view`（Table view: `https://www.notion.so/366b0a4044fa81788359d44b4f807458?v=366b0a4044fa81dcbb14000c73f916c1`）で Notion 側の全カードを取得。
3. TicketID で突合し、差分を分類：
   - **リポジトリにあり Notion に無い** → `notion-create-pages` で作成（parent data_source_id `366b0a40-44fa-81ec-8342-000b6d0a25e0`）。
   - **両方にあり値が違う** → リポジトリ側を正として `notion-update-page` で更新（特に Status / UpdatedAt）。
   - **Notion にあり リポジトリに無い** → **削除しない**。別ブランチ由来の可能性があるため、「要確認カード」として一覧化し社長に報告（§4.1 不可逆削除に該当）。
4. 日付は展開キー（`date:UpdatedAt:start` 等）、RequiresApproval は `__YES__`/`__NO__` で書くこと（書式ミスが過去の失敗主因）。
5. 完了後、結果サマリを **作成N件 / 更新M件 / 要確認K件** で報告。要確認カードはタイトルと TicketID を列挙。

## 注意

- **非破壊**：自動でカードを消さない。
- 真実は `workspace/tickets/` のファイル。ただし**ブランチ分岐**で別セッションの更新が Notion 側に先行している場合があるため、リポジトリが Notion より「古い」状態（todo/waiting なのに Notion は done）を検知したら、上書きせず社長に「ブランチ未マージの疑い」として報告する。
- 引数があればそのチケット ID／状態に絞って同期してよい（例: `/sync-notion T-20260529-001`）。
