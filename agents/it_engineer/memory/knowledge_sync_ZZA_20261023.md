# ZZA 同期（2026-10-23）と入口の本体カート除外

## 手順（ZZ と同じ型で通った・再利用可）
1. 退避：`agent_output/T-20260930-001/sheet_dump_formula.py <out.json>`（gspread で全タブ FORMULA → JSON）＋ 40/63/各 .py を `.bak_<組>_<MMDD>`。agent_output の .py は deliverables への symlink なので `cp -p` で実体が退避される
2. `40_profit_cols.py --offline` → deliverables で test_criteria_check / test_dashin_order
3. sync dry → 本番×2（シート JSON・63・ログを cmp）→ dry（1回目 dry と diff、本番ログとは「dry-run」行だけ違う）
4. 前後比較は `sheet_cmp_before_after.py <前.json> <後.json>`。キー＝(正式社名, 代表ASIN(タカシ))。見る列：接触ステータス・接触日・メモ・採算メモ（「メモ」で部分一致すると採算メモも拾う＝害はない）。打診順は「第1弾/第2弾」の頭で数え、新規行の打診順と判定を並べれば報告がそのまま書ける
- 注意：dry-run でも 63_打診第1弾.csv は書き換わる（シートだけ書かない）。.bak は dry の前に取る

## 数え方
- 入力107 → シート+100。差7は key_of（正式社名）重複の吸収（未特定4・既存同社3）。毎回「入力−増分」を内訳まで説明する
- 酒類はサトルが判定欄で「除外」にすると「対象外（判定：除外）」に入り、「酒類：販売免許なし」は増えない。報告で「酒類で落ちた社」を聞かれたら両方を見る

## 本体カートの穴（56_entry_f の build）
- 層判定は本人カート疑い（self_cart）と規模しか見ておらず、buyBoxSellerId=AN1VRQENFRJN5（Amazon.co.jp）が層1〜3に残っていた（晴香堂・REGiSTA・EPOS・気仙沼ほてい・ISSE の5社）
- 2026-10-23 に cand ループで一次除外を追加（Keepa 追加0 token・キャッシュの sid で判定）。既存キューは追記型なので遡って直さない
- 判断：「入口で落とせるものは入口で落とす」。サトルの窓口集め（1社数分＋Web検索枠）を本体カートの棚に使うのは無駄。§3.3-22 の通り判定の根拠は「いまカートを誰が持つか」なので sid で切ってよい

## ZZB 同期（2026-10-23 早朝・同じ手順で2回目も通った）
- 13行入力 → シート+12。差1は MOLDEX（batchZT と正式社名キーが同じ＝吸収）。サトルの「重複」判定行は既存行と同社キーだと吸収されるが、30_最終 側の重複（Peaker）は社名が違うので新規行になる＝「入力−増分」は重複判定の件数と一致しないことがある。毎回 sheet_cmp の new 一覧で確かめる
- 第1弾 173→174（コスモテック）。所要 約10分（シートダンプ3回が大半）
- 退避リストの 56_entry_f.py は agent_output に無い（deliverables 側のみ・同期では不使用）。cp がそこで止まるので、同期の退避は 40/40_採算列/63/criteria/dashin/sync_ledger の6本で足りる
- `timeout` コマンドは macOS に無い。使わない
