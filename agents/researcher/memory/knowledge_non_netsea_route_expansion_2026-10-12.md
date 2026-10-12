# NETSEA 停止中に他の経路を厚くする手順（2026-10-12 / T-20260920-003）

依頼の型：「NETSEA 以外の卸（SD・国分）から買える商品を台帳に足せ。上限なし・ラウンドロビン」。

## 手順（再利用）

1. **JAN の出所は NETSEA 索引でよい。**`pipeline/netsea_jan_index.json`（10/01・67,667 JAN）に、SD 出展企業と同じ会社の店（Drop ハリマ 5,000／ヤザワ 4,998／国分 3,532／不二貿易 2,242）が丸ごと入っている。**SD を叩かずに同じ会社の商品台帳が手に入る**
2. 入力 CSV を作り（`supplier_screen/input_rr3_*.csv`）、`supplier_screen.py run --tokens N --wait` で Keepa 逆引き＋採点。未取得 JAN は `state/jan_seen.json` に残り、次回は続きから
3. 国分は `kokubu_lookup.py`（法務判定50 §5 を実装：10秒・500回/日・停止トリガ・規約ハッシュ・名乗る UA・「無し」と「失敗」を分ける・生 HTML 保存）→ `supplier_feed_build.py kokubu-input` → `supplier_screen.py run ... --label kokubu` → `kokubu-route`
4. 台帳へは `supplier_feed_build.py feed <screen CSV>` で `ledger20261010/new_supplier_candidates_<日付>.csv` を作り、`ledger_refresh.py` の `score_feeds()` が既存行と同じ `S.build` で採点して追記する。国分の値段は `kokubu/kokubu_route_override_*.csv` を route_to_sd が読んで経路を「国分ネット卸」に切り替える
5. SD 出展企業の行で価格以外では落ちていない行は `supplier_feed_build.py sd-queue` で `sd_buylist20261009/sd_queue_<日付>.csv`（カズヨの Chrome 用。JAN 検索 URL・実績枠/B/A の卸1点上限）

## 数字（分母つき）

- **Keepa の code 逆引きは JAN の約95%が Amazon に当たる**（4社・当日分）。ただし **1 JAN あたり平均 5〜9 ASIN**（セット品の口）が返り、課金は商品数。ハリマは約9.5 ASIN/JAN。**20トークン/分の補充では1時間に約150〜250 JAN**。15,772 JAN を一巡するには数日かかる＝上限ではなく速度の問題
- 国分：照会 498件（10秒間隔・停止トリガ0回）。**国分索引に既知の JAN は 35件中29件が有り。Amazon 起点のブランド重なりは 389件中3件（0.8%）**。Amazon の売れ筋 JAN を国分に当てても当たらない。**照会順は「Keepa で Amazon に当たった国分索引の JAN」を先にする**
- 国分の32 JAN → 201 ASIN：**GO 0・NO-GO 198・UNKNOWN 3**。手残り0円以上は1件（胡麻麦茶・取り分1.3・在庫月数9か月で実績枠にも入らない）。国分の値段は Amazon 売価に近い
- 🔴 **国分の送料は買うほど上がる**（関東 4,000円未満790円／8,000円未満1,480円／以上1,970円）。1ケース買いでは送料按分が1点60〜790円。原価に入れて明記した（按分前のバラ単価はメモ列）

## 気づき

- **`pgrep -f <名前>` で待つループは、ループ自身のコマンド行に名前が入るので永久に終わらない。**PID を控えて `kill -0 <PID>` で待つ
- 国分の商品ページで在庫は「買物かごへ」／「在庫お問合せ」（品切れ）／「取り寄せリクエスト」のボタンで分かる。**ページ下部の「取り寄せリクエストが表示されている場合は…」は全ページ共通の注意書き**なので、本文検索で取り寄せと判定すると全件誤る。ボタン領域（`div.buttons_`）だけを見る
- 国分の販売単位はケース。`販売価格(税抜)`＝ケース、`販売価格バラ(税抜)`＝1点。入数＝ケース÷バラ
- `nohup python3` は出力がバッファされてログが空に見える。`-u` を付ける
- 共有キーの残高は他のジョブ（クラウド側の夜間など）でも減る。開始直後に 1,200 → 186 に落ちていた
- 🔴 **「台帳に既存か」を `ledger20261010/after_*.json` の最新で判定すると、`after_dryrun.json`（書いていない台帳）を掴む。**dry-run で足した153行を「既存」と誤って feed から落とした。`after_dryrun.json` は除外する（supplier_screen.ledger_asins も同じ穴・タカシへ申し送り）
- 台帳の採点（ledger_refresh）は新規 ASIN の実売を `kz_estimate_*.csv` からしか読まない。supplier_screen が計算した再現値を `kz_estimate_<日付>_supplier.csv` に書き出さないと、screen で NO-GO と分かっている行が台帳では UNKNOWN（960件）に化けて段階解消のキューを水増しする。書き出したら UNKNOWN 345件に減った
- 本書き込みの前に dry-run の before と after を ASIN で突き合わせ、**既存行の判定変化**を数える（今回2件）。並行してタカシが同じファイルを編集・同じシートを書いていた（実績枠・unknown_stages）。auto-sync が30分ごとに commit するので、自分の変更が他人の commit に混ざることがある

## 結果（2026-10-12）
台帳 2,238→4,504行。新規 2,266行：GO 0／実績枠 0／UNKNOWN 377／NO-GO 1,889。経路 NETSEA 87.4%（値段の出所が NETSEA 索引のため）。SD の値段確認キュー 206 ASIN。成果物 53
