# SellerSprite 法務リスク評価書

> 作成: 2026-05-20 ／ 法務エージェント **ハルオ**
> チケット: T-20260520-003（ツール導入の法務確認）
> 評価対象: SellerSprite（セラースプライト）— 中国・深圳発 Amazon リサーチ SaaS、月額約 9,800 円（30%OFF クーポン適用後）
> 評価者立場: 当社（社長＝副業初心者・Amazon物販事業の立ち上げ期）の法務エージェントとして、独立評価

---

## 0. 評価の前提と限界（最初に明示します）

法務として、結論を出す前に **証拠の限界** を明示しておきます。

1. 公式の利用規約（`https://www.sellersprite.com/en/help/terms`）およびプライバシーポリシー（`https://www.sellersprite.com/en/help/privacy-policy`）への WebFetch による直接アクセスは、**いずれも HTTP 403 Forbidden** で阻止されました（運営側の bot ブロック）。
2. したがって本評価は、**検索エンジン経由で抽出できた条項断片**、**業界二次情報**、**関連法令・Amazon 公式規約の原典**、および **tool-profiles.md（社内一次資料）** を根拠としています。
3. 「規約を一読者として直接通読できていない」という状態は、法務観点では **それ自体が一つのリスク**（重要条項の見落とし可能性）です。本書の「防御策」セクションで、**契約前に必ず通読すべき**旨を条件化しています。

以上を前提に、明文主義（書かれていることがすべて）の姿勢で評価します。

---

## 1. 結論（最終判断）

### **条件付き可（Conditional GO）**

**ただし、§4 に列挙する 5 つの防御策をすべて満たすこと**、および **段階導入（tool-profiles.md の軸 B、Step 3）を厳守すること** を条件とします。

理由を端的に述べます。

- SellerSprite の利用行為そのものは、**国内法上の違法行為に直結する性質のものではありません**（リサーチ SaaS の購読契約に過ぎず、社長が能動的にスクレイピングを行う構造ではない）。
- しかし、**中国法準拠の可能性が高い** こと、**Amazon 利用規約との抵触リスクが SellerSprite 側の挙動次第で発生し得る** こと、**個人情報の越境移転** が事実上不可避であること、の 3 点で、**無条件の "可" は出せません**。
- 「グレーは原則 NO」が法務の鉄則ですが、本件は **防御策を講じれば管理可能なグレー** と判定しました。**ただし、防御策の一つでも欠ければ、判定は "不可" に転落します**。

---

## 2. リスク一覧（発生確率 × 影響度 × 不可逆性の 3 軸評価）

### 凡例

- **発生確率**: 高 / 中 / 低
- **影響度**: 高（事業継続に関わる）／ 中（金銭損害・是正可能）／ 低（軽微）
- **不可逆性**: 高（取り返しがつかない）／ 中（時間と費用で回復）／ 低（即時回復可）

---

### 【高リスク】R-1: Amazon アカウント停止リスク（出品アカウント）

| 軸 | 評価 |
|---|---|
| 発生確率 | **低〜中**（SellerSprite ユーザー個別の責に帰さない場合が多いが、ゼロではない） |
| 影響度 | **高**（出品アカウント停止は事業の即死） |
| 不可逆性 | **高**（一度停止されると復活困難。出品履歴・レビューも失う） |

**根拠（一次・二次情報）:**

Amazon の利用規約（Conditions of Use）には、次の条項が明記されています。

