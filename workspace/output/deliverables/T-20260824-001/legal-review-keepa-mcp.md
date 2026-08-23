# 法務レビュー：Keepa 公式 MCP サーバ導入と、当社の Keepa データ運用

- チケット: T-20260824-001（原務はリサーチャー／本レビューは法務ハルオが並行実施）
- 作成: 2026-08-24 ／ 法務 ハルオ
- 対象: `https://keepa.com/mcp`（Keepa 公式ホステッド MCP サーバ）＋ **当社の既存 Keepa データ保存・共有運用**
- 依頼元: 秘書カズヨ（CLAUDE.md §5 外部サービス導入前の法務チェック）
- 本レビューで**契約への同意・アカウント作成・課金は一切行っていない**（CLAUDE.md §4.1 遵守）。閲覧と評価のみ。

---

## 0. 結論（先に読むところ）

| 論点 | 判定 | 一行理由 |
|---|---|---|
| ① MCP 経由での Keepa 利用 | **条件付き GO**（条件6件・§8） | API 契約は Keepa 自身が MCP を公式提供しており、API T&C 上の禁止事項に当たらない |
| ② 取得データの CSV / スプレッドシート保存 | **GO（社内利用に限る）** | API T&C §11(2) が「保存して自社業務目的で使う権利」を明文で付与している |
| ③ 1シート制 vs AI 会社構成 | **GO（グレーではない）** | 1シート条項は**サブスクリプション（Pro）T&C**の条項で、**API T&C には存在しない**。かつ AI は「person or entity」ではない |
| ④ API キーの Notion 保管 | **NO（明確に不可）** | Keepa 公式が「共有される場所に置くな」と明記。加えて CLAUDE.md §4.1「機密情報の外部送信」に該当 |
| ⑤ Amazon 側規約との関係（Keepa データ利用） | **直接の抵触は条文上確認できず**（BSA 全文未取得＝**未確認**） | 当社は Amazon システムを叩いていない。Keepa との契約でデータを買っている |
| ⑤’ Amazon **Agent Policy**（2026-03-04 施行） | **⚠ 別件で最優先の要確認** | Keepa MCP より重大。当社の「秘書がブラウザでセラーセントラルを操作する」運用（CLAUDE.md §4.4）に直撃しうる |
| ⑥ **既存運用の是正が必要な点** | **⚠ 是正要（§5）** | Keepa 由来データ約 12,000 行が **PUBLIC な GitHub リポジトリ**に commit 済み。API T&C §11(1) の「reproduce / disseminate 禁止」に触れうる |

> **一言で。** MCP そのものは問題ありません。問題は「MCP の周りにある当社の癖」— 公開リポジトリへの生データ commit と、キーを SaaS に置きたいという発想の2つです。ここを直さずに MCP を足すと、リスクだけが増えます。

---

## 1. 最初に確定させたこと — 「どの契約書が適用されるか」

ここを間違えると全部の答えが変わります。**Keepa には性格の違う契約文書が3本**あり、当社に適用されるのは3本目です。

| # | 文書 | 版 | 適用対象 | 取得元（確認日 2026-08-24） |
|---|---|---|---|---|
| C | サイト利用規約（Terms of Service） | 版表示なし | keepa.com の**無料**ウェブサイト | `https://keepa.com/#!disclaimer` |
| B | **Subscriptions T&C** | **Version of August 22, 2026** | **Keepa Pro（有料・€29/月）＝ウェブサイト側の有料機能** | `https://keepa.com/cdn/termsSubscriptions.txt` |
| **A** | **Price Data API T&C（Data as a Service）** | **Version of July 28, 2026** | **Keepa API（当社が €49/月で契約している側）** | `https://keepa.com/cdn/termsAPI.txt` |

**当社に適用されるのは A（API T&C）です。** 根拠：

1. 当社の運用は `scan_v13.py` 等がアクセスキーで `api.keepa.com` を叩く形態で、社内資料上も契約は「Keepa API Power-User Plan €49/月」（`workspace/output/deliverables/T-20260521-005/03_research-and-strategy.md` ほか）。
2. MCP 公式ドキュメントは *"You need an active Keepa API subscription; your access key is shown on the API page of your Keepa account."* と明記。MCP は **API 契約の上に乗るチャネル**であり、Pro（ウェブサイト）契約の機能ではない。

> ⚠ **ただし1点だけ事実確認が要ります（§9-①）。** Keepa Pro プランの機能一覧には *"API access (1 token/min) — higher rates require a separate API plan"* とあり、**Pro だけでも極小レートの API が付いてきます**。当社が「Pro のおまけ API」で回しているのか「独立した API プラン」なのかで、適用契約が B か A かに割れます。社内資料は A（独立 API プラン €49）を示していますが、**請求ダッシュボードでの実物確認が未了**です。分岐の実害は §4（1シート制）に集中します。

### C（サイト ToS）の自動アクセス禁止は API には及ばない

サイト ToS には次の一文があり、これを字面だけで読むと「AI による自動アクセスは全部アウト」に見えます。

> *"This website provides a free service and, as such, we provide no warranty or guarantee of service or uptime. **Any automated use of our service - including the use of bots, scripts, scrapers, crawlers, or similar tools - is strictly forbidden.** Persons found to be using automation will be immediately and permanently banned."*（Terms of Service、keepa.com `#!disclaimer`）

