# -*- coding: utf-8 -*-
"""② 仕入れ周りの詳細フロー（出品可否チェック→制限解除→発注）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(12.5, 16.5, (0, 16), (0, 20),
         title="② 仕入れ周り 詳細フロー（出品可否チェック→解除→発注）")

# main spine x=5.2
f.box("start", 5.2, 19.0, "リサーチで仕入れ候補を発見\n（ASIN / JAN を特定）", "start", w=4.6, h=0.95)
f.box("PRE", 5.2, 17.5, "【事前準備】出品アカウント開設済 /\nChrome拡張「ショッピングリサーチャー」導入", "info", w=5.2, h=1.0, fs=10.5)
f.box("S1", 5.2, 15.5, "STEP1 出品可否チェック\nセラーセントラル＞カタログ＞商品登録\n＞ASIN検索＞コンディション選択", "gate", w=5.4, h=1.5, fs=10.5)
f.box("T", 5.2, 13.0, "トラップ確認（2点）\n①「ノーブランド品」エラーが出ない?\n②「新品」を選べる?", "gate", w=5.0, h=1.4, fs=10.5)
f.box("S3", 5.2, 10.8, "STEP3 利益計算\n真の利益・利益率20%以上か（→Go/NoGo）", "step", w=5.0, h=1.05, fs=10.5)
f.box("S4", 5.2, 9.2, "STEP4 仕入れ先を選ぶ\n（仕入れ先リスト：予算/時間/ジャンルで）", "step", w=5.0, h=1.05, fs=10.5)
f.box("S5", 5.2, 7.4, "STEP5 発注・決済・領収書PDF取得", "step", w=5.0, h=0.95, fs=11)
f.box("S6", 5.2, 5.9, "STEP6 仕入れ記録CSVに記入（月別ログ）", "step", w=5.0, h=0.9, fs=11)
f.box("END", 5.2, 4.5, "→「6. 出品・カタログ登録」へ", "start", w=4.6, h=0.85, fs=11)

# side boxes
f.box("DEAD", 1.7, 13.0, "出品不可\n→別販路 or 後日再確認\n→候補から外す", "dead", w=2.9, h=1.25, fs=10)
f.box("S2", 12.6, 14.0, "STEP2 出品制限の解除\nカテゴリ制限→現物写真を複数枚UP(簡単)\nブランド制限→3段階解除（別図③）", "rel", w=5.0, h=1.55, fs=10)
f.box("NOTE", 12.6, 7.4, "【領収書の必須条件】\n①180日以内 ②氏名・住所が一致\n③仕入先の名前・住所が記載\n④10点以上購入\n※Amazonからの仕入れは絶対NG", "health", w=5.0, h=1.9, fs=10)

# main arrows
f.arrow("start", "PRE")
f.arrow("PRE", "S1")
# S1 -> 3 branches
f.arrow("S1", "T", label="「この商品を出品する」")
f.arrow("S1", "DEAD", fa="left", tb="top", label="「出品情報のコピー」", color="#888", lc="#777", rad=-0.1)
f.arrow("S1", "S2", fa="right", tb="top", label="「出品を申請」(制限あり)", color="#d6a400", rad=0.1)
# T branches
f.arrow("T", "S3", label="OK（制限なし）")
f.arrow("T", "DEAD", fa="left", tb="right", label="NG", color="#888", lc="#777")
# S2 -> S3 (解除できたら)
f.arrow("S2", "S3", fa="bottom", tb="right", label="解除完了", color="#d6a400", rad=-0.25)
# spine continue
f.arrow("S3", "S4", label="Go")
f.arrow("S4", "S5")
f.arrow("S5", "S6")
f.arrow("S6", "END")
# NOTE link to S5
f.arrow("NOTE", "S5", fa="left", tb="right", color="#e67e22", style="dotted", rad=0.0)
# NoGo from S3 back (note)
f.note(2.0, 10.8, "NoGo→\n候補から外す", color="#b00", fs=9.5)

f.save(os.path.join(os.path.dirname(__file__), "02_sourcing-flow.png"))
