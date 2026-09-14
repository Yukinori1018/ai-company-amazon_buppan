# 外部 API を解約する前の「依存の棚卸し」の型（2026-09-14 / T-20260912-002）

Keepa API（€49/月）を「必要な月だけ」にする社長判断の材料として、Keepa を呼ぶ社内ツールを棚卸しした。
**「この API を解約して大丈夫か」と聞かれたら、この手順で30分で出せる。** 成果物: `deliverables/T-20260912-002/08_Keepa依存の棚卸し.md`

## 手順（再利用可）

1. 定常ジョブを先に見る（壊れて困るのは無人で回っているもの）
   - `ls ~/Library/LaunchAgents/` → 各 plist の `ProgramArguments` を plistlib で出す
   - `launchctl list | grep aicompany`（2列目＝最後の終了コード）／`crontab -l`
   - `~/.claude/scheduled-tasks/*/SKILL.md`、`.claude/hooks/`、`.claude/launch.json`
2. コードは **deliverables と agent_output の両方**を grep する。T-1 や第一陣のスクリプトは agent_output にしか無い（deliverables だけ見ると3系統を落とす）
   - 呼び出しの実体で絞る: `grep -rlE "api\.keepa\.com|adapters\.keepa|import scan_v14|keepa_verify"`。単に `keepa` で grep すると、列名やコメントで100件超に膨らむ
3. 実際に今消費しているかを API で確かめる。Keepa は `/token?key=` が **0 token** で残高・`tokensConsumed`・`tokenFlowReduction` を返す
4. 各ツールに「次に使う予定」と「API が無い月の代わり」を付ける。ファイル数ではなく**用途（系統）で数える**
5. 期限までに API で済ませる抽出は、単価×件数を実測ログから出し、`(合計 − 1,200) ÷ 20` 分で所要時間を出す

## 踏みかけた罠

- **`grep -i keepa` は plist の `KeepAlive` に当たる。** openclaw・pomodoro・catalog-server が「Keepa を使うジョブ」に見えた。plist は `-w` か実体のパターンで見る
- **`/token` の応答は gzip**（Accept-Encoding を付けなくても圧縮で返ることがある）。`json.load(urlopen())` は UnicodeDecodeError で落ちる。`gzip.decompress` を挟む
- 鍵は表示しない。`~/.config/ai-company-amazon-buppan/keepa.env` → `agent_output/T-20260521-005/code/.env` の順に読み、使うだけにする

## 事実（公式・2026-09-14 取得）

- **解約しても、支払済みの期間の終わりまで API は動く。** 期間中は再開でき、切れた後は再開できず新規契約（`keepa.com/api-docs/plans-tokens.html`）。→ 解約操作を早めても抽出の期間は減らない。解約忘れ＝自動更新
- product オブジェクトに **`brandStoreName`／`brandStoreUrl`／`brandStoreUrlName`** がある（`product-object.html`）。ブランドストアの有無は商品ページを開かずに 1 token/ASIN で取れる
- `buyBoxSellerIdHistory` は `offers` か `buybox` を付けたときだけ返る。`buybox=1` は +2 token/ASIN（計 3 token/ASIN）
- `/search`（type=product）は 10 token/クエリ（T-20260906-005 の実測）

## 結果（この回）

- 系統10（うち1系統は取得済みデータを読むだけ）・定常ジョブ1（list-builder・8/31 から STOP）・当日の消費0
- 解約で壊れるのは手動の3つ（出品前の再計算・打診先の検証・需要先行スキャン）。自動で壊れるものは無い
- 10/3 までの抽出 T-3＋S-3 は約1.4万〜2.2万 token。供給は19日で約55万 token あり、間に合う。制約は token ではなく「誰がいつ走らせるか」

関連: [[knowledge_keepa_billing_is_flat_rate]] [[knowledge_launchd_always_on_jobs]] [[knowledge_keepa_token_ceiling_and_unattended_scan]] [[knowledge_buybox_price_recalc]]

## commit の落とし穴（この回に踏んだ）

`git add <自分のファイル>` だけにしても、**他の担当が先に index に載せた行は一緒に commit される**。b76fca5 に、マリエが載せていた `done/T-20260914-005` のログ1行が入った（中身は失っていない。マリエ側も 118d1ac で記録）。
並列作業中は、add の前に `git diff --cached --name-only` を見る。空でなければ、`git commit -- <自分のファイル>`（パス指定の commit は index の他の変更を含めない）を使う。