**及ばないと判断します。根拠は3つ。**

1. **文言上の射程**：同条は自ら *"This website provides a **free** service"* と適用対象を宣言している。有料 API は「free service」ではなく、別途 A の契約書が用意されている（＝特別法優先の関係）。
2. **提供者自身の行為**：Keepa は自ら MCP サーバを公式に運用し、Claude Code 用のセットアップコマンドまで公開している（`api-docs/mcp.html`）。自ら提供したチャネルの利用を「禁止された自動化」と主張するのは矛盾行為（venire contra factum proprium）であり、本件準拠法であるドイツ法（API T&C §20(1)）でも許されない。
3. **不明確条項の解釈**：仮に文言が両義的でも、約款の多義性は使用者（Keepa）の不利に解釈される（BGB §305c(2)）。

同様に、Subscriptions T&C §4(8) の *"...the use of third-party autonomous software programs, such as screen and database scraping tools, spiders, robots, crawlers..."* 禁止も、**「the services（＝ウェブサイト）から情報を抜く行為」**を対象としており、API には及びません。

**残存リスク（低）**：`https://keepa.com/mcp` は物理的には keepa.com ドメイン上です。極端に字面主義の担当者が C を持ち出す可能性はゼロではありません。ただし発生確率は低く、影響は「警告 → 是正」で可逆です。**アラートは上げますが、導入の障害にはしません。**

---

## 2. 論点① MCP 経由の利用は許諾範囲か

### 2-1. 結論：許諾範囲内（条件付き GO）

API T&C には**「MCP」「AI」「エージェント」という語は一つも出てきません**（＝条文上は無記載）。したがって「MCP を名指しで許可した条文」は存在しません。**許諾の根拠は、禁止事項のいずれにも当たらないこと＋提供者自身が公式チャネルとして運用していること**の2点です。

該当しうる禁止条項を1本ずつ潰します。

| API T&C 条項 | 原文（抜粋） | MCP 利用への当てはめ |
|---|---|---|
| §2(2) 目的外利用 | *"The services are provided solely for the user's own business purposes. Reselling data for third-party purposes is only allowed with the Service Provider's prior written consent"* | ○ 当社の仕入れ判断は「own business purposes」そのもの。**再販しない限り** OK |
| §3(4) 事業者限定 | *"The Service Provider's Price Data API is available solely for business purposes."* | ○ 当社は Amazon 物販事業。個人趣味利用ではない |
| §4(2) アクセス主体 | *"the user must ensure that the Service Provider's service is accessed and used exclusively by the user or authorized users with their own registration data"* | ○ 社長本人の環境で動く。詳細は §4 |
| §6.1(1) 再販禁止 | *"Resale of the data obtained from 'Keepa.com' is strictly prohibited"* | ○ 当社は売らない。**将来ツール外販に転じる場合は要再審査** |
| §11(1) 利用権の範囲 | *"The user is not permitted to **modify, edit, translate, or reproduce** any content from the Service Provider's website without express permission"* | ⚠ §3・§5 で扱う。**「translate」に注意** |
| §14(1) 免責・補償 | ユーザーがサービス利用・規約違反・第三者権利侵害等で生じた請求から Keepa を免責・補償 | ⚠ 当社が Keepa データを外に出して揉めた場合、**当社が Keepa を守る義務を負う**。§5 の是正理由の一つ |

### 2-2. MCP 固有で押さえるべき事実（`api-docs/mcp.html`、確認日 2026-08-24）

- *"Tool calls consume the same tokens as direct API requests."* → **新規課金は発生しない。CLAUDE.md §4.1「金銭が動く」には非該当。** ここは秘書の整理どおりで正しいです。
- ただし **トークンは前払い済みの有限資源**です。*"Every tool description states its token cost and every response carries your current balance"* とあり自己抑制はしますが、**AI が探索的にツールを連打すると月の枠を溶かせます**。これは「契約違反」ではなく「経費の空費」ですが、統制は要ります（§8-条件④）。
- **書き込み系ツールが含まれます**。*"...and manage price trackings with notifications."* → AI がトラッキングを**作成・削除**できる。削除は不可逆です。CLAUDE.md §4.1「不可逆な削除」の趣旨に照らし、**読み取り専用で運用すべき**（§8-条件⑤）。
- OAuth 非対応：*"Clients that authenticate remote servers exclusively via OAuth cannot connect yet — this affects claude.ai custom connectors."* → **Bearer トークン直書きしか手段がない**。これが §5（キー管理）を厳しくする理由です。

### 2-3. 「AI に読ませる」動機との整合（付随所見）

導入動機は「AI が Keepa 用語を履き違える」対策でした。この目的自体は、API T&C §2(4) が課す義務と**同じ方向**を向いています。

> *"The Service Provider does not guarantee the completeness of the provided data. Additionally, the accuracy of all data cannot be ensured. **Users must perform a plausibility check on the data obtained from Keepa.com.**"*（API T&C §2(4)）

**「妥当性チェックはユーザーの義務」と契約書に書いてある**以上、`discrepancies.md` で検出された誤読4件を放置することは、単なる社内品質問題ではなく**契約上の自己責任範囲**の話です。MCP 導入は義務履行を助ける方向であり、法務としては積極的に支持します。

---

