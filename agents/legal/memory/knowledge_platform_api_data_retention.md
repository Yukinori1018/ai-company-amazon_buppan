# プラットフォーム API から取ったデータを「候補リストとして持てるか」— 判定の型

初出: T-20260831-005 Phase B（2026-08-31 ハルオ）
併読: `knowledge_thirdparty_list_reuse_3steps.md` / `knowledge_scraping_and_public_db_2026.md`

**「この API のデータを社内の候補リストに保持していいか」は、利用規約の禁止事項ではなく「データ保持条項」を見る。** そこを見ずに「禁止されていないから可」と答えると事故る。

---

## 1. 見るべき順番（禁止事項は最後）

1. **保持期間の上限条項**（"retention" / "store" / "30 days" / "delete or refresh"）
2. **集約禁止条項**（"aggregate" / "Data Aggregation"）
3. **表示先の限定条項**（"your website, systems or other media" のように**主語の修飾語**が付いていないか）
4. **再配布・開示の禁止**（→ **PUBLIC リポへの commit がここに当たる**）
5. その後に一般禁止事項

---

## 2. YouTube Data API — **判定 NO**（2026-08-31）

出典: `https://developers.google.com/youtube/terms/developer-policies`（最終更新 2026-06-24）

### 決定打①：集約そのものの禁止（III.E）

> **Data Aggregation**
> **Do not aggregate API Data** except that you may only aggregate API Data relating to YouTube channels that are **under the same content owner** as recognized by YouTube pursuant to content licensing agreement(s)…
> Do not aggregate API Data or otherwise use API Data or YouTube API Services **to gain insights into YouTube's usage, revenue, or any other aspects of YouTube's business.**

**「複数チャンネルの情報を集めて一覧にする」＝ aggregate。** 例外は同一コンテンツオーナー配下のみ。
条文の趣旨は「YouTube のビジネス洞察の防止」なので**狭く読む余地はある**が、**第1文は無条件の禁止として書かれている。グレーは NO。**

### 決定打②：非認可データの保持は30暦日（III.E.4.c/d）

> an API Client **must not store statistics retrieved as Non-Authorized Data for more than 30 days.** For example, an API Client must not store the **subscriber count** for a YouTube channel for more than 30 days without authorization from the channel owner.
> API Clients may temporarily store limited amounts of Non-Authorized Data … **not longer than 30 calendar days.** After 30 calendar days, the API Client must either **delete or refresh** the stored data.

OAuth なしで取るチャンネル名・概要欄・登録者数は**すべて Non-Authorized Data**。→ **永続的な候補リストは規約違反。**

### 決定打③：代替案も同時に潰れる（III.E Scraping）

> must not … **scrape YouTube Applications or Google Applications, or obtain scraped YouTube data or content.**

### 不可逆性の評価がこの判定を決めた

- III.D "Prohibited Access" は、認証情報の停止後に**新規 Google アカウントを作って回避すること**まで禁じている＝**アカウント単位の制裁が前提の設計**。
- 社長の Google アカウントには**成果物カタログのスプレッドシート（Drive）**が乗っている。**事業インフラ。**
- **発生確率は低いが不可逆性が高い → 行動原則1によりアラート。**

### 決め手になった「そもそも要るのか」

サトル自身が「展示会出展社2,353社の方が母数でも即時性でも上」と書いていた。
→ **上位互換の母集団が手元にあるのに、Google アカウントを賭ける合理性はゼロ。**
**リスク判定より先に「その手段がそもそも必要か」を問う**（`knowledge_scraping_and_public_db_2026` §4-4 と同じ結論の再現。2回目）。

### 残した使い方

| 行為 | 判定 |
|---|---|
| 人が画面で見て1社を個別に調べる | 可（一般利用者と同じ） |
| そこで知った社名を手がかりに自社サイト・法人番号・gBizINFO から取り直す | **可・推奨**（3段階の型の段階3） |
| API で一覧を作る／30日超保持する／PUBLIC リポに置く | **不可** |

---

## 3. 「その他の媒体」に Amazon は入るか — 修飾語で決まる

orosy 第14条2項：「**APIユーザーが運営する**ウェブサイト、システムその他の媒体に表示することができます」

→ **「APIユーザーが運営する」が3語すべてに係る。Amazon のページを運営しているのは Amazon。**
→ 「出品者だから自分の媒体」は**書かれていないことを補う読み方。採らない。**

### ただしここで止めない — **設問を立て直す**

**問うべきは「Amazon に表示してよいか」ではなく「そもそも表示する必要があるか」。**

| 出品の型 | API データを Amazon に表示するか | 判定 |
|---|---|---|
| **既存 ASIN への相乗り出品** | **しない**（置くのは自分が決めた価格・在庫・SKU だけ） | **可。条項の問題が発生しない** |
| **新規 ASIN を作る**（卸元の商品名・説明・画像を使う） | する | **不可** |

**これは横展開できる型。** 「Amazon に載せていいか」と聞かれたら、**相乗りか新規カタログ作成かで割る。** 相乗りなら大半の卸規約は無関係になる。**この一手で、NETSEA・orosy・SD の3件とも経路が生き残った。**

---

## 4. PUBLIC リポは常にここで引っかかる

以下はすべて「PUBLIC リポへの commit ＝ 違反」になる条項。**新しい API/サービスを見たら、必ずこの種の条項を探すこと。**

| サービス | 条項 | 当たる文言 |
|---|---|---|
| orosy | 第14条2項ただし書 | 「第三者に**再配布し、提供し、開示し**、又は販売してはならない」 |
| スーパーデリバリー | 第17条1項 | 「**他のサイトに複製・転用又は発信**することを禁じます」 |
| YouTube | III.E.4 | "store" の期間制限 ＋ Prohibited Actions の "redistribute" |
| kougeihin.jp | サイトポリシー | 「複製、転用、販売することはできません」＋**個人情報保護法27条**（屋号のみの個人事業主が混じる） |

**本リポは PUBLIC＋30分ごと自動 push。commit＝即公開。**
**報告の最後に必ず「これは deliverables にも agent_output にも置かない」と書くこと。** 書かないと置かれる。
