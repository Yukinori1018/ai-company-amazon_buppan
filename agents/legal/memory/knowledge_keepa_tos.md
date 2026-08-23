# Keepa の規約体系（一次情報／2026-08-24 ハルオ確認）

T-20260824-001（Keepa 公式 MCP サーバの導入可否レビュー）で確定させた。
**Keepa の規約を聞かれたら、まずこのファイルを読むこと。毎回ゼロから探す必要はない。**

## 1. 契約文書は3本ある。どれが当社に適用されるかを最初に決めろ

| # | 文書 | 版（確認時点） | 適用対象 | 実URL |
|---|---|---|---|---|
| C | サイト Terms of Service | 版表示なし | keepa.com の**無料**ウェブサイト | `https://keepa.com/#!disclaimer` |
| B | Subscriptions T&C | **2026-08-22 版** | Keepa Pro（€29/月）＝ウェブサイト側の有料機能 | `https://keepa.com/cdn/termsSubscriptions.txt` |
| **A** | **Price Data API T&C（Data as a Service）** | **2026-07-28 版** | **Keepa API（当社が €49/月で契約）** | `https://keepa.com/cdn/termsAPI.txt` |

**当社に適用されるのは A。** MCP（`https://keepa.com/mcp`）も API アクセスキー認証なので A。

### ★ 取得方法のノウハウ（次回これで15分短縮できる）
- keepa.com は SPA（`#!` フラグメント）＋ Cloudflare Turnstile。**WebFetch も curl も本文が取れない。**
- **T&C の実体は `https://keepa.com/cdn/termsAPI.txt` と `termsSubscriptions.txt` に平文で置かれている**（keepa.js が契約画面で読み込む）。認証不要の単純 GET で取れる。
- サイト ToS／FAQ／UI ラベルの原文は **`https://keepa.com/cdn/languages/en.json`（および `ja.json`）** にキー `_165`〜等で入っている。`keepa.js` 内の `generateDisclaimer()` がどのキーを使うかを示す。
  - 免責ページ: `_26`(見出し) `_165/_166`(ToS) `_168/_169`(Privacy) `_792/_794`(商標) `_793/_150`(アフィリエイト) `_170`(会社情報)
  - 1シートFAQ: `_891`（設問）/ `_907`（回答）
- **注意**：curl 取得は文言上「サイトの自動化利用」に触れうる。今後は §4.4 に従いカズヨのブラウザで取るのが安全。今回は必要最小限として実施し、レビュー本文に自己申告した。

## 2. 覚えておくべき条項（当社の実務に効くものだけ）

### API T&C（A）
- **§2(2)** 自社の**業務目的**に限る。第三者目的への再販は**事前書面同意**が必要。
- **§2(4)** 完全性・正確性は保証しない。**「ユーザーが妥当性チェックをする義務」が明文である**。→ discrepancies の是正は契約上の自己責任範囲。
- **§3(4)** API は**事業者専用**。
- **§4(1)(2)** 認証情報の秘匿義務。**「authorized users（許可ユーザー）」の存在を前提にしている**（＝1シート条項が無い）。
- **§6.1(1)** データの再販は厳禁。
- **§11(1)** modify / edit / **translate** / reproduce 禁止。← **当社の日本語用語集・公開リポジトリに直撃する条項。**
- **§11(2)** **保存・印刷して自社業務目的で使う権利を明文で付与**（non-exclusive, unlimited）。CSV/スプレッドシート保存の根拠はここ。
- **§14(1)** 広範な免責・補償義務（キー漏洩による第三者利用も含む）。
- **§19** T&C 改定は **6週間前に text form で通知。異議を出さず使い続けると黙示承諾。** → 通知メールを見落とすと自動で不利になる。
- **§20** ドイツ法・Keepa 所在地の専属管轄。

### Subscriptions T&C（B）— Pro 契約に適用
- **§4(3)** *"intended for use by a single individual and is strictly non-transferable... not to share, distribute, or allow access to their subscription or the services... to any other person or entity."* ← **1シート制の本体はここ。API T&C には無い。**
- **§4(8)** スクレイパー・クローラー等でサービスから情報を抜くことを禁止（＝**ウェブサイト側**の話。API には及ばない）。
- **§11(1)** publishing / disseminating も明示的に禁止。

### サイト ToS（C）
- *"This website provides a **free** service... Any automated use of our service... is strictly forbidden."*
- **自ら「free service」と射程を宣言している**ので、有料 API には及ばない。ドイツ法 BGB §305c(2)（多義性は使用者不利）と、Keepa 自身が MCP を公式提供している事実（矛盾行為の禁止）で補強できる。

### FAQ・UI 由来
- FAQ `_907`: *"Subscriptions are per seat. Sharing within organizations or households is not permitted."*
- Pro プラン購入カード: **"Note: One seat per plan."** ＋ *"API access (1 token/min) — higher rates require a separate API plan"*
  → **Pro にもオマケの極小 API が付く**。だから「API を使っている＝API T&C 適用」とは限らない。**契約の実物確認が必要。**
- グラフ共有リンク `_297`: *"for personal use only"* → 台帳・資料・HP への埋め込みは不可。
- Graph Image API doc: 画像を直接埋め込むと **URL に API キーが載って公開される**。二重に不可。
- Privacy Policy `_169`: **Keepa ブラウザ拡張は Amazon ページの商品情報を Keepa サーバへ送信している**（設定で無効化可）。→ Amazon 側規約とのグレー。セラーセントラル用ブラウザプロファイルと分離すれば消える。

## 3. 判断の型（同種の依頼が来たら）

1. **どの契約書が当たるかを先に確定させる。**（Keepa は3本ある。SaaS 一般でも「サイト規約／有料サブスク規約／API規約」が別なのはよくある）
2. 禁止条項を1本ずつ当てはめて潰す。「許可条文があるか」ではなく「**禁止条項に当たらないか**」で見る。名指しの許可は普通どこにも書いていない。
3. **提供者自身が公式にその使い方を提供しているか**を確認する。提供していれば、字面の禁止条項があっても矛盾行為の禁止で対抗できる。
4. **本当のリスクは「新機能」ではなく「既存運用」にあることが多い。** 今回も MCP は白で、既に走っている公開リポジトリ commit が黒だった。**依頼された範囲だけ見て終わらせない。**
