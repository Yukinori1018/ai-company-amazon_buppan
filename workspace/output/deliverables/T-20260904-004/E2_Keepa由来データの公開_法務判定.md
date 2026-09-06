# E2. Keepa 由来データの PUBLIC リポ公開 — 法務判定

法務ハルオ／2026-09-06／T-20260904-004
一次情報はすべて当職が自分で取得。取得日はいずれも 2026-09-06。

---

## 結論（1行）

**Keepa API T&C §11(1)「reproduce 禁止」に抵触します。ただし危ないのは今回の 02 ではなく、`main` に2ヶ月前から載っている過去チケットの CSV 17本・ユニーク ASIN 19,598 件です。推奨は B＝リポジトリの Private 化。制裁は「金銭」ではなく「API 遮断」で、金銭は契約上 2×年額（約20万円）に上限が切られています。Amazon アカウントには一切波及しません。**

---

## 0. 当職自身の記述を2点訂正します

依頼どおり、自分の §7 申し送りにも同じ検証を当てました。**2件とも当職の誤りでした。**

| 当職の記述（E 判定 §7） | 実際 |
|---|---|
| 「`02_メーカー打診候補リスト.html` は **Keepa 由来399社**のデータを含む」 | **02 に ASIN は1件も入っていません**（`B0[0-9A-Z]{8}` の一致 0）。入っているのは メーカー名／該当商品数／主なカテゴリ／想定仕入れ金額の中央値／Amazon価格の中央値／代表商品名 の6項目。**月間販売数・出品者数・ランク・価格履歴はいずれも無し**（全文検索で 0 件） |
| 「**03 HTML にも Keepa 由来の月間販売数・出品者数**が入っている」 | **こちらは事実**（`出品者数` 19回・`月間販売数` 4回・`ASIN` 27回）。03 を `.gitignore` に残す理由が NETSEA と Keepa の二重である、という結論は維持します |

**→ 02 と `B1_打診候補_全社_優先度順.csv` は、当職が想定したよりはるかに白い。**
一方で、依頼文の「過去チケットまで遡れ」という指示のほうが的中しています（§3）。

### §11(1) の条番号は正しい

`https://keepa.com/cdn/termsAPI.txt`（Version of July 28, 2026）を平文取得し、全20条を目視。**「11. Usage Rights (1)」に "The user is not permitted to modify, edit, translate, or reproduce any content from the Service Provider's website without express permission" が実在します。**NETSEA のような誤引用はありませんでした。

---

## 1. どの契約書が当たるか

Keepa の契約文書は3本あります（当職が T-20260824-001 で確定済み）。

| # | 文書 | 版 | 適用対象 | URL |
|---|---|---|---|---|
| **A** | **Price Data API T&C** | **2026-07-28 版** | **Keepa API（当社が €49/月で契約）** | `https://keepa.com/cdn/termsAPI.txt` |
| B | Subscriptions T&C | 2026-08-22 版 | Keepa Pro（€29/月・ウェブサイト側） | `https://keepa.com/cdn/termsSubscriptions.txt` |
| C | サイト ToS | 版表示なし | keepa.com の**無料**サービス | `https://keepa.com/#!disclaimer` |

**当社は A。**（`scan_v13.py` 等がアクセスキーで `api.keepa.com` を叩いている＝API 契約）

> ⚠ **未解消の事実確認が1件残っています。**Pro プランにも「API access (1 token/min)」がオマケで付くため、当社が独立 API プランなのか Pro のオマケなのかは**請求ダッシュボードの実物確認が未了**です（T-20260824-001 §9-① から持ち越し）。
> **本件の結論は分岐しません。**B が適用される場合、B §11(1) は *"Editing, modifying, translating, exhibiting, **publishing**, reproducing, or **disseminating** the content, in whole or in part, is prohibited"* と、A よりさらに明示的に公開を禁じているからです。**どちらでもアウト。**

---

## 2. ① Keepa 由来データを PUBLIC リポに載せてよいか

### 2-1. 効く条文と、効かない条文（原文）

