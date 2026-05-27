# スキル：Notion チケット同期

秘書が Notion カンバンボードと `workspace/tickets/` を同期する際のプロトコルです。

## 同期方針

- **真実は `workspace/tickets/` のファイル状態**。Notion はその可視化（ミラー）。
- **片方向同期**：リポジトリ → Notion。Notion 側で直接カードを動かしても、リポジトリには反映されない（次回リコンサイル時に Notion 側が上書きされる）。
- 同期は **秘書の責務**。MCP 経由で Notion API を直接呼び出す。

## Notion 側の前提

子会社化時、子会社オーナーが Notion に以下を用意します（詳細は Phase 6 で `docs/notion-setup-guide.md` に整備）。

- Notion データベース 1 つ（カンバンビュー）
- 必須プロパティ：

| Notion プロパティ | 型 | チケット frontmatter |
|------------------|-----|-------------------|
| Name | Title | `title` |
| TicketID | Text（一意） | `ticket_id` |
| Status | Status（todo / doing / waiting / done） | `status` |
| Assignee | Select | `assignee` |
| Priority | Select | `priority` |
| RequiresApproval | Checkbox | `requires_approval` |
| Description | Text | 本文の「要件」セクション |
| CreatedAt | Date | `created_at` |
| UpdatedAt | Date | `updated_at` |

MCP 設定（API トークン、Database ID）も子会社側で `.mcp.json` に注入。親テンプレートにはスタブのみ置きます（Phase 5 で配置）。

## チケット言及時の即時同期確認（最優先トリガー）

**社長の発話で特定チケットへの言及があった瞬間に、秘書は以下を必ず実行する。**
ハンドオーバーや週次リコンサイル待ちでは遅い。発話のたびに整合性を閉じるのが唯一の確実な手段。

### 手順

1. **読み合わせ（指示実行より先）**
   - ローカル `workspace/tickets/{todo,doing,waiting,done}/<該当チケット>.md` を読む
   - Notion 側カードを `notion-fetch` で読む（TicketID で照合）
   - 差分（Status / Assignee / Priority / 本文要約）があれば、社長への返答冒頭で「ローカル=X、Notion=Y、差分あり」と1行で提示
2. **指示実行**
   - 社長指示に従ってチケット状態を動かす（mv / frontmatter 更新 / 本文追記）
3. **同じターン内に Notion 同期**
   - 状態が動いた場合: `notion-update-page` で Status / UpdatedAt / 必要なら本文要約を更新
   - 新規起票なら: `notion-create-pages` でカード作成
   - Assignee Select に該当 role が未追加の場合: `notion-update-data-source` でオプション追加してから本体更新
4. **整合報告**
   - 応答末尾に「ローカル＝Notion 一致（Status: doing, Assignee: it_engineer 等）」と1行で報告

### 「チケット言及」の判定基準

- TicketID（`T-YYYYMMDD-XXX`）が出てきた
- チケット名が明示された（例:「Sato-Scope の…」「用語集の…」）
- 状態遷移を示唆する語があった（「終わった」「着手して」「待ち」等）+ 文脈で一意に特定可能

迷ったらやる。コスト（API 2〜3 コール）より整合性が重要。

### このトリガーで拾えないケース

社長が触れないチケット（長期 todo / 古い waiting 等）は依然ズレうる。**週次ルーティン（日曜夜 or 月曜朝）で全件リコンサイル**を併用する。

---

## 呼び出しタイミング

**社長から「Notion を見ても進捗が見えない」と言われないよう、以下を厳守：**

| イベント | Notion 側のアクション | 即時性 |
|---------|---------------------|---|
| **チケット新規起票**（`todo/` に作成） | カード新規作成、TicketID で一意性確保 | ★ 起票と同じターン内に同期 |
| **状態遷移**（todo → doing 等） | Status プロパティ更新、UpdatedAt 更新 | ★ 状態を動かした同じターン内 |
| **チケット内容更新**（タイトル・担当・優先度等） | 該当プロパティ更新 | 同じセッション内 |
| `done` に移動 | Status を done、UpdatedAt 更新 | ★ 完了と同じターン内 |
| 親子関係の付与 | ParentTicket フィールド更新 | 起票時 |
| チケット削除（基本しない） | カード削除 | 都度 |

## ページ本文に「結果要約」を書く

カンバン表示（カード）には Status・Assignee・Priority 等のプロパティしか出ない。**カード本文（ページを開いた時に見える本文）には、社長が一目で内容を把握できる「結果要約」を必ず置く。**

- 配置：ページ本文の末尾に `## 結果要約` 見出しで追記
- 内容：
  - **done**：何を成し遂げたか／関連コミット
  - **waiting**：何を納品済か／何を待っているか／レビュー観点
  - **doing**：承認済み前提／現在地／次の手
  - **todo**：ブロッカー／情報受領後の流れ
