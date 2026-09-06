# SNS・モール・クラファンからの情報取得 — 判定済みの結論（2026-09-06 実査）

初出: T-20260906-006（ハルオ）。**8/31 の T-20260831-005 判定の「射程確定」として書いた。**
併読: `knowledge_platform_api_data_retention.md` / `knowledge_scraping_and_public_db_2026.md` / `knowledge_public_repo_exposure.md`

---

## 0. 一番の学び：**過去の NO を再照会されたら、まず「あの条項の名宛人は誰か」を見る**

8/31 の「YouTube/X/TikTok/Instagram すべて NO」は、決定打が
- "Do not aggregate **API Data**"
- "an **API Client** must not store ... 30 calendar days"
- "Prohibited Access"（**認証情報**を持つ者）

**3つとも API/自動アクセスを名宛人にした条項だった。**
→ **NO の射程は「自動化された手段」に限られ、人が見る行為には及ばない。**

**この確認を怠ると、自分の過去判定を過大に読んで事業の手を止める。**
逆に、射程を広げて答えるのも誤り。**「あの NO は何の条項を根拠にしたか」を毎回引き直すこと。**

---

## 1. 判定済みの結論（有効期限つき・再確認は半年）

| 対象 | 判定 | 決め手（原文の在処） |
|---|---|---|
| **人が手動閲覧してメモ**（全SNS） | **可** | 各社の禁止条項の要件がすべて「自動化された手段」。人の閲覧を禁じる条項は無い |
| **X のスクレイピング** | **不可（最強）** | robots.txt `User-agent: * / Disallow: /` ＋ ToS §Using the Services / Misuse (iii)「crawling or scraping the Services **in any form, for any purpose**」 |
| YouTube のスクレイピング | 不可 | 利用規約「許可と制限事項」自動化手段禁止（例外は robots.txt に従う公開検索エンジンのみ） |
| TikTok のスクレイピング | 不可 | ToS §5「use automated scripts to collect information from … the Services」＋ robots.txt が `/search?` `/discover/trending/detail/` を Disallow |
| Instagram のスクレイピング | 不可 | **robots.txt の冒頭コメントが規約宣言**：「Collection of data on Instagram through automated means is prohibited unless you have express written permission」＋ `User-agent: Scrapy / Disallow: /` |
| **Google トレンドの自動取得** | **不可** | `trends.google.com/robots.txt` が `Disallow: /explore?` `/trends/explore?`。Google 利用規約が robots 違反の自動アクセスを禁止 → **Google アカウント単位の制裁＝8/31 と同じ不可逆性** |
| Google トレンドを人が見る／CSV DL | 可。**ただし PUBLIC リポは不可**（再公開の許諾を確認できず） | 同上 |
| **Amazon.co.jp の自動取得** | **絶対不可** | 利用規約 nodeId=643006（2026-09-06 再取得）＋ **BSA §3(a)(c) で出品用アカウントの停止事由**。Keepa で代替済み＝そもそも不要 |
| **楽天ウェブサービス API** | **不可** | 規約 Art.10(1)**(4)「楽天アフィリエイト以外の方法で収益を得る行為」**、**(6) 競合サービス**、**(9) 不特定多数と共有できる場所への保存＝PUBLIC リポ直撃** |
| **Yahoo!ショッピング（サイトの自動取得）** | **不可** | LINEヤフー共通利用規約 **§14「当社サービスやそれらを構成するデータを、その提供目的を超えて利用することができません」＋利益相当額の請求権**。§2.1/2.2 で**非会員にも及ぶ** |
| Yahoo!ショッピング **API**（YDN） | **未確認＝着手不可**（§6 参照。サイトと同じ「不可」に丸めないこと） | `developer.yahoo.co.jp/terms/` は 404、ガイドは JS レンダリングで本文取得不能 |
| **CAMPFIRE** | **条件付き可** | 第27条（禁止行為）**全11号に自動収集の禁止が無い**（実査）。robots.txt も `/projects/` を許可。**ただし第34条3項ただし書「告知以外の目的での媒体掲載は事前承諾」→ PUBLIC リポは不可** |
| Makuake | **未確認＝着手不可** | 規約本文が **4URL とも同一スタブ 122,857 bytes**（JS レンダリング）。curl も WebFetch も本文を返さない |
| **ふるさとチョイス** | **不可** | 利用規約 **第12条1項(12)「自動化された手段（…RPAツール…）を用いた情報収集（スクレイピングおよびクローリングを含みます）」** ＋ 第11条1項 転載禁止 |
| さとふる | 未確認＝着手不可 | robots.txt が空・規約ページが curl に応答なし |
| RSS フィード経由 | **可（最も筋がよい）** | 配信者が機械可読で公開した形式。ただし**保存は事実のみ**（記事本文は著作権法21条） |

---

