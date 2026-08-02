# -*- coding: utf-8 -*-
"""④ 出品〜FBA納品の詳細フロー（仕入れ済 → FBA倉庫に届くまで）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(13.0, 17.5, (0, 16), (0, 21),
         title="④ 出品〜FBA納品 詳細フロー（仕入れ済 → 倉庫到着・販売可能化）")

# spine x=5.0
f.box("ST", 5.0, 20.0, "仕入れ完了（商品到着・検品済）\n領収書PDFも保管済", "start", w=5.4, h=1.0, fs=11)
f.box("S1", 5.0, 18.0, "STEP1 出品登録（既存ASINに相乗り）\nセラーセントラル＞カタログ＞商品登録\n＞ASIN検索＞コンディション＝新品", "step", w=6.2, h=1.55, fs=10.5)
f.box("S2", 5.0, 15.7, "STEP2 価格・在庫を設定\n・現在のカート価格と±数円で攻める\n・在庫数を入力（不足→機会損失／過剰→保管料）", "step", w=6.4, h=1.5, fs=10.5)
f.box("S3", 5.0, 13.4, "STEP3 出品形態＝FBA を選び「納品プラン」作成\n・梱包要件は「メーカー梱包そのまま可」か確認\n・危険物該当性チェック（リチウム電池/エアゾール等）", "step", w=6.8, h=1.6, fs=10.5)
f.box("S4", 5.0, 11.0, "STEP4 商品ラベル(FNSKU)を印刷・貼付\n・JANを覆うように貼る（バーコード二重NG）\n・透明OPP袋に入れて1商品1袋", "step", w=6.4, h=1.55, fs=10.5)
f.box("S5", 5.0, 8.7, "STEP5 配送先倉庫の確定\n・倉庫分割が出たら統合可否を判断\n・パートナーキャリア(ヤマト/日本郵便)か自己手配を選択", "step", w=6.6, h=1.6, fs=10.5)
f.box("S6", 5.0, 6.3, "STEP6 外装ラベル(配送ラベル)を印刷・貼付\n・1箱=1ラベル／重量20kg・三辺合計170cm以内", "step", w=6.4, h=1.5, fs=10.5)
f.box("S7", 5.0, 4.2, "STEP7 集荷依頼 or 持ち込み発送", "step", w=4.8, h=0.9, fs=11)
f.box("S8", 5.0, 2.7, "STEP8 倉庫到着・受領（数日〜2週間で在庫反映）", "step", w=5.6, h=0.9, fs=11)
f.box("END", 5.0, 1.2, "→ 販売可能（フロー①「8. 販売」へ）", "start", w=5.2, h=0.85, fs=11)

# side notes
f.box("D1", 12.4, 15.7, "【危険物該当時】\n・FBA禁止 or 専用納品プラン必要\n・該当判定はSDS提出を求められる\n→該当なら一時自己発送に切替", "health", w=4.8, h=1.85, fs=9.5)
f.box("D2", 12.4, 11.0, "【ラベル貼りの事故】\n・JAN残し→FBA倉庫で別商品と混在\n・FNSKU間違い→他出品者の在庫に\n→「メーカーバーコード」設定NG、\n　必ず「Amazon商品ラベル」設定で", "health", w=5.0, h=2.1, fs=9.5)
f.box("D3", 12.4, 8.7, "【倉庫分割の判断】\n・小ロットは1倉庫追加料金を払って統合\n・大ロットは分割のまま分けて発送\n　（送料分岐点≒2,000円/箱）", "info", w=5.0, h=1.7, fs=9.5)
f.box("D4", 12.4, 4.2, "【パートナーキャリア】\n・ヤマト指定→1箱600円〜\n・自己手配→佐川/福通の法人契約検討\n　(月10箱以上で割安)", "info", w=5.0, h=1.65, fs=9.5)

# arrows
for a, b in [("ST","S1"),("S1","S2"),("S2","S3"),("S3","S4"),("S4","S5"),
             ("S5","S6"),("S6","S7"),("S7","S8"),("S8","END")]:
    f.arrow(a, b)

# side notes link (dotted)
f.arrow("D1","S3", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("D2","S4", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("D3","S5", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("D4","S7", fa="left", tb="right", color="#16a085", style="dotted")

f.save(os.path.join(os.path.dirname(__file__), "04_listing-fba-flow.png"))