| 条 | 原文（抜粋） | 当てはめ |
|---|---|---|
| **§11(1)** | "The user may retrieve and display the online contents provided by the Service Provider **solely for their own business purposes**… The user is **not permitted to modify, edit, translate, or reproduce any content** from the Service Provider's website **without express permission**" | **唯一の直撃条文。**CSV/HTML への転記は "reproduce"、加工は "modify/edit"。express permission なし。→ **抵触** |
| §11(2) | "The user **may save or print out contents** from the Service Provider's website **for their own business purposes**, with a non-exclusive and unlimited right of use" | **手元に CSV で保存する行為はここで明文許諾されている。**問題は保存ではなく**公衆送信**。§11(2) は "save or print" までで、公開までは含まない |
| §2(2) | "The services are provided solely for the user's own business purposes. **Reselling** data for third-party purposes is only allowed with the Service Provider's prior written consent" | **効きません。**当社は販売していない。動詞は "Reselling" |
| §6.1(1) | "**Resale** of the data obtained from Keepa.com is strictly prohibited" | **効きません。**同上 |
| §13 | 違反の "concrete indications" があれば **temporarily or permanently block** できる | **制裁の本体はここ**（§4） |
| §12(3) | extraordinary termination は "**intentionally** violated… or gross negligence" が要件 | 本件は自動 `git add -A` による非意図的混入。**intentional ではない**と主張できる |
| §14(3) | 各当事者の総責任は 12ヶ月間の支払額の **2倍が上限**（Liability Cap） | **金銭上限は €49×12×2 ＝ €1,176（約20万円／1€=170円換算）** |
| — | **penalty / liquidated damages / 監査権 / 違約金条項は存在しない**（全文検索で該当0） | NETSEA 会員規約27条4項のような 200万円条項に相当するものは **Keepa には無い** |
| §20(1)(2) | ドイツ法・Keepa 所在地（Kemnath）の専属管轄 | 提訴のハードルは高い |

**→ 禁止されているのは「再配布」「販売」ではなく、"reproduce"（複製）です。**無償公開でも複製は複製なので、無償だから白、にはなりません。

### 2-2. 契約以外の法的根拠（ドイツ・データベース権）

§20(1) によりドイツ法が準拠法です。ドイツ著作権法（UrhG）には EU 由来の**データベース製作者の権利（sui generis）**があります。

- **§87b(1)**: データベース製作者は、**全部または質的・量的に相当な部分**の複製・頒布・公衆送信の**排他権**を持つ。相当でない部分でも、**反復的・体系的**に行い通常の利用を妨げる場合は同視される。
  出典: https://www.gesetze-im-internet.de/englisch_urhg/englisch_urhg.html
- **§87e**: **質的・量的に相当でない部分**について複製等を禁ずる契約条項は、**通常の利用を妨げず正当な利益を不当に害しない限り無効**。

**当てはめ（両論併記）**

- 不利：19,598 ASIN ×（価格・ランク・オファー数・月販）は、Keepa DB からの**量的に相当な抽出**と評価される余地があります。
- 有利：**日本には sui generis のデータベース権が存在しません**（著作権法12条の2は「選択又は体系的な構成に創作性」があるデータベースのみを保護）。行為地は日本、サーバは米国です。知的財産権は属地主義であり、**ドイツの §87b が本件行為に直接及ぶかは相当に疑わしい**。
- 結論：**主戦場は契約（§11(1)）であって、データベース権ではありません。**データベース権は「もし争われたら追加で主張されうる」程度の位置づけです。**確定的な侵害と断定はしません。**

### 2-3. データの切り分け — 「Amazon で誰でも見られるか」テスト

NETSEA では「非ログインで見えるか」で結論が反転しました。**Keepa では同じ手法は使えますが、効き方が違います。**理由は条項の型が違うからです。

| | 条項の型 | 「公開情報だから白」が効くか |
|---|---|---|
| NETSEA | **秘密保持型**（API 15条1・会員 7条2項3号） | **効く。**秘密でない情報に秘密保持義務は生じない |
| **Keepa** | **利用権・複製禁止型**（§11(1)） | **効かない。**複製禁止は情報の秘密性を要件にしていない |

