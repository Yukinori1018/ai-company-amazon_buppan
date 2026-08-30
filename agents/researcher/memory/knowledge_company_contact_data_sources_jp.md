# 日本企業の連絡先を機械的に集める手段（2026-08時点の実地調査）

初出：T-20260831-001 Phase A（822社のメーカー連絡先を埋める）
この分野は**2025〜2026年に地形が大きく変わった**ので、古い記事の記憶で答えないこと。

## 1. 結論マップ（何が生きていて何が死んだか）

| 手段 | 2026-08時点 | 一次ソース |
|---|---|---|
| 国税庁 法人番号 **全件データCSV** | **生きている・0円・申請不要**。全国CSV Unicode 254MB / 月次更新 | houjin-bangou.nta.go.jp/download/zenken/ |
| 国税庁 法人番号 Web-API | 生きている・0円。**アプリケーションIDは今はインボイス公表サイトのフォームから**（`invoice-kohyo.nta.go.jp/web-api/pre-reg/`）。添付書類・手数料不要 | 第一編PDF 4.8版 |
| gBizINFO REST API v2 | 生きている。**`company_url`（企業ホームページ）はあるが電話番号フィールドは存在しない** | `api.info.gbiz.go.jp/hojin/v3/api-docs/v2` |
| **Google Custom Search JSON API** | **新規顧客の受付終了。既存も2027-01-01期限** | developers.google.com/custom-search/v1/overview |
| **Bing Search API (Azure)** | **2025-08-11に廃止済み。** 後継はAzure AI Agentsの「Grounding with Bing Search」でSERP APIではない | Microsoft Learn lifecycle |
| **Gemini API「Grounding with Google Search」** | **Gemini 3.x で月5,000リクエスト無料**／超過$14per1,000。2.5系は1,500RPD無料・$35per1,000 | ai.google.dev/gemini-api/docs/pricing |
| Serper.dev | 2,500クエリ無料・**カード不要** | serper.dev |
| Tavily | 月1,000クレジット無料・**カード不要**／PAYG $0.008/credit | tavily.com/pricing |
| Brave Search API | **2026年2月に無料ティア廃止**。月$5クレジット→以降$5/1,000。カード必須 | brave.com/search/api/ |
| SerpApi | Free 250/月、Developer $75/月(5,000) | serpapi.com/pricing |
| GEPIR | **2024-09-30終了**。後継 Verified by GS1 | GS1 Japan |
| GS1 Japan 事業者コード情報確認サービス | **自社がGS1事業者コードの貸与を受けていないと使えない**。1日50回 | gs1jp.org |
| 特許庁 国内特許情報取得API | 生きている・0円。**新規受付停止は OPD-API のみ**（誤読注意） | jpo.go.jp api-provision.html |

## 2. 一次情報の取り方のコツ（今回効いた）

- **SPAで本文が取れないサイトは、裏のAPI/仕様JSONを探す。**
  gBizINFO は `/hojin/APIManual` が500を返し続けたが、`content.info.gbiz.go.jp/api/index.html` → Swagger UI のリンク → **`https://api.info.gbiz.go.jp/hojin/v3/api-docs/v2` で公式OpenAPI JSONが素で取れた**。フィールド定義・検索パラメータ・上限（page1-10 × limit最大5000）まで確定できる。**「公式ページが読めない＝未確認」で諦める前に api-docs / openapi.json / swagger-config を叩く。**
- **官公庁の仕様は PDF に全部書いてある。** `curl` + `pdftotext -layout` で grep する。国税庁は第一編〜第六編に分かれていて、リクエストパラメータの定義は**第二編（概要編）**にある（バージョン別の第三〜六編には「第二編を見よ」としか書いていない）。
- WebFetch が403/500でも `curl -A "Mozilla/5.0"` なら通ることがある。逆に Cloudflare (help.info.gbiz.go.jp) と gs1.org はどちらでも通らなかった → **素直に「未確認」と書く**。

## 3. ブランド名しか無い状態から法人を特定する

### 効かないもの
- **国税庁もgBizINFOも「商号」検索なので、英字ブランド名（`Gudluky`『htrahy`）には原理的に効かない。** ここを最初に切り分けないと、全体平均のカバー率という無意味な数字が出る。

### 効くもの（0円・すでに手元にあるデータで作れる判別信号）
| 信号 | 意味 | 取得元 |
|---|---|---|
| **EAN先頭 45/49** | GS1 Japan が採番＝日本の事業者が登録している | Keepa `eanList` |
| **Keepa `manufacturer` に日本語** | Amazon上の製造元表記が日本語（`ダンロップ(DUNLOP)`『角川書店`） | Keepa（**単独で25社を追加。見落としやすい**） |
| `.jp`/`.co.jp` ドメインが生きている | 日本向けサイト | HTTP実測 |
| サイトタイトルに日本語 | 日本語で商売している | HTTP実測 |

822社の実測：英字526社中 **145社（27.6%）にいずれかの信号／381社（72.4%）はゼロ**。
**偽陰性あり**：`Anker` は米国UPC＋英語サイトでゼロ判定になるが、アンカー・ジャパン株式会社は実在。**足切りではなく優先順位づけに使う。**

### ドメイン推測の実測歩留まり（英字ブランド N=517）
`<brand>.com` → `.jp` → `.co.jp` を DNS→GET：
生存サイト到達 **321（62.1%）** → ページ内にブランド名が出現 **237（45.8%）** → うち `.jp/.co.jp` 23・日本語タイトル40・パーキング疑い34。
**「公式HPは半分近く0円で取れるが、日本語窓口はほぼ無い」** が結論。

## 4. 社長のフィードバックへの効き方

「仕入れ値・送料・経費が推定で不正確＝最大のボトルネック」（feedback_research_accuracy_blocker）。
今回はこれをカバー率に適用した：**カバー率を推測で書かず、HTTPを実際に517回叩いて歩留まりを測った。** 表の中で「事実（実測）」列と「見込み（推測）」列を物理的に分けたところ、上流（タカシ／ハルオ）から即座に噛み合った反応が返ってきた。**カバー率・歩留まりの類は、サンプルでいいから必ず実測を1本入れる。**

## 5. 次に同種の依頼が来たときの手順（ルーチン化）

1. 入力CSVを**自分で読んで分布を数える**（名前の型／識別子の有無／規模）。一般論を書く前に必ず
2. 「どの部分集合にどのソースが効くか」で**レーンを分ける**。全体平均のカバー率は判断材料にならない
3. 公的DB（0円・申請不要）→ 公的API（0円・申請要）→ 無料枠のある商用API → 有料 の順に並べる
4. **歩留まりは1本だけ実測する**（サンプルでよい）。残りは推測と明記
5. §4.1該当（規約同意・カード登録）を**表で分離**して、社長の手が要る件数を数える
6. 「取れないもの」は取れないと書く。空欄の理由コードを設計して渡す