> "any collection and use of any product listings, descriptions, or prices; any derivative use of any Amazon Service or its contents; any downloading, copying, or other use of account information for the benefit of any third party; or any use of data mining, robots, or similar data gathering and extraction tools" を禁止する。
> （[Amazon Conditions of Use](https://www.amazon.com/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM)）

> "using any automated process or technology to access, acquire, copy, or monitor any part of the Amazon Website" を禁止する。

SellerSprite は商品リサーチ・キーワード逆引きのため、**Amazon の公開ページから ASIN 毎の販売数推定・キーワード推定値を継続的に収集している** ことが、その機能性から強く推認されます（業界二次情報でも自動データ収集を前提とした分析が言及されている：[ScrapeHero](https://www.scrapehero.com/is-scraping-amazon-legal/)、[ScraperAPI](https://www.scraperapi.com/web-scraping/amazon/is-it-legal/)）。

**論点の核心:**

- スクレイピングをしているのは **SellerSprite 側であり、ユーザー（社長）ではない**。よって、社長個人が Amazon 利用規約に直接違反する構造ではありません。
- しかし、**ユーザーが SellerSprite で取得した推定値・キーワードリストを自社の出品最適化に流用** した時点で、Amazon は次のように主張する余地が残ります：「当社の禁止する自動データ収集の成果を第三者経由で受領・利用した」と。
- 現在までに、SellerSprite ユーザーであることを理由に Amazon が一斉アカウント停止を行った **公開事例は確認できませんでした**。しかし、**Amazon は通知なくポリシーを強化する権利を留保** しています。

**判定:** ゼロではない。**特に出品アカウントが事業の生命線である立ち上げ期** には、不可逆性の観点で警戒が必要。

---

### 【高リスク】R-2: 準拠法・裁判管轄が中国法・中国管轄である蓋然性

| 軸 | 評価 |
|---|---|
| 発生確率 | **高**（中国・蘭州／深圳系の運営である事実から、ほぼ確実に中国準拠法・中国管轄） |
| 影響度 | **中**（紛争時の救済手段が事実上塞がれる） |
| 不可逆性 | **中**（個別案件レベルでは諦め＝損切りで対応可能） |

**根拠:**

- tool-profiles.md §2 において「中国・深圳発」「中国発 SaaS」と明記。
- 補足検索で SellerSprite の本社所在地は **中国・蘭州**（[Tracxn 公開情報](https://tracxn.com/d/companies/sellersprite/__mtnEu21tEPbmlQHwfFJGRHlxrX2aVreqvsEt0Zu_y38)）と確認。
- 中国 SaaS の標準的な利用規約は、**中華人民共和国法を準拠法とし、運営所在地の人民法院または北京/上海/深圳の仲裁委員会を専属管轄** とするのが慣行（[Lexology: Dispute resolution and governing law clauses for China-related commercial contracts](https://www.lexology.com/library/detail.aspx?g=07a24805-4b96-4eaf-86c4-bb4e943ec37b)）。
- **公式利用規約の直接取得は 403 で阻止されたため、条文の特定はできていません**。本評価書では「中国法準拠・中国管轄の蓋然性が高い」と推定して進めますが、契約前に **必ず通読し、§9 または同等の条項を確認する必要があります**（防御策 §4-D に組み込み）。

**法務的な意味:**

- 日本の消費者契約法 11 条・12 条による保護は、外国準拠法を選択した場合 **原則として日本ユーザーの保護条項が劣後** する（消費者契約法 12 条の特則あり。ただし B2B 契約では消費者保護法理は適用されない）。
- 社長が **個人事業主／法人として SaaS を購読する場合は B2B 扱い** となり、消費者保護法理の援用は困難。
- 紛争発生時、深圳または蘭州の裁判所に出向く、または中国仲裁委員会で手続を行う必要がある。**日本人個人が事実上アクセスできる救済ルートではありません**。

**判定:** 紛争時の救済は事実上ゼロと想定すべき。**故に、損害が「諦められる金額」を超えないように利用を設計する** ことが防御策となる。

---

### 【中リスク】R-3: 個人情報の越境移転（中国 PIPL と日本 APPI）

| 軸 | 評価 |
|---|---|
| 発生確率 | **高**（中国運営である以上、データは中国本土に流れる蓋然性が高い） |
| 影響度 | **中**（社長個人の個人情報＋クレジットカード情報が中国管轄下に置かれる） |
| 不可逆性 | **中**（一度送ったデータは取り戻せないが、被害が現実化するかは別問題） |

**根拠（プライバシーポリシー断片より）:**

検索エンジン経由で取得できた SellerSprite プライバシーポリシーの該当断片は次のとおりです。

> "SellerSprite discloses potentially personally-identifying and personally-identifying information only to those of its employees, contractors and affiliated organizations that (i) need to know that information in order to process it on SellerSprite's behalf or to provide services available at SellerSprite's website, and (ii) that have agreed not to disclose it to others."
> （[SellerSprite Privacy Policy](https://www.sellersprite.com/en/help/privacy-policy) 抜粋）

> "SellerSprite discloses personally-identifying information to employees, contractors, and affiliated organizations that need it, and some of those may be located outside users' home countries; by using SellerSprite's websites, users consent to the transfer of such information to them."

**論点:**

1. **収集される情報**: 氏名、メールアドレス、住所、クレジットカード情報、利用履歴（検索した ASIN・キーワード）。
2. **越境移転の同意**: 「サイトを利用すること自体が越境移転への同意とみなす」という **包括同意モデル**。日本の個人情報保護法（APPI）28 条の「外国にある第三者への提供」では、原則として **本人同意の取得＋移転先の保護水準に関する情報提供** が必要ですが、本件は **社長が事業者として自らの個人情報を提供** する構造のため、APPI の規律対象外（事業者の自己情報）です。
3. **中国 PIPL（個人情報保護法）の適用**: データが中国本土に格納される場合、中国当局による合法的なデータアクセス要求の対象となります（[DLA Piper: Data protection laws in China](https://www.dlapiperdataprotection.com/index.html?c=CN&t=law)、[TrustArc: China PIPL](https://trustarc.com/regulations/china-pipl/)）。中国国家安全法・データ安全法上、当局は事業者に対しデータ提出を命じる権限を有します。
4. **GDPR / APPI / CCPA への準拠声明**: 検索結果からは、SellerSprite がこれらの法域への明示的な準拠を約束する条項は **確認できませんでした**。

**判定:** 社長個人の氏名・住所・カード情報が中国管轄下に流れる前提で運用すべき。**カード情報は使い捨て可能なバーチャルカードを使う等で被害範囲を限定** することが防御策。

---

### 【中リスク】R-4: 検索行動・調査内容の競合への漏洩可能性

| 軸 | 評価 |
|---|---|
| 発生確率 | **低〜中**（明確な事例はないが、構造上はあり得る） |
| 影響度 | **中**（攻めるカテゴリ・狙う SKU が競合に知られると先回り出品される） |
| 不可逆性 | **中**（情報優位は失われるが、別 SKU に切り替え可能） |

**根拠と論点:**

- SellerSprite は **「世界 10 万ユーザー以上」を公称**（[SellerSprite blog: Top 10 Tools](https://www.sellersprite.com/en/blog/Top-10-Amazon-Seller-Tools-in-2026-From-Product-Research-to-Price-Tracking)）。同じカテゴリを狙う **中国本土の輸出セラー** も多数利用しているとみるべき。
- 利用規約上、**「ユーザーの検索クエリは秘匿される」「他ユーザーに開示しない」旨の明示条項** は、検索結果からは確認できませんでした。
- SellerSprite は「商品リサーチ画面」で **集計済みのトレンドキーワード** を全ユーザーに提供しています。これが個別ユーザーの検索行動からの集計データであるか、Amazon 側の公開データのみからの集計であるかは **不透明**。
- 集計結果として **「日本セラーが直近検索した急上昇ワード」** が他ユーザーに見える設計であれば、社長の調査行動が間接的に競合に伝わるリスクがあります。

**判定:** 構造的なリスクとして認識すべき。**特に "本命 SKU" の検索は最後まで SellerSprite に投げない** という運用ルールが有効。Keepa／公式ツールで確証した後、SellerSprite では周辺リサーチに留めるのが安全。

---

### 【中リスク】R-5: 規約変更・サービス停止・撤退時のデータ消去不全

| 軸 | 評価 |
|---|---|
| 発生確率 | **中**（中国 SaaS は地政学・規制環境により予測困難な変動がある） |
| 影響度 | **中**（依存度が高いほど影響大） |
| 不可逆性 | **中**（代替ツール Helium 10 等への移行は可能だが学習コストあり） |

**根拠:**

- 中国当局による国外サービス向けの規制強化（データ越境規制、サイバーセキュリティ法）の前例多数（[ICLG: Digital Business Laws China 2025-2026](https://iclg.com/practice-areas/digital-business-laws-and-regulations/china)）。
- アカウント削除手続きについては、**専用ページの存在を確認**（`https://www.sellersprite.com/en/help/account-deletion-policy`）。これ自体は加点要素ですが、**実際の削除完全性（バックアップからの削除を含むか）は通読確認が必要**。
- 返金規定: 検索結果より、**新規ユーザーは 7 日間の返金保証**、**それ以降は未消化分の返金可能**（要サポート連絡）。退会自体は「次の請求サイクル以降課金されない」シンプルな仕組み（[SellerSprite Refund Policy](https://www.sellersprite.com/en/help/sellersprite-refund-policy)）。**この点は健全な設計**と評価します。

**判定:** 撤退ルートは存在する。ただし、依存度を上げすぎない運用が前提。

---

### 【低リスク】R-6: 決済・送金経路の安全性

| 軸 | 評価 |
|---|---|
| 発生確率 | **低**（主要決済代行（Stripe／PayPal 等）経由であれば標準的） |
| 影響度 | **低〜中**（カード情報漏洩時の被害） |
| 不可逆性 | **低**（カード再発行で対応可能） |

**根拠と論点:**

- SellerSprite の決済処理基盤の明示は検索結果からは取得できませんでしたが、主要中国系 SaaS は **Stripe または PayPal、または中国系ゲートウェイ（Alipay / WeChat Pay）** を併用するのが標準。
- 中国国内銀行への直接振込を要求する設計であれば **危険信号**。決済画面でこの点を必ず確認する必要があります。
- カード情報の保管が SellerSprite 側ではなく **PCI-DSS 準拠の決済代行側に委ねられている設計** であれば、リスクは限定的。

**判定:** **決済画面で「決済代行業者名（Stripe / PayPal 等）」が表示されているかを必ず確認**。中国系決済 only であれば見送り。

---

### 【低リスク】R-7: 個人開発／個人事業のリスク（運営継続性）

| 軸 | 評価 |
|---|---|
| 発生確率 | **低**（法人運営、ユーザー 10 万超の規模） |
| 影響度 | **低**（突然消滅した場合のみ） |
| 不可逆性 | **低**（代替ツールあり） |

**根拠:** SellerSprite は法人運営、複数言語対応、Amazon 公認ではないが業界での認知度は高い（[Helium 10 公式比較](https://www.helium10.com/)、二次情報多数）。アマサーチ等の個人開発ツールに比べると **継続性リスクは相対的に低い**。

---

## 3. リスクサマリ表

| ID | リスク | 発生確率 | 影響度 | 不可逆性 | ランク |
|---|---|---|---|---|---|
| R-1 | Amazon 出品アカウント停止 | 低〜中 | 高 | 高 | **高** |
| R-2 | 中国法準拠・中国管轄 | 高 | 中 | 中 | **高** |
| R-3 | 個人情報の越境移転（中国 PIPL） | 高 | 中 | 中 | **中** |
| R-4 | 検索行動の競合漏洩 | 低〜中 | 中 | 中 | **中** |
| R-5 | 規約変更・サービス停止 | 中 | 中 | 中 | **中** |
| R-6 | 決済経路 | 低 | 低〜中 | 低 | **低** |
| R-7 | 運営継続性 | 低 | 低 | 低 | **低** |

---

## 4. 防御策（条件付き可とするための必須条件）

以下 **A〜E をすべて満たすこと** を、SellerSprite 利用の条件とします。**一つでも欠ければ、本件の判定は "不可" に転落** します。

### A. 出品アカウントとの完全分離（R-1 対策）

1. SellerSprite の**ログイン用メールアドレス**を、Amazon 出品アカウントのメールアドレス・登録氏名と**完全に切り離す**。専用の Gmail アドレスを作成する。
2. SellerSprite に **Amazon 出品アカウントの API キー（SP-API 認証）を絶対に渡さない**。SellerSprite が「Amazon アカウント連携で機能拡張」を促してきても、Decline する。
3. SellerSprite で取得した推定値・キーワードリストは **参考情報** に留め、**最終的な仕入れ判断・出品キーワード決定** には Keepa／Amazon 公式ツール／自身の検証で裏付ける。これにより、万一 Amazon が SellerSprite 起点のデータ流用を問題視した場合でも、社長の出品行為が **独立した裏付けに基づく**ことを主張可能。

### B. 段階導入・依存度コントロール（R-1, R-5 対策）

1. tool-profiles.md の **軸 B（段階導入）の Step 3 まで進んでから** SellerSprite を導入する。Step 1（無料）→ Step 2（Keepa Pro）→ Step 3（SellerSprite）の順を厳守。
2. **月額契約のみ**（年払いは原則禁止）。中国 SaaS への年払いは、サービス停止・規約激変時の回収可能性が低い。
3. **3 ヶ月利用ごとに ROI レビュー**。月額 9,800 円 × 3 ヶ月 = 29,400 円の投資に対し、SellerSprite 由来の SKU が利益貢献していない場合は解約。

### C. 個人情報・決済の最小化（R-3, R-6 対策）

1. **使い捨て可能なバーチャルカード**（Kyash、バンドルカード、Revolut 等）で決済する。物理カード・主要カードは登録しない。
2. **登録氏名は必須項目のみ**。任意項目（電話番号、住所詳細、生年月日）は空欄または最小化。
3. **決済画面で決済代行業者名を確認**。Stripe／PayPal であれば許容。中国系決済 only（Alipay／WeChat Pay／中国国内銀行振込）であれば **即時中止**。

### D. 規約・プライバシーポリシーの通読確認（契約前必須）

1. 申込前に、以下のページを社長自身が（または法務エージェントが代行で）**通読し、特定の条項を確認する**。
   - 利用規約: `https://www.sellersprite.com/en/help/terms`
   - プライバシーポリシー: `https://www.sellersprite.com/en/help/privacy-policy`
   - 返金規定: `https://www.sellersprite.com/en/help/sellersprite-refund-policy`
   - アカウント削除規定: `https://www.sellersprite.com/en/help/account-deletion-policy`
2. **確認すべき条項チェックリスト**:
   - [ ] 準拠法（Governing Law）— 中国法か否か。中国法でない場合（香港法・シンガポール法等）は加点。
   - [ ] 裁判管轄／仲裁地（Jurisdiction / Arbitration）— 中国本土の人民法院か、第三国の仲裁機関か。
   - [ ] データ保管場所（Server Location）— 中国本土／香港／米国いずれか。
   - [ ] 個人情報の越境移転条項 — 包括同意か、明示同意か。
   - [ ] サービス停止・規約変更時の通知期間 — 30 日以上の通知があるか。
   - [ ] データポータビリティ・削除権 — 完全削除を保証するか。
   - [ ] 損害賠償の上限 — 月額の数倍に制限されているか（通常そうである）。
3. **通読結果を法務（ハルオ）に再フィードバック** し、判定を最終化する。本書はあくまで「直接通読できない状態での暫定評価」。

### E. 撤退オペレーションの事前準備（R-5 対策）

1. **解約手順を導入前にメモ化**。`account profile → cancel` または `support@sellersprite.com` への連絡（[SellerSprite Refund Policy](https://www.sellersprite.com/en/help/sellersprite-refund-policy)）。
2. **代替ツール（Helium 10 / Jungle Scout）への移行ルート** を §5 で予め整理。SellerSprite が突然使用不能になっても、72 時間以内に代替に切り替えられる状態を維持。
3. **クレジットカード明細を月次で確認**し、解約後の二重請求がないかチェック。

---

## 5. 代替案の評価（Helium 10 / Jungle Scout との法務面比較）

法務の核心は「**準拠法・データ管轄・運営の透明性**」の 3 点です。これを軸に比較します。

| 項目 | SellerSprite | Helium 10 | Jungle Scout |
|---|---|---|---|
| 運営国 | 中国（蘭州） | 米国（カリフォルニア州 Irvine） | 米国（テキサス州 Austin） |
| 準拠法（推定） | 中国法 | カリフォルニア州法 | テキサス州法 |
| 裁判管轄（推定） | 中国本土 | 米国連邦／州裁判所 | 米国連邦／州裁判所 |
| データ保管 | 中国本土が蓋然性高 | 米国（AWS US-East 等） | 米国（AWS） |
| 主要法域 | 中国 PIPL（事業者は中国当局のデータ提出要求に応じる義務） | CCPA／GDPR（明示準拠声明あり） | CCPA／GDPR（明示準拠声明あり） |
| Amazon 公式パートナー認定 | なし | Amazon Marketplace Appstore に複数アプリ登録あり | Amazon Marketplace Appstore に登録あり |
| 日本市場サポート | 日本語 UI／日本語サポートあり | 一部日本語対応 | 限定的 |
| 月額（為替により変動） | 約 9,800 円（クーポン後） | $39〜（≒ 6,000 円〜）／上位プラン高額 | $49〜（≒ 7,500 円〜） |
| **法務総合評価** | **要慎重対応** | **相対的に低リスク** | **相対的に低リスク** |

### 法務観点の優位性比較

#### Helium 10 / Jungle Scout の優位点
- **米国法準拠** → 日本ユーザーが救済を求める場合、第三国法廷（米国）の方が、中国法廷より相対的にアクセシブル。
- **Amazon の公式アプリストア（Amazon Marketplace Appstore）に複数アプリが登録**されており、Amazon との関係性が公式に明示されている → **R-1（Amazon アカウント停止）のリスクが構造的に低い**。
- **GDPR／CCPA 準拠を明示**しており、個人情報保護の対外的なコミットメントが文書化されている。
- データ保管が米国 → 中国当局のデータ提出命令の直接対象外。

#### SellerSprite の優位点
- **日本市場・日本セラーへの最適化が深い**（日本 ASIN の網羅性、日本語キーワードリサーチ精度）。
- **コストパフォーマンスが高い**（特に 30%OFF クーポン適用後）。
- **Chrome 拡張で日本 Amazon に即対応**。

### ハルオの所見

**純粋に法務面のみを評価すれば、Helium 10 または Jungle Scout を強く推奨します**。理由は、

1. 米国法準拠・米国管轄であり、日本ユーザーが**救済を求めにくい度合いが中国管轄より低い**。
2. Amazon の公式アプリストアに登録があるため、Amazon 利用規約抵触（R-1）の解釈が**構造的に明確**である。
3. GDPR／CCPA への明示準拠により、個人情報の取り扱いに関する**契約上の保護水準が高い**。

**ただし、**事業のオペレーション面では SellerSprite の日本市場最適化が大きな価値であることは認めます。

**最終的な判断は「法務 1 票 vs 事業 1 票」のトレードオフ**。本書は法務票として「Helium 10 推奨、SellerSprite 採用なら防御策必須」を投じます。

---

## 6. 秘書（カズヨ）への申し送り

社長承認を取る前に、以下の **追加情報** を確認・整理してください。

### 6.1. 社長に確認すべき事項（A/B/C 提示形式）

CLAUDE.md §4.1 「金銭が動く（新規サブスク契約）」に該当するため、本件は **承認必須案件** です。社長判断を仰ぐ際、以下の選択肢を提示することを推奨します。

- **A. SellerSprite を §4 の防御策付きで導入**（事業最適 × 法務条件付き OK）
- **B. Helium 10 または Jungle Scout に切り替える**（法務最適 × 日本市場最適化はやや劣後）
- **C. SellerSprite は導入せず、Keepa＋公式無料ツールで Step 2 まで様子を見る**（リスクゼロ × 横展開フェーズでの調査効率は犠牲）

**法務推奨: B**（Helium 10 への乗り換え）。
**事業推奨（tool-profiles.md より）: A の段階導入版**。
**法務として許容可能な最低ライン: A（防御策 §4 を全部満たす）**。

### 6.2. 契約前に必ず実施すべき作業（DEFCON）

1. **利用規約・プライバシーポリシーの通読**（§4-D）— これが完了するまで、判定は **暫定** であり、最終承認の根拠とすべきではありません。
2. **法務（ハルオ）への再相談** — 通読結果を踏まえて、本評価書を更新します。
3. **決済画面のスクリーンショット取得** — 決済代行業者の特定（§4-C）。

### 6.3. 社長プロファイルへの反映候補

社長は副業初心者であり、「中国 SaaS のリスク」への感覚が定着していない可能性があります。**本件をきっかけに、以下を社長プロファイルに反映** することを提案します（庶務エージェント経由で）。

- 「外国 SaaS 導入時は、原則として法務エージェントへ事前確認を依頼する」
- 「年払いは原則禁止、月額のみで開始する」
- 「決済は使い捨て可能なバーチャルカードを使う」

これらを「定型ルール」として固定化することで、今後の判断コストが下がります。

### 6.4. チケットの状態遷移

本書の納品により、T-20260520-003 のうち **法務確認パート** は完了しました。秘書側で：

- 本書を `~/Documents/AI Company Outputs/Amazon物販事業/T-20260520-003/` に最終納品物として配置
- 社長承認待ちのため、チケット親本体は `waiting/` ステータスへ移動（§4.1 該当）
- Notion カンバンへ同期

を実施してください。

---

## 7. 結語（ハルオより）

社長、断言しておきます。

SellerSprite は、**「使える」道具です。日本市場最適化という事業価値も認めます**。しかし、**「使ってよい」道具であるかは、防御策を講じるかどうかで決まります**。

中国法準拠・中国管轄・中国本土データ保管は、**平時は何の問題も起こしません**。問題は、**有事に何が起こるか** です。アカウントが突然停止された、データが意図せず開示された、規約が一晩で激変した——これらの事態が現実化した時、**「日本から救済を求めるルートが事実上ない」** ことが、本件の最大のリスクです。

不可逆な事態は、事前に防ぐべきものです。

**防御策 §4 のすべてを満たし、段階導入を厳守すること**。これを条件として、本件は **可** とします。

以上。

— 法務エージェント **ハルオ**

---

## 8. 参照文献・一次情報リスト

- [Amazon Conditions of Use](https://www.amazon.com/gp/help/customer/display.html?nodeId=GLSBYFE9MGKKQXXM)
- [SellerSprite Privacy Policy（直接アクセスは 403、検索経由抜粋を引用）](https://www.sellersprite.com/en/help/privacy-policy)
- [SellerSprite Refund Policy（同上）](https://www.sellersprite.com/en/help/sellersprite-refund-policy)
- [SellerSprite Account Deletion Policy（同上）](https://www.sellersprite.com/en/help/account-deletion-policy)
- [Lexology: Dispute resolution and governing law clauses for China-related commercial contracts](https://www.lexology.com/library/detail.aspx?g=07a24805-4b96-4eaf-86c4-bb4e943ec37b)
- [DLA Piper: Data protection laws in China](https://www.dlapiperdataprotection.com/index.html?c=CN&t=law)
- [TrustArc: China PIPL](https://trustarc.com/regulations/china-pipl/)
- [ICLG: Digital Business Laws China 2025-2026](https://iclg.com/practice-areas/digital-business-laws-and-regulations/china)
- [ScrapeHero: Is Scraping Amazon Legal?](https://www.scrapehero.com/is-scraping-amazon-legal/)
- [ScraperAPI: Is Scraping Amazon Legal?](https://www.scraperapi.com/web-scraping/amazon/is-it-legal/)
- [Tracxn: SellerSprite Company Profile](https://tracxn.com/d/companies/sellersprite/__mtnEu21tEPbmlQHwfFJGRHlxrX2aVreqvsEt0Zu_y38)
- [Helium 10 公式](https://www.helium10.com/)
- 社内資料: `/home/user/ai-company-amazon_buppan/workspace/output/agent_output/T-20260520-003/tool-profiles.md`