**したがって「Amazon で見られるから白」は Keepa には通りません。**ただし切り分けには**別の効用**があります — **実害と、Keepa 側の "legitimate interests"（§87b・§13 の考慮要素）の大きさが桁で変わる**からです。

| 項目 | Keepa なしで Amazon 商品ページから今すぐ確認できるか | 位置づけ | 実害 |
|---|---|---|---|
| ASIN | **見える**（URL そのもの） | Amazon の公開識別子 | 極小 |
| 商品名・ブランド・メーカー・カテゴリ | **見える** | 公開情報 | 極小 |
| Amazon 価格（現在の新品最安・カート価格） | **見える**（スナップショット） | 公開情報 | 極小 |
| ランキング（sales_rank） | **見える**（「Amazon 売れ筋ランキング」欄） | 公開情報 | 極小 |
| 新品オファー数（offer_count） | **見える**（「新品 (N)件の出品」） | 公開情報 | 極小 |
| セラー名一覧 | **見える**（出品者一覧ページ） | 公開情報 | 小 |
| **月間ドロップ数** | **見えない** | **Keepa 固有の加工値**（Keepa のランク履歴 DB からの算出） | **大** |
| **過去最安値・365日最安・価格履歴** | **見えない** | **Keepa の中核商品そのもの** | **大** |
| **月間販売数（ドロップ数からの推計）** | **見えない**（Amazon の「過去1か月で N点購入」バッジは別物。Keepa 推計とは算出根拠が違う） | **Keepa 固有の加工値** | **大** |
| 実セラー数（重複除去後） | 見えない（生の出品者数から当社/Keepa が加工） | 加工値 | 中 |
| 消化月数・損益分岐仕入れ値・想定仕入れ額・利益率 | 見えない | **当社の計算**。ただし**入力が Keepa 固有値なら派生物** | 中 |

> **判定の型（次回もこれを使う）**
> 1. **その値が Keepa の履歴 DB を通らないと出せないか**で分ける（＝ Keepa 固有の加工値）。
> 2. 固有の加工値は **§11(1) 直撃・実害も大**。
> 3. スナップショット値は **§11(1) には形式的に当たるが、実害はほぼゼロ**（Keepa を契約せずとも Amazon で取れるため、Keepa の正当な利益を害さない）。
> 4. **「白い」とは言いません。**グレーは原則 NO。ただし**是正の優先順位は 2 → 4 → 3 の順**で付けてよい。

---

## 3. ② 現に公開されているものの全量（実測）

`git ls-files` で追跡ファイルを全走査しました。

### 3-1. 今回のチケット（T-20260904-004）

| ファイル | 追跡 | ASIN | Keepa 固有値 | 判定 |
|---|---|---|---|---|
| `02_メーカー打診候補リスト.html`（882KB・399社） | **追跡中** | **0件** | **無し** | **§11(1) の対象になる Keepa 固有値は含まれていない。**Amazon価格の中央値・該当商品数は Keepa 経由で得たスナップショット値の統計であり、原データの復元は不可能。**このファイル単独で追跡を止める必要は認めません**（※§3-3 の別論点あり） |
| `B1_打診候補_全社_優先度順.csv`（399行・538KB） | **追跡中** | **0件** | **無し** | 同上 |
| `B1_work_queue.csv`（228行） | **追跡中** | **228件** | **消化月数の中央値**（Keepa 月販の派生） | **抵触。**軽微だが対象 |
| `B1_contacts_top50.csv` | 追跡中 | 0件 | 無し | 対象外 |
| `03_初回仕入れ_発注セットと全体まとめ.html` | 追跡外 | 27件 | 出品者数・月間販売数 | **抵触。**追跡外の判断は正しい（NETSEA と二重の理由） |

### 3-2. 過去チケット — **ここが本丸です**

**追跡中かつ Keepa 固有値を含むファイル：17本。ユニーク ASIN 19,598 件。**

