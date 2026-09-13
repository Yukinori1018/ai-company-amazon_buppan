# 社長差し戻し（waiting → doing）の同期セット（2026-09-14 / T-20260912-002・子 T-20260914-001〜003）

## 何が起きたか

9/13 に waiting へ出した統合報告（判断12点）を、社長が 9/14 に差し戻した（「12ヶ月で現金が増えない事業はダメ」＋他AIの引き継ぎPDF）。
カズヨが -002 を doing に戻し、子3枚（-001 doing／-002・-003 todo）を起票（commit 148c60e）。私の仕事はその可視化。

## 差し戻しは「done」でも「waiting 追加」でもない第3の型

| 事象 | 社長タスク | owner-tasks でやること |
|---|---|---|
| waiting へ出す | +1 | 🔴/🟡 に項目追加 |
| done | −1 | 「解消」として入れ替わりを書く |
| **差し戻し（waiting → doing）** | **−1（純減）** | 🔴 から項目を**外す**。冒頭の旧「更新㉑㉒」は残したまま**取り下げ**と注記。ℹ️ に「再設計中・社長判断は収束後」を書く |

差し戻しで消えた社長タスクは「解消」ではなく「一旦取り下げ」。再提示の目安（9/15〜16）まで書く。
既存の更新㉑㉒（判断11点→12点）は削らない。読者が「判断12点はどこへ行った？」と迷わないよう、**取り下げの1行を旧記述の直下と 🔴 の元位置ではなく冒頭の新節に置いた**。

## Notion 側の3点セット（1 turn で閉じる）

1. 親カード：Status=doing・UpdatedAt・**Description を差し戻し版に書き換え**（Description は「【waiting …判断12点・期限 9/16】」のまま残すと看板だけが古くなる）。結果要約は `update_content` で最後の bullet の末尾文をアンカーにして1行追記（`insert_content` は末尾＝成果物節の下に落ちるので使わない）
2. 子3枚：SQL で TicketID 在籍ゼロを確認 → `notion-create-pages` の pages 配列1回で作成。**発注文のラベル一覧を信用せず frontmatter × スキーマを自分で突き合わせる**（今回は `pipeline` 既存・`cashflow` 未登録。発注文どおりだった）
3. ラベル追加は `ALTER COLUMN "Labels" SET MULTI_SELECT(全55件＋新規)`。返ってきた state で 56 件・既存 option URL 不変（`pipeline` の ID で確認）を数える

## 落とし穴

- **SQL モードの Status と fetch の Status が食い違った**（SQL=doing／fetch=waiting・last_edited 9/13 14:49）。書き込み前の実物は **fetch** を正とする。更新は冪等なので迷ったら書いてから fetch で読み返す（書き込み後 fetch で doing・UpdatedAt 9/14・結果要約1行を確認）
- `git status` が clean でも、数分後の Edit までに並列編集者の追記が着地する（今回はサトルの「現在地」「ログ」16行が -001 に入った）。**並列編集中のチケットは最初から cacheinfo 方式**（HEAD＋自分の1行の blob を index に載せ、working tree は触った状態のまま残す）。`knowledge_parallel_ticket_edit_stage_own_hunk.md` の型をそのまま使った
- handover は「🆕 節の冒頭に小節を足す」＋「最終更新の日時・次セッションの主題」の2点。9/13 の到達点・初動は残し、初動のどれが無効になったか（1 は無効・2/3 は据え置き）を書く。消すと再開者が「なぜ判断12点が無いのか」を辿れない

## 日付

作業日＝事実日＝2026-09-14。ログ・owner-tasks・handover・memory すべて同日。
