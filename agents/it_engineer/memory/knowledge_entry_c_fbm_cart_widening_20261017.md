# 入口(c)＝カート自己発送の棚で母数を延ばす（2026-10-17 / T-20260930-001）

## 何をしたか
- 窓口集めキューが尽きたとき、Finder 条件のうち「中村本の3基準でも積極条件でもない当社の定数」を1本だけ外すと次の入口が作れる。
  残っていたのは `buyBoxIsFBA=True`（入口a/b の段5a）。False 側＝カートを自己発送の出品者が持つ棚
- 同条件で buyBoxIsFBA なし 33,600 / False 8,278（True ≒ a+b 23,600）。**Keepa Finder の Boolean は False 側も効く**（件数が変わることで確認・11 token/件の件数クエリ）
- 一覧 8,267 のうち 3,110 が既取得と重複（カートは日々 FBA⇄FBM が入れ替わる）。既取得 ASIN の除外は必須
- 結果：product 2,300 → 1,860 → 963社 → +255社（層3 が 218）。層4（本人カート疑い）は 6% で、心配したほど増えなかった

## 再利用できる型
- 入口の追加は `52_entry_b.py` のモジュール変数（TAG/ORDER/STATUS/SEL_B/LABEL/ENTRY_MARK/KNOWN_ORDERS/OLD_POOLS/OUT_*/BAK_TAG/RESERVE）を
  差し替える薄いファイル（`53_entry_c.py` 30行）で済む。新しい入口ごとに300行コピーしない
- 前の入口を OLD_POOLS と KNOWN_ORDERS に必ず足す（入れないと同じ社を再判定して token を食う）
- 共用キーでの夜間実行：各バッチ前に `wait_for(必要量+RESERVE)`。premium_watch と並走すると実効 約20 token/分 → 2.3時間で product 2,300 件＋カート保持者 254社が上限の目安
- リファクタしたら旧入口を `build --dry-run` して漏斗・落とした理由が前回の status と一致し、追加0社になることを確かめる（冪等の確認を兼ねる）

## 次に延ばすなら
- 入口(c) の残り 2,857 ASIN を先に（同じ手順）。その後の変数候補は「buyBoxIsUnqualified」（段5b・効きがほぼ0で母数にならない）くらいしか残っていない。
  次は Finder 条件ではなく、セラーリサーチ入口（50_expand.py の sellers）を入口(b)(c) のカート保持セラーで回すのが筋
