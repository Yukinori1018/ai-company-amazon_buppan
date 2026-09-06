# チケットIDの重複は Notion 同期を止める（TicketID が同期キーだから）

初出: 2026-09-06 / カズヨから T-20260906-004・005 の同期依頼を受けた回

## 何が起きたか

同期前の実在確認（`notion-query-data-sources` で `TicketID LIKE 'T-20260906%'`）をしたところ、
**`T-20260906-004` が別々の2枚のチケットに割り当てられている**ことが分かった。

| ファイル | title | status | assignee |
|---|---|---|---|
| `doing/T-20260906-004_sns-trend-sourcing-ideas.md` | SNS/トレンド起点で商品を見つけるスキーム | doing | researcher |
| `done/T-20260906-004_netsea-url-publishability.md` | NETSEA商品URLをPUBLICリポに載せてよいか | done | legal |

後者は `9af3a56` で「法務判定を遡って起票しdoneへ」として作られたもの。
**遡って起票するときに、その日の連番の最大値を取り直さなかった**のが原因と見られる。

## なぜ「とりあえず作る」をしなかったか

`TicketID` は同期キーそのもの。同じ ID のカードが2枚並ぶと、

- どちらを更新すべきか機械的に決められなくなる
- **非破壊原則があるので、間違って作ったカードを自動では消せない**（社長確認が要る）

つまり**作った瞬間に、人手でしか直せない負債になる**。
今回は「今この時点では -004 のカードが Notion に1枚も無い」状態だったので、
**両方とも作らずに保留し、採番のやり直しをカズヨへ差し戻した**。採番は秘書の責務であって庶務の判断で変えてよい所ではない。

判断材料として、**保留しても社長への実害は無い**ことも確認した（両方 doing / done で、社長が見る `waiting` 列には出ない）。
これが waiting のチケットだったら、保留せず先に社長へ知らせる必要がある。

## 副産物: 取りこぼし2枚

同じ照会で **T-20260906-002 / -003 のカードも存在しない**ことが分かった（起票 turn での同期漏れ）。
これは重複ではないので、その場で遡って作成した。

→ **同期依頼が来たら、依頼された ID だけでなく「その日の連番全部」を照会する。**
`LIKE 'T-YYYYMMDD%'` で引けば、依頼外の漏れと ID 重複が同時に見つかる。1回のクエリで済む。

## `assignee` の表記ゆれ

`T-20260906-002 / -003` の frontmatter は `assignee: it-engineer`（ハイフン）だが、
Notion の Assignee 選択肢は **`it_engineer`（アンダースコア）**。書き込み時は読み替えた。
`ticket-frontmatter-contract.md` の正は `it_engineer` なので、起票側の表記ゆれとしてカズヨへ報告した。

## ラベル追加（今回足した5件）

`honmaru` `expo` `list-quality` `data-quality` `overnight` を追加。
手順は `knowledge_notion_label_option_must_be_added_first.md` のとおりで、
**既存34件を全列挙 + 新規5件 = 39件**を `ALTER COLUMN "Labels" SET MULTI_SELECT(...)` に渡し、
返ってきた `<data-source-state>` で 39 件になっていることを数えて確認した。
