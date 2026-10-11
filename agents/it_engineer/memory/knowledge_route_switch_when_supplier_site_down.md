---
name: knowledge-route-switch-when-supplier-site-down
description: 卸サイトが止まったとき、同じ購入元の別サイトに仕入れ経路を切り替えて採算し直す手順（2026-10-11 NETSEA停止→SD）
metadata:
  type: knowledge
---

# 仕入れ経路の切替（NETSEA 停止 → SD・T-20260920-003・2026-10-11）

## 手順（再利用できる形）
1. 切替先の仕入れ値は**人の実画面**で取る（カズヨ）。値は agent_output の override CSV（sd_route_override_<日付>.csv）にだけ置き、列の定義はそのファイルのヘッダを見る
2. `ledger_refresh.route_to_sd`：行をコピーして原価・URL・ロットを差し替え、**その JAN を外した NETSEA 索引**で `S.build` し直す（索引に当たると NETSEA の在庫・channel が残る）。#17 仕入れのゲートは切替先の実画面在庫で付け直す
3. main の分岐（卸サイト=SD の行は SD 処理へ）に、override の ASIN を例外として通す。通さないと次回から SD 行として扱われ、sd_candidates に無いので**黙って凍結**される
4. 検証は「新コードの dry-run」と「HEAD のコードの dry-run」を突合する。差の行が切替対象＋意図した行だけかを見る（今回 38行：SD 行・FLR910・90日窓の時刻ずれ4件）

## 学び
- 段階価格（例：1点・10点・200点で単価が下がる）は**最小口の単価**で採算する＝利益を多く見せない側。まとめ買いの段はメモに残す
- before（get_all_values＝表示文字列）と after（Python 値）は型が違う。数値を正規化してから比べないと「人の行が全部変わった」ように見える。卸率は % 書式バグ（32.9→3290%）でさらにずれる
- SD の卸値は NETSEA より約3割高く、FLR910 の利益率は 24.8%→11.2%。B 等級は「中央5% or 手残り400円」なので GO は維持。同じ購入元でも卸サイトで3割違う
- 照会キュー（yazawa_sd_queue.py）は econ_at と同じ式で原価を二分探索して「B に必要な卸1点上限（税抜）」を出す。売り切り月数が推定＝最高 B なので A 上限は常に0、列から外した