| ASIN数 | ブランチ | ファイル | 含まれる Keepa 固有値 | 公開開始 |
|---|---|---|---|---|
| 7,834 | **origin/main** | `T-20260804-001/monthlysold.csv` | monthly_sold_real | 2026-08-05 |
| 7,834 | **origin/main** | `T-20260804-001/maker_products.csv` | monthly_sales, rival_sellers | 2026-08-05 |
| 4,446 | **origin/main** | `T-20260803-001/shiire_list_3000.csv` | monthly_sales, offer_count, buybox | 2026-08-03 |
| 3,846 | **origin/main** | `T-20260817-005/candidates_v13.csv` | **月間ドロップ数・過去最安値・365日最安**・新品オファー数・実セラー数・想定月販 | 2026-08-21 |
| 3,276 | **origin/main** | `T-20260804-001/maker_ledger.csv` | sum_monthly | 2026-08-05 |
| 1,996 | **origin/main** | `T-20260705-001/density_v2_results.csv` | monthly_sales, offer_count, buybox | **2026-07-06** |
| 1,134 | branch | `T-20260831-004/12_全メーカー判定台帳.csv` | 実セラー数 | — |
| 269 | **origin/main** | `T-20260705-001/netsea_scan_results.csv` | msales ＋**NETSEA 卸値**（2026-08-31 の先例ファイル） | 2026-07-06 |
| 262 | branch | `T-20260831-004/10_連絡候補メーカー.csv` | 実セラー数 | — |
| 235 | **origin/main** | `T-20260705-001/density_scan_results.csv` | monthly_sales, offer_count | 2026-07-06 |
| 220 | branch | `T-20260831-004/11_条件付き候補_再販版元カテゴリ.csv` | 実セラー数 | — |
| 187 | **origin/main** | `T-20260705-001/density_v2_gems_liquidity.csv` | monthly_sales, offer_count, buybox | 2026-07-06 |
| 100 ×2 | **origin/main** | `T-20260817-005/candidates_v13_top100(_clean).csv` | **月間ドロップ数・過去最安値・365日最安** | 2026-08-21 |
| 100 | **origin/main** | `T-20260804-001/maker_contact_shortlist.csv` | sum_monthly | 2026-08-05 |
| 47 ×2 | **origin/main** | `T-20260705-001/buy_shortlist(_amazon).csv` | BuyBox | 2026-07-06 |

**要点3つ**

1. **14本が `origin/main`＝デフォルトブランチに載っています。**NETSEA の件（非デフォルトブランチ1本）とは露出の質が違います。デフォルトブランチはコード検索・アーカイブ・クローラの一次対象です。
2. **最古は 2026-07-06。既に2ヶ月公開されています。**「今日気づいた」問題ではありません。
3. **最も黒いのは `candidates_v13.csv` 系（3,846 ASIN）**です。**月間ドロップ数・過去最安値・365日最安**という、**Keepa を契約しないと絶対に得られない値**が生で入っています。これは Keepa の商品そのものの部分的な複製に最も近い。

### 3-3. 本件の射程外（別途判定が要るもの）

**`02` と `B1_*.csv` は Keepa 論点では白ですが、別の論点で黒い疑いがあります。**399社分の**代表者名を含まない法人連絡先**（所在地・電話・メール）を PUBLIC リポに載せています。法人情報そのものは個人情報保護法の「個人情報」ではありませんが、**個人事業主・屋号や、`info@` でない個人名アドレスが混ざっていれば同法27条（第三者提供）の問題になります。**当職の記憶ファイル `knowledge_public_repo_pii_and_thirdparty_db.md` でも「未精査・要別途チェック」のまま残っています。**別チケットでの判定を推奨します。**

---

## 4. 制裁の内容 — 社長の最大の関心事に答えます

社長のご懸念（「Keepa が切れたらリサーチ基盤が止まる」「Amazon アカウントが停止中」）に、条文で直接お答えします。

