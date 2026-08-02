# スキル：Notion チケット同期（秘書の関与）

> **2026-05-29 変更:** Notion 同期の**責務は庶務マリエに移管**しました。
> 運用本体（接続先・プロパティ書式・MCP レシピ・リコンサイル手順）は
> [agents/general_affairs/skills/notion-ticket-sync.md](../../general_affairs/skills/notion-ticket-sync.md) を参照してください。

## 秘書カズヨがやること

社長窓口として、チケットを起票・移動した**その turn 内で**、上記マリエのスキルに従い Notion を即時同期します（軽量な単発同期は秘書が直接 MCP を叩いてよい＝マリエの作業を代行）。

| イベント | 即時アクション |
|---------|--------------|
| 新規起票（todo 作成） | カード新規作成（`notion-create-pages`） |
| 状態遷移（todo→doing→waiting→done） | Status・UpdatedAt 更新（`notion-update-page`） |
| done 化 | Status=done＋本文「結果要約」更新 |

- `.claude/hooks/ticket-notion-sync-reminder.sh`（PostToolUse 強制フック）がチケットファイル変更を検知して同期を促します。**リマインドが出たら未同期で turn を終えない。**
- 大量同期・ドリフト修復は `/sync-notion` でマリエに一括依頼します。
- 真実は `workspace/tickets/` のファイル。Notion は片方向ミラー（リポジトリ → Notion）。

詳細・実値・落とし穴はすべてマリエのスキルに集約してあります。