## 3. 論点② 取得データの保存・再利用・第三者提供／当社の既存運用

### 3-1. 保存は明文で OK

> *"(2) The user **may save or print out contents** from the Service Provider's website **for their own business purposes**, with a **non-exclusive and unlimited right of use**, unless payment is not made, in which case the granted rights may be revoked by the Service Provider."*（API T&C §11(2)）

**当社の CSV / Google スプレッドシート保存は、この条項で明確に許諾されています。**「問題ありません」と言い切れる数少ない論点です。付随して2点。

- *"unlimited right of use"* は**期間無制限**の意味です。§11(1) の「利用権は契約期間に限る」との関係で読むと、**契約中に保存したものは解約後も使ってよい**と読めます（＝解約時に台帳を消す必要はない）。ただしこれは条文の文理解釈であり、**Keepa の公式見解を取ったものではありません**（§9-③）。
- *"unless payment is not made"* — **支払い不履行で遡って利用権が失われます**。カード失効は法務イベントでもあると認識してください。

### 3-2. 第三者提供・再販は原則 NG

- §2(2)「third-party purposes への再販は事前**書面**同意が必要」／§6.1(1)「再販は厳禁」。
- 当社が将来 Sato-Scope 的なツールを外販する、あるいは Keepa 由来の数値を含むリストを他のセラーに販売・配布する場合、**その瞬間に契約違反**です。「無償配布なら再販ではない」という理屈は §11(1) の *disseminate/reproduce* 禁止（Subscriptions T&C §11(1) はさらに明示的）で塞がれます。

### 3-3. ⚠ 「translate」条項 — 当社の成果物に直撃します

> *"The user is not permitted to modify, edit, **translate**, or reproduce any content from the Service Provider's website without express permission"*（API T&C §11(1)）

本チケットの成果物 `keepa-glossary.md` は、**Keepa 公式 API ドキュメントの定義文を日本語に翻訳した文書**です。文言を素直に読むと §11(1) に当たります。

- **社内限りで使う限り、実害リスクはほぼゼロ**（発生確率：極低／影響：小／可逆性：高）。実務上ここを咎める事業者はいません。
- **ただし公開した瞬間に性質が変わります。** 具体的には (a) PUBLIC な GitHub リポジトリへの commit、(b) Satoy Select ホームページへの掲載、(c) note / SNS での発信。**(a) は既に起きています**（§5）。
- **対処は簡単です**：引用は「必要最小限の原文＋出典＋自社の解説が主」の形（著作権法32条1項の引用要件）に留め、**全訳の対訳表を公開しない**。社内版は現状のままで構いません。

### 3-4. Keepa グラフ画像の埋め込みは二重に NG

- グラフ共有リンクの UI 文言：*"Copy this link to display the chart - **for personal use only**."*（keepa.com 言語リソース `_297`）
- Graph Image API ドキュメント：*"**Important:** Make sure you do not embed the images directly, as this will make your **API key publicly accessible** and open to misuse. Always put the Graph Image requests behind a proxy to secure your API key."*

**規約上（personal use only）にも、セキュリティ上（URL にキーが載る）にも不可**です。台帳・レポート・HP に Keepa グラフ画像を貼る案が出たら、法務は止めます。
なお `add_keepa_link_columns.py` が台帳に入れている `https://keepa.com/#!product/5-<ASIN>` は**ただのリンク**であり、コンテンツの複製ではないので問題ありません（閲覧者は各自の Keepa アカウントで見る）。

---

## 4. 論点③ 1シート制 — 当社の AI 会社構成は「共有」に当たるか

### 4-1. 結論：**当たりません。グレーでもありません。**

秘書からの引用（公式FAQ「サブスクリプションは1ユーザー（1シート）ごと」）は事実ですが、**それは Pro サブスクリプションの話であり、API 契約の条項ではありません。**

**1シート制がどこに書いてあるか（＝どこに書いていないか）**

| 文書 | 単一個人条項 | 原文 |
|---|---|---|
| **Subscriptions T&C（Pro）§4(3)** | **あり・強い** | *"Each subscription purchased from Keepa.com is intended for use by a **single individual** and is strictly non-transferable. Users agree not to share, distribute, or allow access to their subscription or the services provided via Keepa.com to **any other person or entity**."* |
| 公式FAQ「Can I share my subscription?」 | あり | *"No. Subscriptions are per seat. Sharing within organizations or households is not permitted. For multiple users, separate accounts and subscriptions are required."* |
| Pro プラン購入カードの注記 | あり | *"Note: One seat per plan."* |
| **API T&C** | **なし（全文に "seat" も "single individual" も存在しない）** | 代わりに §4(2)：*"the user must ensure that the Service Provider's service is accessed and used exclusively by **the user or authorized users** with their own registration data"* |

**API T&C は「authorized users（許可されたユーザー）」の存在を積極的に予定しています。** §4(3) は *"The user shall be liable... for any activities or use of the Service Provider's services by the user **or authorized users** with their access data."* と、許可ユーザーの行為について**ユーザーが責任を負う**という建て付けです。つまり API 契約の思想は「1人だけ」ではなく「**主体は1契約者、行為者が増えても責任は契約者が丸被り**」です。

### 4-2. AI エージェントは「person or entity」か

