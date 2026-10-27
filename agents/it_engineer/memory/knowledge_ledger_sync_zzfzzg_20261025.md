# メーカー連絡先台帳 ZZF・ZZG 同期（2026-10-25 夜間・T-20260930-001）

## 再利用できる手順
1. 退避：`python3 sheet_dump_formula.py sheet_backup_before_<batch>_<date>.json`（全6タブ FORMULA）＋ 40_profit_cols・40_採算列・63・criteria_check・dashin_order・sync_ledger を `.bak_<batch>_<MMDD>`
2. `python3 40_profit_cols.py --offline`（新しいバッチの行を足す。Keepa 0 token）→ test_criteria_check / test_dashin_order / test_listed_mark
3. `sync_ledger.py --dry-run --through=<batch> --recheck=recheck,recheck2 --unchecked-out=64_…後.csv` → 本番2回 → `sheet_cmp_before_after.py 前.json 後.json` で消えた行0・社長入力列の変化0を確認
4. sync_ledger の本番は1回60秒超かかる。2回＋dump を1コマンドに詰めると 120 秒のタイムアウトで背景に回る（結果は通知で受ける）

## 罠：同じ社の「窓口だけ取り直し」バッチ（ZZF）は batch として足しても効かない
- 重複除去は「先に読んだ行が勝つ」。ZZF（バクマ工業）は ZZD 6034 と同じ代表ASINなので、24_連絡先_batchZZF.csv を --through に入れても ZZD 側（＋recheck_20261024）の窓口未調査の行が残る
- 正しい口：**`24_連絡先_recheck_<date>.csv` に ZZF の行を写して代表ASINで差し替える**（後の日付が勝つ）。正式社名を ZZF と同じにしておけば ZZF の batch 行は同じキーで自然に吸収される
- 秘書の除外判断（タニカ＝本人カート）も同じ recheck ファイルに「判定」を書き換えた行で入れる（10/24 aib と同じ型）

## 罠：紐付けの判定「確認済み（…）」は4値に無いので未確認に落ちる
- `do.link_verdict` は「一致／一致（表記ゆれ）／一致（ブランド単位）／未確認」の接頭辞だけを読む。サトルが「確認済み（型番のハイフン位置のみ表記ゆれ）」と書くと**未確認**→検算で第1弾・第2弾から外れる（dry-run 1回目でバクマが「検算で外した」に出た）
- 直し方：recheck 行で `一致（表記ゆれ）` に読み替え、原文は備考に残す。発注文側でも「紐付けの判定は4値で書く」をサトルに再度伝えるべき（knowledge_ledger_link_verdict_four_values_20261014 の再発）