| 制裁 | 条文 | 評価 |
|---|---|---|
| **① API アクセスの遮断**（一時／恒久） | **§13** "may temporarily or permanently block… if there are concrete indications that the user has violated these terms"。ただし **"will consider the user's justified interests"** | **これが本命。**発動要件は「具体的兆候」だけで、催告も予告も不要。**ご懸念どおり、リサーチ基盤が止まります** |
| ② 特別解約 | §12(3) **"intentionally violated… or gross negligence"** | **要件が重い。**本件は自動 `git add -A` による非意図的混入で、意図的ではない。ただし**「2ヶ月・19,598件・気づいた後も放置」となると gross negligence の評価に近づきます**。＝**気づいた今が分水嶺** |
| ③ 通常解約 | §12(2) 1ヶ月前予告・日割返金 | 理由不要。ただし Keepa はいつでも行使できるので本件固有のリスクではない |
| **④ 金銭** | **§14(3) Liability Cap ＝ 12ヶ月間の支払額の2倍** | **€1,176（約20万円）が上限。**違約金条項・懲罰賠償条項は**存在しません**（全文検索で該当0）。§17(4) で逸失利益も除外 |
| ⑤ 訴訟 | §20(2) **Kemnath（ドイツ）の専属管轄** | €1,176 の回収のためにドイツから日本の一人会社を訴える経済合理性は無い |
| **⑥ Amazon アカウントへの波及** | — | **ありません。**Keepa は Amazon の関連会社ではなく、本件は Keepa との私法上の契約違反です。Amazon 出品規約・アカウント健全性・現在の3か国停止（本人確認）とは**法的経路が一切繋がっていません**。**この心配は不要です** |

**まとめ：金銭は上限20万円で恐くない。恐いのは §13 の API 遮断ただ1点。**そして §13 は「Keepa が気づくかどうか」だけに懸かっています。

### リスク3軸

| 軸 | 評価 | 根拠 |
|---|---|---|
| 発生確率 | **低〜中** | fork 0・star 0（`gh repo view` 実測）。ただし**14本が `main` に2ヶ月**。GitHub のコード検索は公開リポ全文を索引化しており、`candidates_v13` のような Keepa 固有列名は特徴的な検索語になります。NETSEA 案件（非デフォルトブランチ・30分）より確率は明確に高い |
| 影響度 | **中〜高** | 金銭は上限20万円。ただし**API 遮断＝リサーチ基盤の停止**。当社の主力手法（メーカー抽出・v1.3 基準スキャン）はすべて Keepa API 依存 |
| **不可逆性** | **高** | 2ヶ月分は回収不能。§4 の force push 評価（当職が E 判定で確立済み）どおり、履歴書き換えでは消えない |

---

## 5. ③ 取るべき措置（A/B/C＋推奨）

| 案 | 内容 | 判定 |
|---|---|---|
| **A** | 履歴から除去（force push / filter-repo） | **非推奨。**E 判定 §4 の評価をそのまま適用します。①GitHub はダングリングコミットを即座に消さず `/commit/<sha>` で当分見える（確実な消去は GitHub Support への依頼＝第三者連絡・§4.1）②既にクローン／コード検索索引に入っていれば回収不能（**2ヶ月経過している本件では前提として想定すべき**）③`.claude/scripts/github-sync.sh` は分岐検知で何もせず終了する設計のため、**30分ごとの自動同期が止まる**。**リスクは減らず、コストだけ確定します** |
| **B** | **リポジトリを Private 化** | **推奨。**1操作・**可逆**（いつでも Public に戻せる）・**履歴も含めて全部閉じる**唯一の手段。副作用の実測：**GitHub Pages 未使用**（`gh api …/pages` が 404・2026-09-06 再確認）、成果物カタログの GitHub リンクは所有者（社長）が閲覧するので Private でも開ける、`github-sync.sh` は認証済みなので影響なし。**19,598 ASIN を今後の増加ごと止められるのは B だけです** |
| **C** | HEAD から削除・履歴は残す（先例 `f450b01` と同じ） | **B と併用なら可、単独では不十分。**単独だと `origin/main` の2ヶ月分の履歴が公開されたまま残ります |
| **D** | 現状維持 | **不可。**§12(3) の gross negligence 評価に近づくだけです |

### 推奨 ＝ **B（Private 化）→ その後 C（HEAD からの整理）→ 落ち着いたら Public 復帰を検討**

**先例（`f450b01`・2026-08-31・卸価格227行）と扱いを変える理由を明示します。**

| | 2026-08-31 の先例 | 本件 |
|---|---|---|
| 規模 | 227行・1ファイル | **19,598 ASIN・17ファイル** |
| ブランチ | — | **14本が `origin/main`（デフォルト）** |
| 経過 | 当日発覚 | **最古 2026-07-06＝2ヶ月** |
| 制裁の型 | 会員登録取消（NETSEA） | **API 遮断（Keepa §13）** |