## 2. 新しく手に入った「原文の武器」（何度も使う）

**X ToS §Using the Services / Misuse of the Services (iii)**（Effective: April 10, 2026）
> (NOTE: **crawling or scraping the Services in any form, for any purpose without our prior written consent is expressly prohibited**)

→ **"for any purpose" と書かれた条項は、目的による例外の議論を条文自身が塞いでいる。**この形の条項を見たら即 NO。

**LINEヤフー共通利用規約 §14**
> 当社サービスやそれらを構成するデータを、**その提供目的を超えて利用することができません**。…**それらの行為によってお客様が得た利益相当額を請求する権利**を有します。

→ **「提供目的を超えて」型の条項＋利益相当額請求権**。差止だけでなく金銭請求を明文で予定している。

**楽天ウェブサービス規約 Art.10(1)(9)**
> Storing information obtained through the Web Services … **in a place that enables the sharing of information with unspecified and/or many people.**

→ **PUBLIC リポを名指ししたのと同じ条項。**`knowledge_public_repo_exposure` の一覧に追加した。

---

## 3. Zendesk Help Center API が Makuake でも通った（時短の型）

`https://mkhelp.makuake.com/api/v2/help_center/ja/articles/<id>.json` → `article.body` に全文 HTML。
検索も通る：`.../api/v2/help_center/articles/search.json?query=<urlencoded>&per_page=20`

- **WebFetch は 403、curl の HTML も SPA。だが Zendesk API は素の curl で通る。**
- gBizINFO（`help.info.gbiz.go.jp`）でも同じ手が効いた（`knowledge_scraping_and_public_db_2026` §3）。
- **ヘルプセンターが Zendesk 製なら、まずこの API を試すこと。**

---

## 4. 規約本文が読めない時の扱い（型として固定した）

**「読めない＝不可」ではなく「読めない＝着手不可（未確認）」。**
これで 8/31 のザッカネット（NO）と、6-b Amazon ドロップシッピング（未確認→着手不可）を統一的に説明できる。

| 状況 | 判定 |
|---|---|
| **会員登録して規約に同意する**必要がある × 規約本文が読めない | **NO**（白紙で法的拘束を受ける行為） |
| **非会員のまま公開ページを読むだけ** × 規約本文が読めない | **未確認＝着手不可**（読めたら再判定） |

**そして「秘書のブラウザで取ってきて」まで書く。**CLAUDE.md §4.4 によりブラウザ操作は秘書の担当。**社長に手順を渡さない。**

---

## 5. 今回も出た「そもそも要るのか」（4回目）

Amazon ランキングの自動取得は、**Keepa を契約済みで BSR が取れる**以上、判定する前に不要。
`knowledge_scraping_and_public_db_2026` §4-4 と同じ結論。**リスク判定より先に「その手段がそもそも必要か」を問う。**

---

## 6. ★依頼範囲外だが見つけた衝突（3回目）— Sato-Scope の楽天/Yahoo アダプタ

T-20260906-006 の判定中に発見。**依頼は「新しい経路の可否」だったが、既存の稼働物が同じ規約に抵触していた。**

- `workspace/output/deliverables/T-20260521-005/code/adapters/rakuten_shopping.py` / `yahoo_shopping.py`
- 用途はヘッダコメントに明記：「**仕入れ元起点 = 電脳せどりの入口**」＝ Yahoo/楽天で仕入れて Amazon で売る
- `agents/it_engineer/memory/rakuten_new_api_referer_gatekeeper.md`（2026-06-05）に「**Yahoo は実APIで稼働中**」
- **楽天ウェブサービス規約 Art.10(1)(4)「楽天アフィリエイト以外の方法で収益を得る行為」／(6)「競合サービスの提供」に真正面から当たる。**
- Yahoo API は**ガイドライン本文を取得できず、判定保留**（共通利用規約が API に及ぶか、API 固有ガイドラインが商用を許諾しているかが未確認）。**「共通規約 §14 が来るから黒」と即断しないこと。**

**教訓（Keepa・NETSEA に続く3回目）**
> **法務レビューは、依頼された「これから作るもの」だけを見て終わらせない。**
> **同じ規約の下で既に動いているものが無いかを、必ず `grep` で確認する。**新機能が白でも既存運用が黒、という構図が繰り返し出る。

**確認の手順（次回そのまま使う）**
```
grep -rli "<サービス名>" --include=*.py --include=*.md --include=*.json scripts/ agents/ workspace/output/deliverables/
find . -name "*<サービス名>*" | grep -v node_modules
```
IT エンジニアの `memory/` は**稼働状況の一次情報**になる（「稼働中」と書いてある）。**必ず読むこと。**

**そして停止・削除は自分でやらない。** スケジュール解除もファイル削除も §4.1。**A/B/C と推奨まで作って秘書に返す。**
