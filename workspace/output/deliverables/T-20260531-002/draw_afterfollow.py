# -*- coding: utf-8 -*-
"""⑫ アフターフォロー詳細フロー（並走・イベント駆動／顧客対応とアカウントヘルス維持）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(14.5, 18.5, (0, 18), (0, 22),
         title="⑫ アフターフォロー 詳細フロー（販売後ずっと並走・アカウントヘルスを守る）")

# トリガ（最上段）
f.box("TRIG", 6.0, 21.0, "販売後イベントが発生（販売〜入金と並走で起き続ける）", "after", w=8.4, h=0.9, fs=11)

# 4分岐の見出し
f.box("E1", 2.3, 19.0, "①購入者から\nメッセージ/問合せ", "after", w=3.6, h=1.05, fs=10)
f.box("E2", 6.0, 19.0, "②返品・返金\nリクエスト", "after", w=3.6, h=1.05, fs=10)
f.box("E3", 9.7, 19.0, "③評価・レビューが\n付いた", "after", w=3.6, h=1.05, fs=10)
f.box("E4", 13.2, 19.0, "④A-to-Z/真贋・\n知財クレーム", "gate", w=3.6, h=1.05, fs=10)

# ①メッセージ
f.box("C1", 2.3, 16.7, "24時間以内に返信\n（FBAでも商品Q&Aは自分で）", "step", w=3.8, h=1.15, fs=9.5)
f.box("C1b", 2.3, 14.6, "定型文を用意し丁寧・迅速に\n→無対応は評価悪化の主因", "step", w=3.8, h=1.15, fs=9.5)

# ②返品・返金
f.box("C2", 6.0, 16.7, "FBA=Amazonが自動処理\n自己発送=自分で返金対応", "step", w=3.8, h=1.15, fs=9.5)
f.box("C2b", 6.0, 14.6, "返送品を検品\n→再販可/不可を判定", "step", w=3.8, h=1.15, fs=9.5)
f.box("C2c", 6.0, 12.4, "再販可→在庫へ戻す\n不可→返品在庫の処分/返送", "step", w=3.8, h=1.15, fs=9.5)

# ③評価・レビュー
f.box("C3", 9.7, 16.7, "評価(セラー)とレビュー(商品)\nは別物。まず種類を見分ける", "step", w=3.8, h=1.2, fs=9.5)
f.box("C3b", 9.7, 14.6, "セラー評価で誤り/規約違反\n→削除依頼が可能", "step", w=3.8, h=1.15, fs=9.5)
f.box("C3c", 9.7, 12.4, "商品レビューは原則削除不可\n→改善材料として活用", "step", w=3.8, h=1.15, fs=9.5)

# ④クレーム
f.box("C4", 13.2, 16.7, "即時対応（放置厳禁）\n証憑（請求書/追跡)を準備", "gate", w=3.8, h=1.2, fs=9.5)
f.box("C4b", 13.2, 14.6, "真贋=正規仕入の請求書を提出\nA-to-Z=配送/対応の記録を提出", "gate", w=3.8, h=1.25, fs=9.5)

# 合流 → アカウントヘルス
f.box("AH", 6.0, 9.8, "すべての対応結果が\n【アカウントヘルス】に反映される", "health", w=7.0, h=1.2, fs=11)

f.box("M1", 2.3, 7.6, "注文不良率 ODR < 1%\n（生命線の指標）", "health", w=3.8, h=1.05, fs=9.5)
f.box("M2", 6.0, 7.6, "出荷遅延率/キャンセル率\nを基準内に保つ", "health", w=3.8, h=1.05, fs=9.5)
f.box("M3", 9.7, 7.6, "ポリシー違反\n(真贋/知財)の有無", "health", w=3.8, h=1.05, fs=9.5)

f.box("G", 6.0, 5.4, "健全？", "gate", w=2.8, h=1.0, fs=11)
f.box("OK", 2.6, 3.6, "良好を維持\n→学びをフロー①「11.振り返り」へ", "start", w=4.6, h=1.1, fs=9.5)
f.box("NG", 9.6, 3.6, "悪化・警告\n→改善計画(POA)を提出\n→最悪アカウント停止=事業停止", "gate", w=4.8, h=1.25, fs=9.5)

# side notes
f.box("N1", 13.7, 9.8, "【FBAと自己発送の差】\n・FBA=返品/カスタマー対応をAmazon代行\n・自己発送=すべて自前\n→初心者はFBAで運用負荷を下げる", "info", w=5.2, h=1.85, fs=9.2)
f.box("N2", 13.7, 5.4, "【真贋クレームは最重要】\n・即アカウント停止リスク\n・正規ルート仕入れの請求書を即提出\n→だから領収書/請求書の保管が命綱", "health", w=5.2, h=1.95, fs=9.2)

# arrows: trigger -> 4 events
f.arrow("TRIG","E1", fa="bottom", tb="top", color="#8e44ad")
f.arrow("TRIG","E2", fa="bottom", tb="top", color="#8e44ad")
f.arrow("TRIG","E3", fa="bottom", tb="top", color="#8e44ad")
f.arrow("TRIG","E4", fa="bottom", tb="top", color="#cc3333")
# each lane
f.arrow("E1","C1"); f.arrow("C1","C1b")
f.arrow("E2","C2"); f.arrow("C2","C2b"); f.arrow("C2b","C2c")
f.arrow("E3","C3"); f.arrow("C3","C3b"); f.arrow("C3b","C3c")
f.arrow("E4","C4"); f.arrow("C4","C4b")
# lanes converge to AH
f.arrow("C1b","AH", fa="bottom", tb="left", color="#e67e22", rad=-0.15)
f.arrow("C2c","AH", fa="bottom", tb="top", color="#e67e22")
f.arrow("C3c","AH", fa="bottom", tb="right", color="#e67e22", rad=0.15)
f.arrow("C4b","AH", fa="bottom", tb="right", color="#cc3333", rad=0.25)
# AH -> metrics -> gate
f.arrow("AH","M1", fa="bottom", tb="top", color="#e67e22", rad=0.1)
f.arrow("AH","M2", fa="bottom", tb="top", color="#e67e22")
f.arrow("AH","M3", fa="bottom", tb="top", color="#e67e22", rad=-0.1)
f.arrow("M2","G")
f.arrow("G","OK", fa="left", tb="top", label="健全", color="#3a8c3a", lc="#2a7fb5", rad=0.15)
f.arrow("G","NG", fa="right", tb="top", label="悪化", color="#cc3333", lc="#cc3333", rad=-0.15)
# side notes
f.arrow("N1","AH", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("N2","C4b", fa="top", tb="bottom", color="#cc3333", style="dotted", rad=0.2)

f.save(os.path.join(os.path.dirname(__file__), "12_afterfollow-flow.png"))
