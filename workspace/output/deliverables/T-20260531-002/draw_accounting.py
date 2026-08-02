# -*- coding: utf-8 -*-
"""⑩ 入金・会計の詳細フロー（全体像の段階10／売上回収→利益確定→記帳→申告）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(13.5, 19.0, (0, 17), (0, 23),
         title="⑩ 入金・会計 詳細フロー（売上回収 → 利益確定 → 記帳 → 確定申告）")

# spine x=5.2
f.box("ST", 5.2, 22.0, "商品が売れた（注文確定）", "start", w=5.0, h=0.85, fs=11)

f.box("A1", 5.2, 20.4, "STEP1 Amazonが代金を回収\n売上はいったん「売上金（残高）」にプール", "step", w=6.6, h=1.2, fs=10.5)

f.box("A2", 5.2, 18.4, "STEP2 各種手数料が自動控除\n販売手数料(8〜15%)＋FBA配送手数料\n＋(あれば)保管料・返金関連", "step", w=6.6, h=1.5, fs=10.5)

f.box("A3", 5.2, 16.3, "STEP3 清算サイクルで売上金が確定\n原則14日ごとに集計（リザーブ＝引当金を除く）", "step", w=6.8, h=1.3, fs=10.5)

f.box("G1", 5.2, 14.1, "登録口座へ\n自動振込", "gate", w=3.8, h=1.15, fs=11)

f.box("A4", 5.2, 12.0, "STEP4 レポートを取得\n・ペイメント(取引明細)／サマリー\n・月次でCSVダウンロードして保管", "step", w=6.6, h=1.45, fs=10.5)

f.box("A5", 5.2, 9.8, "STEP5 記帳（仕訳）\n売上・仕入・手数料・送料・返金を月次で計上\n→会計ソフトでAmazon連携自動取込が楽", "step", w=6.8, h=1.55, fs=10.5)

f.box("A6", 5.2, 7.6, "STEP6 月次の採算チェック\n・利益率20%以上か（KPI）\n・キャッシュフロー（仕入→入金のズレ）", "step", w=6.6, h=1.45, fs=10.5)

f.box("END", 5.2, 5.5, "→ フロー①「11. 振り返り」へ", "start", w=5.2, h=0.85, fs=11)

# 年次（並走）
f.box("Y0", 5.2, 3.6, "【年次】確定申告の準備（毎年1/1〜3/15）", "info", w=7.2, h=0.85, fs=10.5)
f.box("Y1", 2.4, 1.9, "棚卸し（12/31在庫）\n→売れ残りは経費にならず\n　翌期の売上原価へ繰越", "rel", w=4.4, h=1.4, fs=9.5)
f.box("Y2", 8.0, 1.9, "青色申告で提出\n→領収書・帳簿7年保管\n　65万円控除を取りに行く", "rel", w=4.4, h=1.4, fs=9.5)

# side notes
f.box("N1", 13.4, 18.4, "【手数料の正体】\n・販売手数料＝カテゴリ別8〜15%\n・FBA手数料＝サイズ重量で変動\n・在庫保管料＝月割（180日超で長期料）\n→「真の利益」は手数料控除後で見る", "health", w=5.6, h=2.15, fs=9.3)

f.box("N2", 13.4, 16.3, "【リザーブ(売上金保留)】\n・新規アカウントは7〜14日保留\n・A-to-Z/チャージバックで増額も\n→入金が遅れる前提で資金繰りを組む", "health", w=5.6, h=1.85, fs=9.3)

f.box("N3", 13.4, 12.0, "【入金サイクルのコツ】\n・原則14日ごと自動振込\n・ネット銀行(住信SBI/楽天)で明細◎\n・振込手数料・最低振込額に注意", "info", w=5.4, h=1.75, fs=9.3)

f.box("N4", 13.4, 9.8, "【記帳をラクにする】\n・freee / マネーフォワード等で\n　Amazon取引を自動取込\n・仕入領収書PDFは月フォルダで保管\n→確定申告が一気に軽くなる", "info", w=5.6, h=1.95, fs=9.3)

f.box("N5", 13.4, 3.6, "【消費税の分かれ目】\n・売上1,000万円超→2年後に課税事業者\n・インボイス登録は取引先要件で判断\n→迷えばハジメ(経理)/ハルオ(法務)に確認", "rel", w=5.6, h=1.9, fs=9.3)

# arrows (spine)
for a, b in [("ST","A1"),("A1","A2"),("A2","A3"),("A3","G1")]:
    f.arrow(a, b)
f.arrow("G1","A4", label="振込完了", lc="#2a7fb5")
for a, b in [("A4","A5"),("A5","A6"),("A6","END")]:
    f.arrow(a, b)
# 年次並走
f.arrow("END","Y0", color="#16a085")
f.arrow("Y0","Y1", color="#d6a400")
f.arrow("Y0","Y2", color="#d6a400")

# side note links (dotted)
f.arrow("N1","A2", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("N2","A3", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("N3","A4", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("N4","A5", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("N5","Y0", fa="left", tb="right", color="#d6a400", style="dotted")

f.save(os.path.join(os.path.dirname(__file__), "10_accounting-flow.png"))