仮に厳しい方（Subscriptions T&C §4(3)）が適用される場合でも、**該当しないと判断します。**

1. **文言**：禁止対象は *"any other **person or entity**"*。Claude Code は法人でも自然人でもなく、契約者が自分の端末で動かす**ソフトウェア**です。`scan_v13.py` を「他人」と呼ばないのと同じ理屈で、MCP クライアントも他人ではありません。
2. **提供者の行為**：Keepa は AI アシスタント向けの接続手段を公式に用意し、*"Give AI assistants like Claude structured access..."* と自ら推奨しています。**自社サブスクの範囲内で AI に使わせること自体を、提供者が想定・推奨している。**
3. **多義性は使用者不利**（BGB §305c(2)）。

**したがって、「社長1名の作業を AI が代行する」構成は共有に当たりません。**

### 4-3. では、当社で本当に危ないのはどこか

AI ではなく**人間の頭数**です。以下は明確な違反です。

| 危険な運用 | 判定 | 根拠 |
|---|---|---|
| 外注スタッフに Keepa のログイン ID/PW を渡す | **NG** | Subscriptions T&C §4(3)、FAQ |
| 外注スタッフに API アクセスキーを渡して各自の PC で叩かせる | **NG に近いグレー** | API T&C §4(1) 秘匿義務／§14(1)(vi) 免責条項 |
| 家族が同じアカウントで Keepa を見る | **NG** | FAQ *"Sharing within organizations or households is not permitted"* |
| **社長が Keepa データを CSV/シートで見て、外注に「この商品を仕入れて」と指示する** | **OK** | 提供しているのは**判断結果**であって、Keepa サービスへのアクセスではない |
| 社長管理下の端末で AI エージェントが MCP を叩く | **OK** | §4-2 |
| **クラウド／夜間自走セッションにキーを置く** | **⚠ 要統制** | 「社長管理下」から外れる。§8-条件③ |

> **実務上の落としどころ**：外注に共有してよいのは「Keepa から得た数字を当社が加工した結論」までです。**Keepa への入口（ID/PW/キー/拡張機能入りブラウザ）は絶対に渡さない。** この線を引いておけば、体制を何人に増やしても 1シート制は破れません。

---

## 5. 論点④ API キーの取り扱い — Notion 保管は **NO**

### 5-1. 規約上の義務

> *"(1) During the registration process, the user must provide confidential registration data such as a user name and password, **which must be kept secret and not disclosed to unauthorized third parties.**"*（API T&C §4(1)）
> *"(2) ...the user must ensure that the Service Provider's service is accessed and used exclusively by the user or authorized users with their own registration data. **If there is reason to believe that unauthorized third parties have obtained or will obtain access to the user's data, the Service Provider must be promptly notified.**"*（同 §4(2)）
> 免責条項 §14(1)(vi)：*"any other party's access and use of the Service with the user's unique username, password or other appropriate security code **to the extent that the third-party access resulted from actions/inactions of the user**"* についても、ユーザーが Keepa を免責・補償する。

**キーが漏れた場合、①損害は当社負担、②Keepa への通知義務が発生、③第三者が起こした問題まで当社が Keepa を守る義務を負う** ── この3点セットです。

### 5-2. Keepa 公式の名指しの警告（MCP ドキュメント）

> *"**Important: Your API key is a secret.** Client configurations that embed it (for example a checked-in `.mcp.json`) **must not be committed to shared repositories or otherwise published.** Anyone with the key can spend your tokens."*
> *"**Tip:** Where possible, **keep the key out of config files that might be committed or shared**..."*

### 5-3. Notion に置くことの評価

社長のご希望（キーを Notion に置いて読み込ませたい）は、**規約と公式警告の両方に正面から当たります。**

| 評価軸 | 内容 |
|---|---|
| 発生確率 | **中〜高**。当社 Notion には Integration トークンで複数のエージェント／自動同期が接続している（`.mcp.json`、`/sync-notion`）。**読める主体が増えるほど漏洩確率は上がる**。Notion の「Web に公開」を1回誤操作すれば即公開 |
| 影響度 | **中**。トークンを他人に溶かされる／不正利用の責任は当社（§14(1)(vi)） |
| **不可逆性** | **高**。**一度外に出たキーは「取り消す」しかなく、取り消せば全スクリプトと MCP が同時に止まる**。漏洩に気づかない期間の被害は回収不能 |
| CLAUDE.md 抵触 | **§4.1「機密情報の外部送信」に該当**。加えて、Notion に置いたキーは AI が読み出すたびに**平文でコンテキストに載って外部 API へ送信される**。これは「保管場所」の問題ではなく「毎回送信する運用」を作ることになる |

**→ 法務判定：NO。グレーではなく黒に近い。**「グレーは原則 NO」以前に、公式が名指しで止めている行為です。

### 5-4. 代替案（実装判断は IT エンジニア タカシへ）

