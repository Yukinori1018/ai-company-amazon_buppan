# recheck に秘書判断を足して同期（2026-10-26 夜間・T-20260930-001）

## 手順（ZZG と同じ型・スクリプト修正なしで通った）
退避（sheet_dump_formula＋6本 .bak＋サトルの recheck 原本 .orig_satoru）→ recheck に秘書判断を書き込む → 40_profit_cols --offline → テスト3本 → sync dry → 本番×2 → dry → sheet_cmp_before_after。--through は最後の batch のまま（recheck は --recheck=recheck,recheck2 で日付順に拾われる）

## 罠：「接触候補に上げる」だけでは第1弾・第2弾に入らない
判定を接触候補にしても、次の3つが空だと dashin_order で落ちる。秘書判断を反映するときは全部埋める
1. 窓口（電話・メール・フォームのどれか）。サトルは「未確認」と書き、値は備考にしか無いことがある → 備考から電話を移す。無ければ「対象外（連絡先なし）」（今回 芳月堂）
2. 紐付けの判定（4値の接頭辞「一致」）＋根拠 URL（http）。根拠は rc1026/html の楽天ページのキャッシュの og:url で取れた
3. 62b/65 の実画面証跡。無ければ「出品可否 未実測」。§3.3-40 によりタカシが社長の Chrome で読む（既存タブで fetch・元の URL に戻す）。`62b_/65_…_RC2_<日付>.csv` として秘書の RC と別名で置く

## 社名変更行の「gone」は消失ではない
sheet_cmp の gone は（正式社名, 代表ASIN）キー。社名が埋まると23件 gone/new が出るが、同じ ASIN が後ろに残っていれば消失0。代表 ASIN で突き合わせて確認する
