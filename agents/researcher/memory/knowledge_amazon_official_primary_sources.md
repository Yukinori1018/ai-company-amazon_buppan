# Amazon 公式一次情報の「取れる場所／取れない場所」（2026-09-04 検証）

T-20260904-004 A-5（小口プランとカートボックス）で確定した、Amazon 公式の一次情報アクセス地図。同じ調査を繰り返さないための所在メモ。

## 取れる（非ログイン・curl で本文が返る）
| 情報 | URL | 備考 |
|---|---|---|
| 大口プランの機能一覧（**カートボックス利用資格が大口の機能だと明記**） | https://www.amazon.co.jp/b?ie=UTF8&node=8485743051 （出品形態変更のご案内） | **JPでカート×プランの一次情報はここが唯一の当たり**。WebFetch は 503 になる。`curl -A "Mozilla/5.0 ..." -H "Accept-Language: ja-JP"` なら 200 |
| 出品プラン比較・手数料 | https://sell.amazon.co.jp/pricing ＋ 公式PDF https://m.media-amazon.com/images/G/09/sell/pdf/selling-plans_JP.pdf | 比較表の**チェックマークは画像**でテキスト抽出不能。使えるのは「このプランが適しているケース」の文言のみ |
| Featured Offer（英語・条件と非資格の理由） | https://sell.amazon.com/blog/buy-box-featured-offer | 在庫切れ/価格が高すぎ低すぎ/配送の速さ。**Professional 必須の明文は現行版に無い**（脚注に料金があるだけ） |

## 取れない（ログイン必須・JS SPA。本文0件）
- `sellercentral.amazon.co.jp/gp/help/external/G200418100`（おすすめ出品の利用資格）ほか help/hub 系は全滅。`/help/hub/reference/`, `/gp/help/help.html?itemID=`, `sellercentral-japan.amazon.com` の4経路すべてで本文が返らない。
- `advertising.amazon.com/help/...` も JS で本文0件。
- → **ヘルプ本文が要る調査は、最初から「社長がログインして読む」前提でチケットに書く**。非ログインで粘るのは時間の無駄（今回30分相当）。

## 調査上の学び
1. **WebFetch が 503 でも curl + UA + Accept-Language で通ることがある**（amazon.co.jp の node ページ）。WebFetch の失敗＝情報が無い、ではない。
2. **公式の明文は「肯定形」でしか存在しないことがある。**「大口の機能である」とは書くが「小口は不可」とは書かない。報告では否定形の明文が無いことを明示する（勝手に否定形に言い換えない）。
3. **PDF の比較表はチェックマークが画像**。pdftotext では列の帰属が取れない。表を根拠にするなら画像確認が要る。
4. 社内資料 T-20260817-001 は「確定（公式・複数一致）」と書いていたが、**挙げていた出典は全部二次情報**だった。結論は正しかったが根拠付けが甘い。過去の社内資料の「確定」タグは鵜呑みにせず出典欄まで見る。
