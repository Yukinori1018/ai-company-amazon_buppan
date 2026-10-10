# 夜間の仕入れ走行：ラウンドロビンと「在席必須レーン」の扱い（2026-10-10）

## この依頼はこう処理した（再利用できる手順）
1. 現在地を読む：`pipeline/nightly.log` 末尾・`daily_token_budget.json`・`tried_jans.json`・`roundrobin_state.json`・
   SD の `sd_jan_backoff_state.json`（**2か所ある**：`sd/` と `sd_buylist20261009/`。新しい方は後者）・Keepa `/token`。
2. NETSEA：`26_候補提案パイプライン/nightly.sh` を nohup で起動 → `until grep 終了` を background で待つ。
   既定 1日6,000トークン（段A 4,000／段B 2,000）。残高1,200・補充20/分なので**約4〜5時間**かかる。
3. SD：**夜間は SD へリクエストしない**（下記）。SD を叩かない作業（手元行の Keepa 突合）だけやり、在席時のコマンド一式を
   `pipeline/nightly_stop_note.md` に書く。
4. 構成比：`pipeline/composition.py`（経路／ブランド／カテゴリー・分母併記・80%超を🔴）。
5. 整合検査：`consistency.py check … --show` と `autofill.py`。

## 🔴 SD の照会は「在席必須」。夜間指示でも `--attended` を付けない
- 法務判定 成果物29 §5 条件3「人が在席していて、すぐ止められる時間帯のみ。夜間自走・/loop は禁止」。
  `28_SD突合/_budget.py` が `--attended` 必須で実装済み。
- 秘書の夜間指示は「間隔10秒・1日30回」だけを書いていて在席条件が落ちていた。**フラグを付ければ動くが、それは
  自社の記録に嘘の在席を残すこと**（§3.3-14）。止めずに「在席時に1コマンドで流せる束」を用意するのが正解（§3.3-18）。
- 次の人のために：lane A の次の JAN リスト（`laneA_jans_next.txt`）は `buylist20261009/all_rows.csv` の
  `経路≠NETSEA × 月販あり × カート非Amazon` から、`laneA.log` の実行済みを除いて作る。JAN は Keepa 生データの `eanList`。

## ラウンドロビンの実装（`run_supplier_first.py --order roundrobin`・既定）
- NETSEA 索引にブランド欄が無いので**出店者（shop_id）20件単位**。tier（黒字の見込み順）の中で回す。tier を崩すと楽な棚を先に見る利点が消える。
- **カテゴリーは JAN 段階では分からない**＝事前に回せない。事後に構成比で検査する。
- 上限ではなく順番。`plan()` と同じ集合を並べ替えるだけ（集合一致をテストで確認）。

## カテゴリーの「不明」は手元の Keepa 生データで埋まる（0トークン）
- 候補 CSV のカテゴリー列は9割空だったが、`resolve_raw.jsonl`／`keepa_raw.jsonl`／`refetch20261004/raw.jsonl` の
  `categoryTree[0].name` で **89% → 5%** に。`pipeline/asin_category_map.json`。

## 整合検査 252行 NG の原因（数字は合わせていない）
- `score20261004/all.csv` は 10/04 の原価モデル（外注25円・1箱30点）で計算。10/09 にハジメが `fba_cost.other_costs` を
  おりおん実額へ差し替え（commit 334ff4b3）。検査は新モデルで再計算するので、**その他固定費が全252行でずれる**。
  検出器は正しく働いている。直すのは表の再生成で、検査の閾値ではない。