- 粒度：3〜10行程度。長文は要件セクションに譲る
- 更新タイミング：状態遷移と同じターン内に書き換える（古い要約を残さない）
- MCP 呼び出し：`notion-update-page` の `insert_content`（末尾追記）または `update_content`（既存差し替え）

## チケット粒度と Notion 上の見え方

**「Notion で進捗が見えない」問題の根本原因：チケット粒度が大きすぎる**

- 1チケットが1〜2週間規模だと、何日も `doing` から動かず「進んでない」と見える
- 対策：[ticket-management.md](ticket-management.md) の「チケット粒度ルール」に従い、1〜2セッションで完了する単位に分割
- 親子分割した場合：親カード＋子カードがそれぞれ Notion に出現し、子が動くたびに Notion で進捗が可視化される
- 3日以上 `doing` のままのチケットは子分割を検討するか、`waiting/` に動かすべきでないか再確認

## 社長タスクまとめの自動同期

社長が「次の動き」を1枚で把握するためのダッシュボード。**社長のタスクが増減・変更されるたびに必ず最新化する**（CLAUDE.md §3-8）。

**実体（2層）:**
- 真実: [../../../workspace/owner-tasks.md](../../../workspace/owner-tasks.md)（リポジトリ）
- 可視化: Notion「📋 社長タスクまとめ」カード（page_id `36db0a40-44fa-815b-a60b-f854b6cd431d`、ticket DB の **Status=「まとめ」** 列に常駐）

**更新トリガー（いずれかが起きたら同じターン内で同期）:**
- 新規チケット起票（社長アクションが発生するもの）
- チケットの状態遷移（todo↔doing↔waiting↔done）
- 社長依存タスクの追加・解消・内容変更（承認待ち・情報提供待ち・レビュー待ち・本人手作業）

**担当: マリエ（庶務）。** 情報整頓は庶務の本分のため、まとめの維持はマリエが担当する。カズヨは司令塔として更新が必要なタイミングを検知してマリエに発注し、成果を品質確認して社長へ報告する（routing.md §着手前の可視化）。軽微・即時の反映はスピード判断でカズヨ代行も可だが、原則はマリエ名義の成果物。

**同期手順:**
1. （カズヨ）更新トリガーを検知 → 「この作業はマリエ（庶務）です」と宣言してマリエに発注
2. （マリエ）`workspace/tickets/{todo,doing,waiting,done}/` を走査し、社長アクションが必要なものを抽出
3. （マリエ）`workspace/owner-tasks.md` を更新（🔴 今すぐ着手 / 🟡 情報・判断待ち / 🟢 レビュー待ち / ℹ️ 自動進行 の区分、「最終更新」日付も）
4. （マリエ）Notion カードを `notion-update-page` で同期。**Status=「まとめ」を維持**（`doing` 等に戻さない）。`UpdatedAt` も更新
5. （カズヨ）整合を確認し、社長へ報告

**強制の仕組み:** Stop フック [../../../.claude/hooks/owner-tasks-sync-check.sh](../../../.claude/hooks/owner-tasks-sync-check.sh) が「owner-tasks.md より新しいチケットがある＝未同期」を検知してターン終了をブロックする。owner-tasks.md を更新すれば最新になり自動解除（ループしない）。社長アクションに影響しない変更なら最終更新日のみ更新で可。

## エラー時のフォールバック

MCP 呼び出しが失敗した場合：

1. 失敗内容を [../memory/](../memory/) の `notion-sync-errors.md` に追記（タイムスタンプ・チケットID・エラー内容）
2. **チケット自体の処理は止めない**（リポジトリ側を真実として進める）
3. その日のうちに社長に「Notion 同期 N 件失敗、リコンサイル要」と報告
4. 次の機会にリコンサイル実行

## リコンサイル（手動同期）

`workspace/tickets/` 全体を走査して Notion 側を上書き更新する操作。

**実行タイミング:**
- 同期エラーが蓄積した時
- 社長から「Notion とズレてる気がする」と指摘された時
- 月次の定期メンテナンス

**手順:**
1. `workspace/tickets/{todo,doing,waiting,done}/` 配下の全 `.md` を走査
2. 各チケットの frontmatter を読み取り
3. TicketID で Notion 側カードを検索
4. あれば更新、なければ作成
5. Notion 側に存在するが リポジトリにない TicketID は、社長確認の上でアーカイブ
6. 結果サマリ（更新N件・作成M件・要確認K件）を社長に報告

## メモリへの記録対象

- 同期失敗パターン（どのフィールドで何が起きやすいか）
- Notion 側の手動変更が頻発する箇所（同期方針見直しの材料）
- リコンサイル時の差分傾向

→ [../memory/](../memory/) に蓄積。