| 案 | 内容 | 法務評価 |
|---|---|---|
| **A（推奨）** | **OS のキーチェーン／パスワードマネージャ**（macOS Keychain / 1Password）に保管し、シェルの環境変数として注入。設定ファイルには `${KEEPA_API_KEY}` 参照のみ書く | ◎ 公式 Tip に完全準拠 |
| B | Keepa 公式コマンド `claude mcp add --transport http keepa https://keepa.com/mcp --header "Authorization: Bearer YOUR_API_KEY"` をそのまま実行（保存先はリポ外のユーザー設定） | ○ **リポジトリには入らないので公式警告には抵触しない**が、平文ファイルに残る。単独運用なら許容 |
| C | リポジトリ内 `.mcp.json` に直書き | **✗ 絶対不可**。`.mcp.json` は `.gitignore` 済みだが、**当リポジトリは PUBLIC** であり、1回の `git add -f` や `.gitignore` 事故で即公開される |
| D | Notion 保管 | **✗ 不可**（§5-3） |

> **社長へのご説明の要点**：「Notion に置きたい」の背景にあるのは *どの環境からでも AI に使わせたい* という要求だと理解しています。それは **A（キーチェーン＋環境変数）を各実行環境に一度ずつ設定する**ことで満たせます。利便性を捨てずに規約を守れるので、Notion を選ぶ理由がありません。
> なお `${VAR}` 展開が Claude Code の設定でそのまま効くかは**技術検証事項（タカシ）**であり、私の所管ではありません。効かない場合は B を採用してください。

---

## 6. 論点⑤ Amazon 側の規約との関係

### 6-1. Keepa データの利用そのもの

**条文上、直接の禁止は確認できませんでした。** ただし後述のとおり **BSA 全文を一次情報で取得できていない**ため、「問題なし」とは断定しません（**条文上不明**）。

判断の骨子（事実に基づく推論であり、条文の引用ではありません）：

- 当社は Amazon のシステムから自分でデータを取っていません。**Keepa GmbH と契約してデータを買っている**だけです。Amazon BSA が規律するのは当社と Amazon の関係であり、当社が第三者から市場データを購入する行為を包括的に禁止する条項は、一般的な BSA の構造上想定しにくい。
- Keepa は Amazon アソシエイト／サードパーティ生態系の一員として15年運用されており、Amazon 側が Keepa 利用者たるセラーを処分した公知の事例を、本レビューでは確認していません（**未確認＝存在しないことの証明ではありません**）。

### 6-2. ⚠ Keepa ブラウザ拡張機能は別問題（グレー）

Keepa 自身のプライバシーポリシーに、次の記載があります。

> *"Our browser extension may occasionally **retrieve product information from Amazon pages and send related product data to our servers** to maintain and improve our services. ... **You can disable this in the extension settings at any time.**"*（keepa.com `#!disclaimer` プライバシーポリシー）

つまり **拡張機能を入れたブラウザは、Amazon のページ情報を第三者サーバへ送っています**。Amazon の Conditions of Use には *"any use of data mining, robots, or similar data gathering and extraction tools"* を許諾から除外する条項があるとされます（**二次情報。一次情報は amazon.co.jp のボット遮断により本レビューでは取得できず＝未確認**）。

| 評価軸 | 内容 |
|---|---|
| 発生確率 | 低（数百万人が使う拡張。個別セラーの処分事例は未確認） |
| 影響度 | **高**（アカウント警告〜停止は当社事業の生命線） |
| 不可逆性 | 中〜高（停止からの復帰は POA 次第） |

**実務上の落としどころ**：拡張機能の利用自体は継続してよい（禁止すると Keepa を使う意味が消え、リスクに対して対価が見合わない）。ただし **セラーセントラルにログインしているブラウザプロファイルでは Keepa 拡張を動かさない**。買い物用／リサーチ用と、出品管理用のブラウザプロファイルを分けるだけで、この論点はほぼ消えます。**コストゼロの分離なので、やらない理由がありません。**

### 6-3. ⚠⚠ Amazon Agent Policy（2026-03-04 施行）— これが本命です

社内に「Amazon が AI エージェントによるアクセス規制を強化」という未検証の報告があるとのことでした（T-20260817-004）。**未検証ではなく、事実である可能性が高い**と判断します。

複数の業界メディアが、**2026年3月4日発効の Business Solutions Agreement 改定**として次を報じています（いずれも**二次情報**）：

- BSA に **Subsection 4.2**（Amazon の素材・サービスを AI/機械学習モデルの開発・改善に使うことの禁止）と **Section 19**（自動化エージェント／AI システムの定義と制限）を追加。
- 新設 **Agent Policy** の要求：**(a) AI エージェントは自動化システムであることを常に明示すること、(b) Agent Policy を例外なく遵守すること、(c) Amazon から要求されたら直ちにアクセスを停止すること。**
- 適用範囲として、価格・在庫の自動化、**ブラウザ自動化ツール**、スクリプト、セラーセントラルにアクセスする第三者ベンダーが挙げられている。
- **2026-03-04 以降のサービス継続利用が、改定条件への承諾とみなされる。**
- 参照されている公式ページ：`https://sellercentral.amazon.com/help/hub/reference/external/G47071`

**当社にとっての意味（率直に申し上げます）**

CLAUDE.md §4.4 で、当社は「**ブラウザ上の作業は秘書がブラウザツールで実行する**」を明文の運用原則にしています。これは Agent Policy の「ブラウザ自動化ツール」に真正面から当たる可能性があります。**Keepa MCP の1シート論点よりも、桁違いに大きい論点です。**

