# -*- coding: utf-8 -*-
"""⑤ 事業準備・初期登録の詳細フロー（全体像の段階0／アカウント開設〜売れる状態づくり）"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from flow_lib import Flow

f = Flow(13.5, 19.0, (0, 17), (0, 23),
         title="⑤ 事業準備・初期登録 詳細フロー（個人・小口プラン・副業初心者を想定）")

# spine x=5.2
f.box("ST", 5.2, 22.0, "事業スタート（Amazon物販をやる！）", "start", w=5.6, h=0.9, fs=11)

f.box("A1", 5.2, 20.3, "STEP1 「5点セット」を準備\n①本人確認書類 ②決済カード ③受取用銀行口座\n④事業用メール ⑤携帯電話番号", "step", w=6.8, h=1.55, fs=10.5)

f.box("A2", 5.2, 18.1, "STEP2 出品プランを選ぶ\n・小口＝月額0円＋1点100円（初心者推奨）\n・大口＝月額4,900円（月50個以上で得）", "step", w=6.8, h=1.55, fs=10.5)

f.box("A3", 5.2, 15.9, "STEP3 Amazon出品アカウント登録\nセラーセントラルで事業者情報・口座・カードを入力", "step", w=6.8, h=1.3, fs=10.5)

f.box("A4", 5.2, 13.8, "STEP4 本人確認（KYC）\nビデオ通話 or 書類アップロードで審査", "step", w=6.4, h=1.2, fs=10.5)

f.box("G1", 5.2, 11.7, "アカウントが\n有効化された？", "gate", w=4.0, h=1.25, fs=11)

f.box("A5", 5.2, 9.6, "STEP5 セラーセントラル初期設定\n・受取口座/決済カードの最終確認\n・返品/特商法表記/通知設定", "step", w=6.6, h=1.45, fs=10.5)

f.box("A6", 5.2, 7.3, "STEP6 リサーチ環境を整える\n・ERESA PRO 等のツール導入（別チケT-027-001）\n・仕入れ先サイトの会員登録", "step", w=6.8, h=1.45, fs=10.5)

f.box("END", 5.2, 5.1, "準備完了 → フロー①「1. リサーチ」へ", "start", w=5.8, h=0.9, fs=11)

# 任意・条件分岐（事業形態に応じて並走）
f.box("OPT", 5.2, 3.2, "【並走】事業形態に応じた届出（任意だが推奨）", "info", w=7.2, h=0.85, fs=10.5)
f.box("B1", 2.4, 1.6, "青色申告したい\n→開業届＋青色申告承認申請\n（開業2ヶ月以内）", "rel", w=4.4, h=1.35, fs=9.5)
f.box("B2", 8.0, 1.6, "中古品を扱う\n→古物商許可（警察署）\n（約19,000円・40日）", "rel", w=4.4, h=1.35, fs=9.5)

# side notes
f.box("N1", 13.4, 20.3, "【本人確認書類の正解】\n・顔写真付き身分証（免許/パスポート/マイナ）\n・過去180日以内の住所確認書類\n　（クレカ明細/銀行取引明細/各種請求書）\n→社長はここの書類準備で停滞中(T-004)", "health", w=5.6, h=2.2, fs=9.3)

f.box("N2", 13.4, 18.1, "【小口↔大口の損益分岐】\n月の販売数 ≒ 50個が境目\n(4,900円 ÷ 100円 = 49個)\n→最初は小口で開始、増えたら切替", "info", w=5.4, h=1.75, fs=9.3)

f.box("N3", 13.4, 13.8, "【本人確認の落とし穴】\n・書類の住所と入力住所の不一致で差戻し\n・氏名のヘボン式/漢字ゆれ\n・暗い/反射した撮影→再提出\n→焦らず鮮明に、住所表記を完全一致で", "health", w=5.6, h=2.0, fs=9.3)

f.box("N4", 13.4, 9.6, "【受取口座のコツ】\n・屋号なしの個人口座でOK\n・ネット銀行(住信SBI/楽天)が明細取得◎\n　→確定申告がラクになる", "info", w=5.4, h=1.7, fs=9.3)

f.box("N5", 13.4, 1.6, "【古物商が要るのは】\n中古/転売目的の新品買取等。\n新品をメーカー/卸/正規店から仕入れて\n売るだけなら原則不要。判断に迷えば\nハルオ(法務)に確認を。", "rel", w=5.6, h=1.95, fs=9.3)

# arrows (spine)
for a, b in [("ST","A1"),("A1","A2"),("A2","A3"),("A3","A4"),("A4","G1")]:
    f.arrow(a, b)
f.arrow("G1","A5", label="有効化OK", lc="#2a7fb5")
f.arrow("A5","A6"); f.arrow("A6","END")
# G1 差戻しループ
f.arrow("G1","A4", fa="left", tb="left", label="差戻し\n(書類再提出)", color="#cc3333", rad=-0.5, lc="#cc3333", lx=2.0, ly=12.75)
# 並走届出
f.arrow("END","OPT", color="#16a085")
f.arrow("OPT","B1", fa="bottom", tb="top", color="#d6a400")
f.arrow("OPT","B2", fa="bottom", tb="top", color="#d6a400")

# side note links (dotted)
f.arrow("N1","A1", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("N2","A2", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("N3","A4", fa="left", tb="right", color="#e67e22", style="dotted")
f.arrow("N4","A5", fa="left", tb="right", color="#16a085", style="dotted")
f.arrow("N5","B2", fa="left", tb="right", color="#d6a400", style="dotted")

f.save(os.path.join(os.path.dirname(__file__), "05_setup-flow.png"))
