# SaaS／データ API を解約した後、取得済みデータを使い続けてよいか — 判定の型

初出：T-20260912-002（2026-09-14 ハルオ・Keepa API 解約前の確認）。成果物：`workspace/output/deliverables/T-20260912-002/10_Keepa解約後のデータ利用.md`
併読：`knowledge_keepa_tos.md`（Keepa 規約3本）／`knowledge_keepa_data_public_repo_judgment.md`（公開の判定）／`knowledge_platform_api_data_retention.md`（在籍中の保持期限）

## 1. 見る順番

1. 利用権の条項を「取得・表示の権利」と「保存物の利用権」に分けて読む。前者は契約期間に限られていることが多い。後者に期間の定めが無いか、"unlimited" / "perpetual" と書いてあれば解約後も使える。
2. 削除・返還の条項（"delete" / "destroy" / "return" / "upon termination"）を全文検索する。無ければ削除義務は無い。YouTube のような「30日で削除か更新」の型は在籍中にも効くので別に見る。
3. 保存物の利用権に付いた取消条件（未払い・チャージバック）を拾う。解約前にやることはここから出る。
4. 解約で制裁の形がどう変わるかを書く。遮断は効かなくなる。代わりに「再契約の拒否」（理由不要の契約拒絶条項）が効くようになる。再契約を前提にした計画なら、ここが一番不可逆。
5. 解約とアカウント削除を分ける。アカウント削除が契約終了の手段になっている規約は多く、請求書（電子帳簿保存法7条の保存対象）ごと消える。

## 2. Keepa の結果（2026-09-14・termsAPI.txt Version of July 28, 2026）

- §11(1) 第2文：retrieve and display は "limited to the duration of the contractual relationship"。
- §11(2)：save or print は "own business purposes" で "non-exclusive and unlimited"。取消は未払いのときだけ。→ 解約後も社内利用は可。削除義務の条項は無い。
- 公開・第三者開示は §11(2) の許諾の外で、解約後も不可。PUBLIC リポの HEAD は 2026-09-06 に列を削除済みで合っている。履歴には `月間ドロップ数` を含むコミットが23件（08-17〜09-06）残る。
- §14(3) の賠償上限は "during the Term" の文言で、解約後の請求に効くか不明確。
- §3(3)：理由を示さず契約を拒める。「必要な月だけ再契約」の前提を崩しうる唯一の条項。
- 無料サイトの ToS は自動化の利用者を "permanently banned" とする。解約後にスクリプトをサイトへ向けると再契約の道が閉じる。
- api-docs に Terms・License のページは無い（索引の全リンクで確認）。契約条件は termsAPI.txt だけ。

## 3. 今回の処理手順（再利用できる形）

1. `curl -s https://keepa.com/cdn/termsAPI.txt` → HTML タグを除去 → `grep -n -i "terminat\|delet\|retain\|store\|save\|surviv\|upon termination"`。
2. 条番号の見出し一覧（`grep -n "^[0-9]*\. "`）を出してから、§2・§11・§12・§13・§14 を全文で読む。
3. 社内の実態を実測する：追跡下の Keepa 固有列（`git ls-files | xargs grep -l`）、`origin/main` の有無、履歴（`git log origin/main -S'<列名>'`）、打診文に数字が入っていないか、Google シートの共有先。
4. 行為別の表（保存・集計・リスト化・判断・シート・打診文・公開・第三者提供）に落とす。
5. 解約前に秘書がやることを出す：解約はアカウント削除でなく cancel／請求書の保存／チャージバックしない／抽出の期限／サイトへの自動アクセス禁止／再契約時の版の確認。

## 4. 気づき

- 前回（T-20260904-004）推奨した Private 化は、社長判断で「しない・列を抜く」になっていた。これは既定なので蒸し返さない。解約で変わった前提（再契約の拒否）だけを、3点セットの撤退条件として足した。
- 依頼は「データを使えるか」だったが、実務で効いたのは「解約≠アカウント削除」と「解約後はサイトにスクリプトを向けない」の2点。依頼の範囲で終わらせない。