| 評価軸 | 内容 |
|---|---|
| 発生確率 | **不明（一次情報未取得）**。ただし施行済みなら、当社は既に5ヶ月以上、無自覚に適用下にある |
| 影響度 | **最大**（BSA 違反 → アカウント停止。当社事業そのものが消える） |
| **不可逆性** | **最高**（社長は既に KYC 起因の米国店停止を経験済み。日本店の停止は事業終了と同義） |

**→ 法務としての要求：本件は Keepa の件から切り離し、独立チケットで一次情報を確認してください（§10-A）。** セラーセントラルはログインが要るため、私は取得できません。CLAUDE.md §4.4 の例外（ログインは社長の一手）に沿ってカズヨが取得してください。

**それまでの暫定運用（法務推奨）**：セラーセントラル上の操作について、**在庫・価格・出品の変更、購入者へのメッセージ送信など「Amazon 側に書き込む操作」を AI が実行することは一時停止**し、閲覧・情報取得に限る。書き込みは社長が実施する。これは §4.4 の分担を一時的に狭めるものですが、確認が取れるまでの期間限定措置として提案します。

---

## 7. ⚠ 当社の既存運用で、いま是正が必要な点

**MCP の可否より優先度の高い指摘です。**

### 7-1. PUBLIC な GitHub リポジトリに Keepa 由来データが commit されている

- 当リポジトリは **PUBLIC** です（`gh repo view` にて確認、2026-08-24 / `https://github.com/Yukinori1018/ai-company-amazon_buppan`）。
- 追跡下にある Keepa 由来データ（一例）：

| ファイル | 行数 | 含まれる Keepa 由来項目 |
|---|---|---|
| `workspace/output/deliverables/T-20260817-005/candidates_v13.csv` | 約 4,000 | ランク／月間ドロップ数／月間販売数／出品者数／BuyBox価格／過去1年最安値 |
| `workspace/output/deliverables/T-20260803-001/shiire_list_3000.csv` | 約 4,400 | sales_rank／offer_count／monthly_sales／buybox ほか |
| `workspace/output/deliverables/T-20260705-002/research/maker_candidates.csv` | 数百 | 現ランク／現FBA出品者数／推定月販 |
| ほか `T-20260705-001/*.csv` 等 | 数千 | 同種 |

- 抵触しうる条項：API T&C **§11(1)**（*"not permitted to modify, edit, translate, or **reproduce** any content"*）、および Subscriptions T&C §11(1)（*"Editing, modifying, translating, exhibiting, **publishing**, reproducing, or **disseminating** the content, in whole or in part, is prohibited"*）。§2(2)/§6.1(1) の「third-party purposes への提供」にも接近します。

| 評価軸 | 内容 |
|---|---|
| 発生確率 | **中**。誰でも閲覧・スクレイプできる状態が既に数ヶ月継続。競合が Keepa へ通報する動機は現実にあります |
| 影響度 | **高**。API アクセス遮断（§13 Blocking Access）＋契約解除（§12(3)）＋ §14(1) の補償義務 |
| 不可逆性 | **高**。**Git 履歴に残るため、いま削除しても過去のコミットからは取得可能**。フォーク済みなら回収不能 |

**加えて、Keepa 以外にも同じ穴が空いています**：メーカー担当者の連絡先を含む `T-20260804-001/contacts_*.json` 等が公開されている可能性があります。**個人情報保護法（第三者提供）の論点になりうるため、Keepa の件と併せて棚卸ししてください。**（本レビューの対象外。要別途チェック）

### 7-2. 是正案（A/B/C ＋推奨） — **実行は社長承認事項**

> ⚠ Git 履歴の書き換え・ファイル削除は **CLAUDE.md §4.1「不可逆な削除」**に該当します。**私は実行しません。** 判断材料のみ提示します。

| 案 | 内容 | 効果 | 副作用 |
|---|---|---|---|
| **C（推奨）** | **リポジトリを Private 化する** | **1操作で全部が閉じる。**過去履歴も含めて外部から見えなくなる。Keepa の件も連絡先の件も同時に解決 | 成果物カタログの GitHub blob リンクは**社長本人はログイン済みで閲覧可**。第三者に見せる必要が出た時だけ個別公開に切り替える。GitHub Pages は未使用（`gh api .../pages` が 404）なので **HP 公開への影響なし** |
| B | `git rm --cached` ＋ `.gitignore` で追跡解除 | 今後の露出は止まる | **過去履歴は残る**（＝抜本解決にならない）。§4.1 該当 |
| A | 現状維持。以後 `deliverables/` に Keepa 由来の生データを置かない運用に変更 | 追加露出は止まる | 既存分は放置。**推奨しません** |

**法務推奨：C。** 理由は「不可逆性が最も高いリスクを、最も可逆的で低コストな1操作で消せる」から。Private 化は後でいつでも Public に戻せます（可逆）。一方、公開してしまったデータは戻せません（不可逆）。**可逆な手段で不可逆なリスクを消せる時は、迷わずそれを選ぶべきです。**
C を採らない場合は、最低でも **B ＋ A の併用**を条件とします。

### 7-3. 本レビュー文書自体の扱い（自己適用）

本文書には Keepa の T&C 原文を引用しています。**引用は「必要最小限＋出典明示＋自社の評価が主」の形に留め**（著作権法32条1項）、**全文の複製・翻訳は行っていません**。原文全体は Git 追跡外の `workspace/output/agent_output/T-20260824-001/legal-sources/` にのみ保存しました。§7-2 で C（Private 化）を採る場合はこの制約は緩みますが、**当面はこの方針を維持**してください。

