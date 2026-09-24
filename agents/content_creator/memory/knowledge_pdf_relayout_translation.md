# 外国語の配布PDFを「同じレイアウトの日本語版」に作り直す手順

記録 2026-09-25（T-20260925-001 / Amazon Global Selling "Ready to Sell Checklist" 日本語版）。
同種の依頼（Amazon等の英語資料を社長の参照用に日本語化・同レイアウト・写真差し替え）の再利用手順。

## 0. 置き場を最初に決める（第三者著作物）

- 原本が第三者著作物なら、翻訳版も二次的著作物。**リポ（PUBLIC・30分ごと自動 push）には入れない**。
  `~/Documents/AI Company 素材/Amazon物販事業/<topic>-<YYYYMMDD>/` に PDF・README・`_src/` をまとめ、親 README の「収蔵物」に追記する。
- 作業用 HTML もリポ内の agent_output ではなく最初から素材フォルダの `_src/` に作る（訳文がリポに落ちる窓を作らない）。
- memory とチケットには訳文を貼らない。手順と判断だけを書く。

## 1. 原本を座標ごと写す（組版の型）

- `pdftoppm -r 100 -png` で原本を描くと **Letter は 850×1100px** になる。HTML をこの座標系で組み、
  `.page{width:850px;height:1100px;zoom:0.96}` で Letter（816×1056 CSS px）に合わせる。
  こうすると同じ `pdftoppm -r 100` で描いた自作版と**画素単位で横に並べて比較できる**（PIL で左右連結して1枚で見る）。
- 🔴 **`transform: scale(0.96)` は使わない。** Chrome の印刷で、背景色が変形前の 1056px で切れ、下端に白い帯が出る（写真は切れないので気づきにくい）。`zoom` なら出ない。
- PDF 化: `Google Chrome --headless --no-pdf-header-footer --print-to-pdf=... file://...`＋`@page{size:8.5in 11in;margin:0}`＋`print-color-adjust:exact`。
- Chrome はヒラギノを **Type 3** で埋め込む（pdffonts で確認済み。表示・印刷・テキスト抽出は問題なし）。pdftoppm が "Bad bounding box in Type 3 glyph" と警告するが無害。

## 2. 日本語は英語より縦に伸びる ─ 見出しを別行にしない

- 1稿で「太字の見出し語を1行＋説明を次の行」にしたら、2ページ目の5番・11番が次の帯に潜って消えた。
- 原本どおり **太字の見出し語に説明を続けて1段落に流す**（`<b>…する。</b>説明…`）と行数が減り、原本の組み方にも忠実。
- `word-break: auto-phrase`（Chrome 119以降。文節で改行）はリード文・見出しには効くが、**狭い段では右端が大きく余って行数が増える**。
  余裕のない段は `word-break: normal`、縦に余裕のある段だけ auto-phrase、と使い分けた。
- `text-align: justify` は和文の短い行で字間が間延びする → 使わない。
- 1文字だけの泣き別れ（「対応す／る」「送る。」）は、`<br>` で改行位置を指定するか、括弧内の補足を縮めて潰す。
  固有名詞（「Amazon グローバルセリング」）は `white-space:nowrap` で分割させない。
- 行頭が「は、」になる文は語順を入れ替える（主語を文頭へ）。

## 3. 写真差し替え：Unsplash の「無料に見えて有料」に注意

- 検索上位の "Getty Images" 名義の写真は **Unsplash+（有料）**。使わない。
- `unsplash.com/napi/...` は curl だと認証を求められる。**WebFetch で `unsplash.com/s/photos/<語>?license=free&orientation=landscape` を読み**、候補IDを得る。
- 画像は `curl -L https://unsplash.com/photos/<id>/download?w=480` で候補を取り、HTML に並べて Chrome headless `--screenshot` で**コンタクトシート（候補一覧の1枚絵）**にして一度に目視する。
- 採用候補は写真ページを WebFetch して "Free to use under the Unsplash License" を**1枚ずつ**確認し、撮影者・URL を README に残す。
- 選定基準（今回）：原本と同じ構図（人物が右寄り＝左に見出しの余白）／アジア系人物／**他社ブランド名の写り込みがないこと**。
  1稿のヒーロー写真は小冊子に化粧品ブランド名が大きく写り、見出しと重なったため差し替えた。
- 白抜き見出しの下地が明るい写真は、左から右へ濃→淡のグラデーション（rgba(24,30,40,.70)→.08）を重ねて読ませる。

## 4. 訳語の判断（Amazon 公式用語に寄せる）

| 原文 | 採用 | 理由 |
|---|---|---|
| Professional vs. Individual | 「大口出品」と「小口出品」 | Amazon.co.jp の公式用語 |
| Self-Fulfillment | 自己発送 | 同上 |
| Solution Provider Network | サービスプロバイダーネットワーク（SPN） | Amazon 日本の呼称 |
| pick（pick, pack, ship） | 商品の取り出し | 「ピッキング」は副業初心者には業界用語 |
| preferred payment method / payment cycles | 売上金の受け取り方法／入金のサイクル | 出品者側から見た「支払い」は受け取り。原文の曖昧さを受け手目線で解消（意訳として報告） |
| placement（4Pの一つ） | 商品の見せ方 | 文脈が出品ページ上の露出。「流通」と訳すと誤読を招く |
| Ready to get started? | さあ、始めましょう。 | 疑問形の直訳（準備はできましたか？）は販促文として不自然 |
| a great way to grow your business | ビジネスを大きく伸ばすチャンス | 「〜する素晴らしい方法」は翻訳調 |

- ロゴ（amazon global selling、Solution Provider Network のバッジ）は**商標の表記なので英語のまま**残した。

## 5. 資料の前提は README に書く（本文は変えない）

- この資料は米国 Amazon.com 向け・2017年版。「FBA輸出」は日本から使える制度ではない。
  **翻訳本文に注記を足すと原本と一致しなくなるので、README の「読むときの注意」に書いた。**
