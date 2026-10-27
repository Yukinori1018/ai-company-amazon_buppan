# ZZC・ZZD・ZZE 同期（2026-10-24）と「判定を変える秘書判断」の入れ方

## 手順（ZZA/ZZB と同じ型で通った）
退避（sheet_dump_formula.py＋6本の .bak）→ 40_profit_cols --offline → テスト3本 → sync dry → 本番×2（JSON・63・ログ cmp）→ dry → sheet_cmp_before_after.py。所要 約25分（sync 本番1回＋ダンプで約1分半ずつ。Bash の120秒を超えるので run_in_background＋until ループで待つ）

## 判定を変える秘書判断の筋
- **元の batch CSV は書き換えない。`24_連絡先_recheck_<日付>.csv` に全列の行を書き、判定・備考を直す**（列は batch の列＋「元の担当・順位／更新前の判定／差し替え前の代表ASIN」）。タグ recheck なら既存の `--recheck=recheck,recheck2` でそのまま読まれる。理由：サトルの原本が残り、何をいつ誰の判断で変えたかが追える
- **判定を変えない事実の追記（他担当の行への寄せ）は sync_ledger.py の RC_MERGES に1行足す**（代表ASIN・列・文）。recheck 行を作るより軽い
- 判定の文字列は明示が勝つ（BIG_RE は判定が空のときだけ効く）。備考に「大手」と残っていても判定が接触候補なら接触候補

## 落とし穴
- **大手→接触候補に戻すと、窓口（電話・メール・フォーム）が空**。サトルは大手の窓口を採らない。基準OKでも「対象外（連絡先なし）」になる（今回バクマ）。規模の線を動かしたら窓口の有無も見て、無ければ窓口集めを秘書に返す
- 接触候補に戻した行は 62b/65 も無い。社長の Chrome の既存 sellercentral タブで `fetch('/hz/approvalrequest/restrictions/approve?asin=…&itemcondition=New')` → DOMParser で読める。Amazon 商品ページは別オリジンなのでタブを amazon.co.jp に navigate して `/dp/<ASIN>` と `/gp/product/ajax/aodAjaxMain?asin=…&filters={"new":true}` を fetch、終わったら元の URL に戻す（閉じない・新規タブを作らない）
- 拡張の出力フィルタが URL・クエリ風の文字列を含む結果を `[BLOCKED: Cookie/query string data]` で全部潰す。**結果は和文と英数字だけに正規表現で削ってから返す**／window 変数に溜めてから別呼び出しで出す
- 規模の線（2026-10-24 秘書固定）：「300人超 **かつ** 資本金3億円超で大手」。自己資本・売上は資本金ではない（トヨトミの「自己資本92億円」）
