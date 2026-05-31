# -*- coding: utf-8 -*-
"""③ 出品制限の3段階解除フロー（コストを抑える順番）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(12.5, 16.0, (0, 16), (0, 20),
         title="③ 出品制限の解除フロー（コストを抑える3段階）")

f.box("start", 5.0, 19.0, "出品制限の解除が必要\n（STEP1で「出品を申請」と表示）", "start", w=5.0, h=0.95, fs=11)
f.box("Q", 5.0, 17.3, "制限の種類は？\n（申請画面の一番上に表示）", "gate", w=4.8, h=1.0, fs=11)
# category branch
f.box("CAT", 11.8, 17.3, "カテゴリー制限\n→現物の商品写真を複数枚UP\n（明るい場所・型番くっきり）\n＝簡単に解除", "rel", w=4.6, h=1.5, fs=10)
# brand 3-step
f.box("B1", 5.0, 15.0, "第1段階：0円解除\n直近半年の「無関係な領収書」(水・日用品等)で申請\n→マイナーメーカーは通ることが多い", "step", w=6.6, h=1.25, fs=10)
f.box("B2", 5.0, 12.6, "第2段階：1点だけ購入\n該当メーカーをヨドバシ等で「安い順」検索→最安1点購入\n→1点分の領収書でも通ることがある（数円〜数百円）", "step", w=6.8, h=1.3, fs=10)
f.box("B3", 5.0, 10.1, "第3段階：10点で王道申請\n同じ商品を9点買い足し合計10点の領収書で申請\n※高額品は「今後ペイできるか」を判断（無名ならスルーも可）", "step", w=6.8, h=1.35, fs=10)
f.box("TIP", 12.4, 12.6, "【承認率UPの工夫】\n領収書に赤枠＋注記\n（注文日/氏名住所/商品名/\nJAN/数量を赤枠）\n＋補足スクショを2P目以降に", "info", w=4.8, h=1.9, fs=10)
f.box("OK", 5.0, 7.8, "解除できたら → 落とし穴チェックへ", "start", w=5.2, h=0.85, fs=11)

# pitfalls
f.box("P", 5.0, 6.0, "解除したのに出品できない3つの落とし穴", "gate", w=7.4, h=0.8, fs=11)
f.box("P1", 2.7, 4.2, "①表記違い\nｶﾀｶﾅ↔英(PANASONIC)\n→同じ領収書で再申請", "health", w=3.4, h=1.3, fs=9.5)
f.box("P2", 7.0, 4.2, "②メーカー名の勘違い\n例:PlayStation=SIE\n(ソニー解除では不可)\n→ブランド名を正確に", "health", w=3.6, h=1.5, fs=9.5)
f.box("P3", 11.4, 4.2, "③カテゴリー二重ブロック\nブランド解除でも\nカテゴリ制限が残る\n→現物写真UPで解除", "health", w=3.8, h=1.5, fs=9.5)
f.box("DONE", 7.0, 1.8, "→ 出品可能（STEP3 利益計算 / 発注へ）", "start", w=6.0, h=0.85, fs=11)

f.box("TRANS", 12.4, 9.6, "※トランスペアレンシー(青いT)\nが出たら→電脳せどりでは\nスルーが合理的", "dead", w=4.6, h=1.2, fs=9.5)

# arrows
f.arrow("start", "Q")
f.arrow("Q", "CAT", fa="right", tb="left", label="カテゴリー制限", color="#d6a400", lc="#b00")
f.arrow("Q", "B1", label="ブランド制限")
f.arrow("B1", "B2", label="弾かれたら")
f.arrow("B2", "B3", label="弾かれたら")
f.arrow("B1", "OK", fa="left", tb="left", label="通れば完了", color="#3a8c3a", lc="#3a8c3a", rad=-0.45)
f.arrow("B2", "OK", fa="left", tb="left", label="通れば完了", color="#3a8c3a", lc="#3a8c3a", rad=-0.35)
f.arrow("B3", "OK", label="完了")
f.arrow("CAT", "OK", fa="bottom", tb="right", color="#3a8c3a", rad=-0.3)
f.arrow("OK", "P")
f.arrow("P", "P1", fa="bottom", tb="top", color="#e67e22", rad=0.1)
f.arrow("P", "P2", fa="bottom", tb="top", color="#e67e22")
f.arrow("P", "P3", fa="bottom", tb="top", color="#e67e22", rad=-0.1)
f.arrow("P1", "DONE", fa="bottom", tb="left", color="#3a8c3a", rad=-0.1)
f.arrow("P2", "DONE", fa="bottom", tb="top", color="#3a8c3a")
f.arrow("P3", "DONE", fa="bottom", tb="right", color="#3a8c3a", rad=0.1)

f.save(os.path.join(os.path.dirname(__file__), "03_restriction-release-flow.png"))
