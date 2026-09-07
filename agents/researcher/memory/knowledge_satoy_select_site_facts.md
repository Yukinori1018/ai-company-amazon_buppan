# 自社サイト satoy-select.com の実態（2026-09-04 実測 / T-20260904-005）

**販売サイトではない。ブランド／信用付けサイトである。** ここを取り違えると判断を誤る。

- 配信：Cloudflare Pages（静的）。ソースは `workspace/output/deliverables/T-20260817-006/site/`（T-20260817-006「仕入れ信用力の準備」の成果物）
- `sitemap.xml` 実測で**全8ページ**：`/` `/about` `/business` `/contact` `/guides` `/guide-cutting-board` `/guide-bottle` `/partners`
- **商品ページ0・価格表示0・カート0・決済0。** `/business` に「当サイトでは販売しておりません」と明記
- **特商法表記ページは無い**（`/tokusho` `/tokushoho` `/law` `/legal` `/company` はすべて404）。`/about` に「法定の表示事項は販売ページ（Amazon.co.jp ストア）に掲載」と明記
- `/about` の「事業者情報」に **屋号 Satoy Select／代表者 佐藤之則／所在地（大田区）／開業 2026年8月／事業内容 インターネット通信販売業／販売サイト＝Amazon.co.jp ストア／配送＝Amazon FBA** が揃う
- `/partners` は**メーカー向けの営業ページ**。「価格を崩さない」「正規品のみ」「初回10点程度の小ロット・前払い」「FBA直送可」「開業届の控えを提出可」を明文で約束している
- トップ・`/business` とも「**Amazonストア、まもなく公開します**」＝ 送客先の Amazon ストア自体が未公開

## 判断に効く含意

- 「自社サイトがあるから販売サイトとして通る」は**成り立たない**。卸プラットフォームが見るのは「販売ページ」であって会社案内ではない
- 住所が全ページのフッターに載っている＝**このリポジトリは PUBLIC なので、成果物に住所を書くときは伏せる**（今回は `〒146-00xx 東京都大田区（以下略）` とした）

## 配信まわりの実測（2026-09-07 / T-20260907-001）

Search Console の「インデックス未登録の新しい要因」通知を調べて確定した挙動。**同じ通知が再び来ても、この2つなら実害なし。**

- **`www.satoy-select.com` は 301 せず 200 で実体を返す**（apex と両方が生きている）。ただし www 側8ページの canonical はすべて apex を指すので、Google は www を「適切な canonical のある代替ページ」と判定する＝通知の要因①。消したければ Cloudflare の Redirect Rules で hostname 単位の 301 を張る（Pages の `_redirects` ではホスト分岐できない）
- **`.html` 付きURLは Cloudflare Pages が 308 で拡張子なしへ正規化**（`/about.html`→`/about`、`/index.html`→`/`）。`http://`→`https://` は 301 ＝通知の要因②。Google が `.html` を拾った出所は旧版（`site_backup_20260820/`）の canonical が `.html` 付きだった名残で、**現行版は canonical・sitemap・内部リンクとも拡張子なしに統一済み**（公開用の `href="*.html"` は0件）
- `robots.txt` は `Allow: /` ＋ sitemap 宣言あり。ブロックなし

**教訓：Search Console の通知は「エラー」ではなく「分類の報告」。慌てて直す前に curl でステータスと canonical を実測する。**
