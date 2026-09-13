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

## 追記：子の done 同期セット（同日・-001 done／-002 doing・commit e70bd1c の後）

1 turn で閉じた順番（再利用可）：
1. 実物照合：`ls tickets/*/`・`git ls-files deliverables/<id>/`・チケット直下 `.gitignore` を読む。今回 `out/` と `*.csv`（`!stats_*.csv` 以外）が追跡外。**追跡外は Notion でもカタログでもリンクにしない**。Notion は「ローカルのみ」と1行注記、カタログは 01 本文行の備考へ逃がす
2. 配信 URL を curl で 11本すべて 200 確認してから Notion に貼る
3. Notion は `update_properties`（Status・UpdatedAt）と `update_content` を別呼び出し。成果物節は既存の「（作業中 — 納品時に配信URLを追記）」を old_str にして置換（insert_content だと重複）。結果要約は最後の bullet をアンカーに追記。親は「…目安 9/15〜16）。\n## 成果物」をアンカーにすると一意に当たる
4. fetch で3枚読み返し（Status と本文）
5. カタログ CSV は **CRLF・15列**（skill の「13列」記載は古い。実物は 公開状態・ローカルリンク を含む15列）。`csv.writer(lineterminator='\r\n')` で追記→列数集合 {15} を検算→同期（今回は一発 HTTP 200・735行）
6. スクリプト3本は1行に集約（代表 recut.py・備考に同梱2本）

気づき：`deliverables-catalog.md` §2 は「13列」のまま。実物は15列。次に skill を触る機会で直す（今回は発注範囲外なので未修正）。

## 追記：計画納品（doing 継続）＋ 次段 todo→doing の同期セット（同日・更新㉕・commit aff72e2 の後）

- 型：前段は「納品したが doing 継続」（検証待ち）、次段は todo→doing。**社長タスク増減ゼロ**なので owner-tasks は冒頭の新節と ℹ️ の1行を書き換えるだけ（🔴/🟡 は触らない）
- Notion は4回の書き込みを並列に実行：-002 は update_content 1回（最後の bullet ＋「## 成果物\n（未着手）」を old_str に指定して結果要約と成果物を一度に置換）／-003 は update_properties と update_content を別々に呼ぶ／親は「→ -003 todo（マサル）。社長タスク増減ゼロ。\n## 成果物」をアンカーにした
- **落とし穴（新規）：Notion は本文中の `xxx.py` を自動でリンク化する**（`00_cf_[base.py](http://base.py)` のようになる）。リンクにしないファイル名はバッククォートで囲む。読み返しで見つけて `update_content` で直した。次回からは最初からバッククォートで書く
- カタログ：出力 txt と json の片方はスクリプト行・代表行の備考に入れて集約し、-002 は7行・-003 は4行。追記後に列数 {15} を確認→同期（1回目で HTTP 200・746行）
- 並列編集：-002 はサトル S-2（`03_S2_SD会費.md`・README 変更・`.gitignore`）が作業中で、working tree が HEAD と違っていた → cacheinfo 方式でログ1行だけを commit。-003 は HEAD と同じだったが、手順を揃えて同じ方式にした