**先例は「HEAD から削除・履歴は残す」でしたが、あれは非デフォルトブランチの小規模・即日発覚の事案です。本件は規模・露出・経過のすべてが1〜2桁違います。同じ扱いにする合理性はありません。**
なお当職の記憶ファイル `knowledge_public_repo_exposure.md`（2026-08-24 起票）は、**当時すでに Private 化を推奨していました**。**その推奨が実行されないまま2週間で ASIN が積み増しされた、というのが本件の実体です。**

### B を実行しない場合の3点セット（グレーを通すので必須）

| | 内容 |
|---|---|
| **リスクシナリオ** | Keepa が GitHub コード検索等で当該 CSV を発見 → §13 により**予告なく API アクセスを block** → `scan_v13.py` 系のスキャンが全停止。メーカー抽出・v1.3 基準による候補生成が不能になり、**T-20260904-004 以降の仕入れパイプラインが止まる**。金銭請求は §14(3) により最大 €1,176（約20万円） |
| **発生時の対応策** | ①**先に削除を完了させる**（Private 化 or 該当ファイル除去）→ ②削除完了の事実を添えて Keepa へ説明し、非意図的（自動 `git add -A`）である旨と再発防止策を提示（**第三者連絡＝§4.1・要社長承認**）→ ③復旧を求める。**順番を逆にしない**（謝罪が先だと「削除していない状態での自白」になる） |
| **撤退条件** | ① Keepa から照会・警告メールが来たら**即時 Private 化**（この時点で費用対効果が完全に逆転）／② 同種の混入が**もう1件**発生した時点で、判断を待たず Private 化／③ 30日以内に是正が完了しない場合、B を強制適用 |

**当職は §4.1 該当操作（Private 化・force push・履歴書き換え・ファイル削除・Keepa への照会）を一切実行していません。判定のみです。実行は社長承認のうえ、秘書／IT の領分です。**

---

## 6. ④ 実務ルール — 今後 Keepa 由来データをどう扱うか

### 6-1. 一般則（3行）

1. **Keepa 固有の加工値（履歴 DB を通らないと出せない値）は、Git 追跡下に置かない。**置き場は `agent_output/` ではなく、`deliverables/<ticket_id>/.gitignore` によるホワイトリスト除外（成果物は消さない・追跡だけしない）。
2. **スナップショット値（ASIN・商品名・ブランド・現在価格・ランク・オファー数）は、行数で判断する。**判定基準は §6-2。
3. **成果物に載せてよいのは「統計・分布・判断結果」であって「行データ」ではない。**中央値・件数・カテゴリ内訳は原データを復元できないので §11(1) の "reproduce" に当たりません（**本件の 02 が白いのはこの構造だからです**）。

### 6-2. 行数のしきい値（法的根拠つき）

UrhG **§87e** は、**「質的・量的に相当でない部分」の複製を禁ずる契約条項は無効**としています。文中に ASIN が数件出るだけの引用・障害報告・ナレッジ記事まで一律に止めるのは、法的にも実務的にも過剰です。

> **推奨しきい値：1ファイル内のユニーク ASIN が 20件以上 → ブロック。19件以下 → 警告のみ（通過可）。**
> 20 という数字は法定ではありません。当職の実務判断です。既存の合法的な文書（`seller-count-defect-report.md`＝10件、`keepa-glossary.md`＝5件、`pricing-formula-explainer`＝9件）が誤検知で全部止まる境界が実測で 10〜16 件だったため、その上に取りました。

**ただし Keepa 固有値の列名が1つでも出たら、ASIN 件数に関わらずブロック**にしてください（列名が出る＝行データである、が実務上ほぼ成立します）。

### 6-3. pre-commit フック用 検知語リスト（IT タカシへそのまま渡せます）

**【レベル1：1件でもヒットしたら commit 中止】— Keepa 固有の加工値の列名**