> ⚠ **カズヨへ：この文書自体が §7-2 の一番強い論拠です。**
> 私は社内ルール（成果物は `deliverables/` に直納し即 commit）に従って本文書を commit しますが、**本文書は当社のコンプライアンス上の弱点を一覧にしたもの**であり、公開リポジトリに置くのに最も適さない種類の文書です。CSV より本文書のほうが「読まれて困る度合い」は上です。
> **本文書を公開したくない**という理由だけでも、リポジトリの Private 化（C 案）を社長に諮る価値があります。逆に「commit するな／追跡から外せ」というご判断であれば、それは **§4.1（不可逆な削除）に隣接する操作**なので、私ではなくカズヨが社長承認を取って実施してください。

### 7-4. 私自身の取得方法についての自己申告

透明性のため記録します。**規約解釈上、私の行為も完全に白ではありません。**

- keepa.com の T&C は本来「API 契約画面の "Terms and Conditions" リンク」から読むものですが、当社からは Cloudflare の Anti-bot check により当該画面へ到達できません（カズヨが 2026-08-24 に実機で確認済み）。
- そこで、公開配信されている `keepa.js`（ブラウザが通常読み込むスクリプト）を読んで T&C の**公開 URL** を特定し、`https://keepa.com/cdn/termsAPI.txt` / `termsSubscriptions.txt` を認証なしの単純 GET で取得しました。**ボット検知の回避は一切していません。非公開エンドポイントも使っていません。**
- ただし、curl による取得は文言上「ウェブサイトの自動化された利用」（サイト ToS）に触れうる行為です。**今後 keepa.com 本体のコンテンツを取得する必要が生じた場合は、curl / WebFetch ではなくカズヨのブラウザ操作で行ってください**（CLAUDE.md §4.4 の既存ルールどおりに運用すれば足ります）。私の今回の取得は、規約レビューという目的の必要最小限に留めています。

---

## 8. 導入条件（条件付き GO の「条件」）

以下**6件すべて**を満たすことを導入の条件とします。1つでも欠ければ、法務判定は GO ではなく保留です。

| # | 条件 | 担当 |
|---|---|---|
| ① | **API キーをリポジトリ内の設定ファイルに書かない。** OS キーチェーン／環境変数経由とする（§5-4 案 A、不可なら B） | タカシ |
| ② | **Notion その他の外部 SaaS にキーを保管しない。** 例外なし | 全員 |
| ③ | **クラウド／夜間自走セッションにキーを配置しない。** 必要が生じた場合は、その時点で改めて法務判断を求めること（社長管理下から外れるため） | カズヨ |
| ④ | **トークン消費の上限運用を決める。** MCP はレスポンスに残高を返すので、月次の許容消費量と、超過時に停止する閾値を経理（ハジメ）と決めておく | ハジメ／タカシ |
| ⑤ | **書き込み系ツール（price tracking の作成・削除）を AI に使わせない。** 読み取り専用で運用。クライアント側で制限できないなら「使わない」を運用ルールとして明記 | タカシ |
| ⑥ | **§7-2 の是正（推奨 C）について社長の判断を得る。** MCP を足す前に、いま開いている穴を閉じること | 社長／カズヨ |

### リスクシナリオ・発生時の対応・撤退条件（グレー案件の3点セット）

| リスクシナリオ | 発生時の対応 | 撤退条件 |
|---|---|---|
| キー漏洩（リポジトリ／SaaS／ログ経由） | ① Keepa API ダッシュボードでキーを即時再発行 ② API T&C §4(2) に基づき info@keepa.com へ通知 ③ 全スクリプト・MCP の設定を差し替え ④ 漏洩経路をチケット化 | 同一原因で**2回目**の漏洩が起きたら MCP 運用を停止し、スクリプト経由（キーが1箇所にしかない構成）に戻す |
| Keepa から警告・アクセス遮断（§13） | ① 直ちに全自動処理を停止 ② 指摘事項を特定し是正 ③ 是正報告を送付 | 是正後も遮断が解除されない場合、Keepa 依存の仕入れ判断ロジックを停止し、代替（ERESA 等）の再評価に切り替える |
| Keepa が T&C を改定し AI/MCP 利用を制限 | §19 により**6週間前に text form で通知**され、異議申立て可。通知を見落とすと黙示承諾になる | 改定内容が当社の運用（保存・社内再利用）を否定する場合、6週間以内に異議 → §12 で解約 |
| Amazon Agent Policy 違反の指摘 | ① セラーセントラルへの AI 書き込み操作を全面停止 ② 一次情報を取得し差分を是正 ③ 必要なら POA | 一次情報上、当社の運用が明確に違反と判明した場合、**§4.4 の運用原則そのものを改定**する（AI ブラウザ操作の全面停止を含む） |

---

## 9. 条文上・事実上、確認できなかった点（推測で埋めていません）