```
月間ドロップ数
ドロップ数
過去最安値
365日最安
価格履歴
月間販売数
想定月販
monthly_sales
monthlySold
monthly_sold
monthly_sold_real
sum_monthly
msales
drop_count
dropsN
実セラー数
rival_sellers
消化月数
損益分岐仕入れ値
仕入れ掛け率上限
```

**【レベル2：ユニーク ASIN が20件以上で commit 中止】— スナップショット値の列名**

```
正規表現: B0[0-9A-Z]{8}
新品オファー数
offer_count
offerCount
セラー名一覧
buybox
buyBoxPrice
sales_rank
salesRank
amazon_price
新品最安値
```

**【レベル3：常にブロック】— 認証情報・API 生レスポンス**

```
api.keepa.com
KEEPA_KEY
KEEPA_API_KEY
accesskey=
"csv":[[      ← Keepa API の生 JSON（価格履歴配列）そのもの
```

**【NETSEA 側（E 判定から継続。統合してください）】**

```
netsea.jp/shop/
卸値
仕入れ先:
supplierData
```

**設計上の注意（これを外すとフックが効きません）**

- **`.claude/scripts/github-sync.sh` は `git add -A` → `git commit` を呼ぶ**ので、pre-commit フックは**自動同期にも効きます**。ここが最大の要点です。
- 一方、**フックは `.git/hooks/` に置かれ Git 追跡されません**。worktree やクラウド環境では消えます。**`core.hooksPath` をリポ内ディレクトリに向けるか、`github-sync.sh` 冒頭で明示的に検査を呼ぶ**二重化を推奨します。
- **バイパス（`--no-verify`）は禁止**とし、必要な場合は理由をチケットに残す運用に。
- **既存の追跡済みファイルはフックでは止まりません**（ステージに乗らないため）。§5 の是正とは別物です。

### 6-4. 再発防止の本丸（E 判定から継続）

`deliverables/<ticket_id>/.gitignore` の冒頭を `*` にし、追跡したいものだけ `!ファイル名` で明示する**ホワイトリスト運用**。現行は「既定＝載せる／例外＝除外を書く」で、**書き忘れが危険側に倒れます**。反転させれば安全側に倒れます。1行で済みます。

---

## 出典一覧（すべて 2026-09-06 取得）

| 文書・事実 | 出典 |
|---|---|
| Keepa Price Data API T&C（Version of July 28, 2026・全20条） | https://keepa.com/cdn/termsAPI.txt |
| Keepa Subscriptions T&C（Version of August 22, 2026） | https://keepa.com/cdn/termsSubscriptions.txt |
| ドイツ著作権法 §87a–87e（データベース製作者の権利・英訳） | https://www.gesetze-im-internet.de/englisch_urhg/englisch_urhg.html |
| 日本の著作権法12条の2（創作性あるデータベースのみ保護／sui generis 権は無い） | https://laws.e-gov.go.jp/document?lawid=345AC0000000048 （旧 `elaws.e-gov.go.jp` は 301 で同URLへ転送・実測） |
| リポジトリの公開状態・fork/star 数 | `gh repo view --json visibility,forkCount,stargazerCount` → `PUBLIC` / `0` / `0` |
| GitHub Pages 未使用 | `gh api repos/Yukinori1018/ai-company-amazon_buppan/pages` → **404** |
| 追跡ファイル全走査・ユニーク ASIN 19,598 件 | `git ls-files -z \| xargs -0 grep -ahoE 'B0[0-9A-Z]{8}' \| sort -u \| wc -l` |
| 各ファイルの `origin/main` 収載・公開開始日 | `git cat-file -e origin/main:<path>` ／ `git log origin/main --diff-filter=A` |
| 02 に ASIN・Keepa 固有値が無いこと | `grep -aoE 'B0[0-9A-Z]{8}'` → 0件、`月間販売数`/`出品者数`/`BSR` → 各0件 |
| 先例（卸価格227行・HEAD 削除／履歴残置） | コミット `f450b01`（2026-08-31 / T-20260831-006） |
| 自動同期の分岐時挙動 | `.claude/scripts/github-sync.sh` 冒頭コメント |
| 適用契約の未確認事項（Pro のオマケ API か独立 API プランか） | `workspace/output/deliverables/T-20260824-001/legal-review-keepa-mcp.md` §9-① |