| # | 項目 | 状態 | 解消方法 |
|---|---|---|---|
| ① | 当社の Keepa 契約が「独立 API プラン」か「Pro 付属の API」か | **事実未確認**。社内資料は独立 API プラン €49/月を示すが、請求実物は未確認。適用契約が A か B かに影響（§4 の1シート論点） | Keepa 設定画面 → サブスクリプションダッシュボード、または請求書 PDF を1枚確認（カズヨ／ブラウザ） |
| ② | API T&C が MCP／AI エージェント利用を明示的に許諾しているか | **条文上不明**。禁止条項に当たらないことと、Keepa 自身が公式提供していることからの帰結として GO と判断 | 決定打が要るなら info@keepa.com へ照会（第三者連絡＝§4.1。社長承認が必要） |
| ③ | 解約後に保存済み Keepa データを使い続けてよいか | **条文の文理では可**（§11(2) *"non-exclusive and unlimited right of use"*）。ただし §11(1) の「利用権は契約期間に限る」との整合について公式見解なし | ②と同じ照会に含める |
| ④ | Amazon BSA 本文・Agent Policy（G47071）の原文 | **未取得**。sellercentral はログイン必須で JS レンダリング。当方から到達不可 | カズヨがログイン状態のブラウザで取得（§10-A） |
| ⑤ | Amazon Conditions of Use（amazon.co.jp 508088）の data mining 条項原文 | **未取得**。amazon.co.jp がボット遮断（HTTP 503／空レスポンス） | カズヨがブラウザで取得 |
| ⑥ | Google スプレッドシート（台帳・成果物カタログ）の共有設定 | **未確認**。「リンクを知っている全員」になっていれば §7-1 と同じ問題が発生する | カズヨが各シートの共有設定を確認 |
| ⑦ | Keepa が過去にセラーの規約違反を実際に執行した事例 | **未確認**（公知の事例を確認できず。ないことの証明ではない） | 継続ウォッチ |

---

## 10. 秘書カズヨへの依頼事項

**A（最優先・別チケット化を推奨）Amazon Agent Policy の一次情報取得**
- `https://sellercentral.amazon.co.jp/help/hub/reference/external/G47071`（Agent Policy）
- Business Solutions Agreement 本文（Subsection 4.2 と Section 19 の有無・原文）
- Amazon.co.jp 利用規約 `nodeId=508088` の「ライセンスとサイトへのアクセス」条項
- いずれもログインが要ります。CLAUDE.md §4.4 に従い、ログインの一手だけ社長にお願いして操作を引き取ってください。**取得できたら法務へ回してください。私が読みます。**

**B（軽い・ブラウザ1〜2手）**
- Keepa サブスクリプションダッシュボードで、契約が「API プラン」か「Pro」かを確認（§9-①）
- Google スプレッドシート各種の共有設定を確認（§9-⑥）

**C（社長判断が要る事項）** → §7-2 の A/B/C。**法務推奨は C（リポジトリの Private 化）**。

---

## 11. 出典一覧（すべて 2026-08-24 確認）

| # | 文書 | URL | 取得方法 |
|---|---|---|---|
| 1 | Keepa Price Data API T&C（Version of July 28, 2026） | `https://keepa.com/cdn/termsAPI.txt` | 認証なし GET（keepa.com の API 契約画面が読み込む実ファイル） |
| 2 | Keepa Subscriptions T&C（Version of August 22, 2026） | `https://keepa.com/cdn/termsSubscriptions.txt` | 同上 |
| 3 | Keepa サイト Terms of Service / Privacy Policy / Trademarks | `https://keepa.com/#!disclaimer`（本文は `https://keepa.com/cdn/languages/{en,ja}.json` の `_165`〜`_170`, `_792`〜`_794`, `_150`） | 同上（SPA のため言語リソースから原文取得） |
| 4 | Keepa 公式FAQ「Can I share my subscription?」 | `https://keepa.com/#!support`（`_891` / `_907`） | 同上／カズヨのブラウザ実機確認と一致 |
| 5 | Keepa MCP Server ドキュメント | `https://keepa.com/api-docs/mcp.html` | サトル保全済み HTML |
| 6 | Keepa Graph Image API ドキュメント | `https://keepa.com/api-docs/graph-image.html` | 同上 |
| 7 | Keepa Pro プラン購入カード注記（"One seat per plan."／"API access (1 token/min)"） | `https://keepa.com/cdn/20260826/keepa.js` | 認証なし GET |
| 8 | Amazon BSA 改定・Agent Policy（**二次情報**） | ppc.land / EcommerceBytes / EcomCrew の各記事、Seller Central フォーラム告知 | WebSearch。**一次情報は未取得** |

> 原文全文は `workspace/output/agent_output/T-20260824-001/legal-sources/`（Git 追跡外）に保全しています。

---

## 12. 法務としての一言

MCP の導入自体は止めません。**Keepa が自分で用意した扉を、鍵を持っている当社が通るだけの話**です。

止めるのは2つ。**キーを Notion に置くこと**と、**Keepa のデータを公開リポジトリに置き続けること**。前者は公式が名指しで禁じており、後者は既に起きている継続的な違反状態です。どちらも「発覚したら終わり」の性質を持ち、しかも**片方は無料で、もう片方は1操作で消せます**。順序としては、穴を塞いでから機能を足してください。

そして、本件の調査中に見つかった **Amazon Agent Policy（2026-03-04 施行）** のほうが、当社にとってはるかに重大です。当社はアカウント停止を一度経験しています。**二度目は事業の終わりです。** 一次情報の確認を最優先でお願いします。

以上。
