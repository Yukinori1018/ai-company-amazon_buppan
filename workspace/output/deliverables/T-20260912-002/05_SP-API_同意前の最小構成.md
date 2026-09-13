# SP-API 同意前の最小構成（設計と雛形）

IT タカシ／2026-09-13／T-20260912-002（親）

対象：統合報告 論点⑤（登録だけ1周目・実装は成立3社以上で）と論点⑪（同意前に最小構成を用意してよいか）。
本書は**設計と雛形まで**です。開発者登録・規約同意・API キー取得・`.gitignore` 変更・DB 作成は**していません**（§4.1／社長判断後）。

法務判定（ハルオ 02 §1-7）の前提を引き継ぎます：DPP §1 は規約同意の時点から全部かかる。PII 不問。SP-API 由来の情報は集計値でも PUBLIC リポに置けない（AUP 4.6）。

---

## 0. 結論

| 項目 | 数字 |
|---|---|
| DPP §1 の要件 | 18 項目（1.1.1〜1.8 ＋ §3 記録保持） |
| うち今の Mac で既に満たす | 6 |
| うち本書（文書・手順）で満たす | 8 |
| うち**社長の一手が要る**（設定変更・メール送信） | 3（ファイアウォール ON／ログイン失敗ロック／インシデント時のメール送信） |
| うち未達で実装が要る | 1（鍵のローテーション記録＝雛形に含めた） |
| 実装工数（社長判断「実装 Go」後） | 3〜4 人日。審査待ち（数日〜数週）は別 |
| 登録で社長がクリックする回数 | 4 手（§4 参照）。うち §4.1 は 3 手 |
| 費用 | 0 円 |

推奨：論点⑪は「可」で進めて損がありません。0 円・社内作業・不可逆な操作なし。ただし本書 §1 の「社長の一手」2 件（ファイアウォール・ロック）は**規約同意より前**に済ませる順番です。

---

## 1. DPP §1 の要件 → 当社の環境への当てはめ

出典：DPP 本文（2026-09-13 取得 `sellercentral.amazon.com/mws/static/policy?documentType=DPP`）。当社の環境は 2026-09-13 に読み取りコマンドで実測（設定は変えていない）。

状態の凡例：済＝実測で満たす／文書＝本書に書いて満たす／**一手**＝社長の操作が要る／実装＝コードで満たす（雛形あり）

| 条項 | 要件（要旨） | 当社の実装（最小） | 実測・根拠 | 状態 |
|---|---|---|---|---|
| 1.1.1 ネットワーク保護 | ファイアウォール・ACL・ID ベースのアクセス制御 | Mac 1 台・ローカルのみ・待ち受けサーバなし。macOS ファイアウォールを ON | `socketfilterfw --getglobalstate` → **disabled (State=0)** | **一手**（システム設定 → ネットワーク → ファイアウォール ON） |
| 1.1.2 端末保護 | 端末保護ソフトの無効化・改変を防ぐ | macOS 標準（XProtect・Gatekeeper・SIP）。管理者パスワード無しに無効化できない | `csrutil status` → enabled | 済 |
| 1.1.3 文書化 | ネットワーク・端末保護の文書と構成図 | 本書 §2 の構成図（1 台・1 人・ローカル） | — | 文書 |
| 1.2.1 アクセス管理プロセス | 申請・承認・付与・棚卸し・剥奪の手順を文書化 | Approved User は社長 1 名。追加は本書改訂＋秘書チケットで承認 | — | 文書 |
| 1.2.2 ロックアウト | 連続 10 回以内の失敗でロック | macOS ローカルアカウントにロック方針を設定 | `pwpolicy -getaccountpolicies` → **maxFailedLoginAttempts 未設定** | **一手**（§4-4 のコマンド。社長のみ実行可） |
| 1.2.3 退職・役割変更 24 時間以内に剥奪 | — | 1 名運用。該当時＝Keychain の項目削除＋Seller Central で認可取消（§7-3） | — | 文書 |
| 1.2.4 Approved User のみ・年 1 回の教育 | — | 社長 1 名。年 1 回本書 §1・§7 を読み、日付を §8 の表に記入 | — | 文書 |
| 1.3 最小権限 | 必要最小限のアクセス | Roles は Pricing・Product Listing の 2 つだけ申請（PII 系 Restricted は申請しない）。DB を読むのは `spapi_min.py` だけ | 3 エンドポイントに必要な Roles（確度中・§4-3） | 文書＋実装 |
| 1.4.1 MFA・12 文字以上 | 全ユーザーアカウントに MFA、パスワード 12 文字以上 | Amazon セラー：電話 2FA 済み（memory `project_amazon_login_entrypoint`）。Mac ログイン：**12 文字以上かは社長確認** | 2FA 済みは既知。Mac は未確認 | 済（Amazon）／社長確認（Mac） |
| 1.4.2 API 資格情報の保存時暗号化・12 か月ごとローテ | — | client_id／client_secret／refresh_token は **macOS Keychain**（AES-256・FileVault 二重）。平文ファイル・`.env` に置かない。ローテは年 1 回、§8 の表で管理 | FileVault → **On**。Keychain 方式は Keepa MCP で既定化済み（memory `knowledge_mcp_secret_storage_design`） | 済（保管）／実装（ローテ記録） |
| 1.5 通信の暗号化 | TLS 1.2 以上 | 雛形で `ssl.TLSVersion.TLSv1_2` を最低値に固定 | Python 3.9.6／LibreSSL 2.8.3（TLS 1.2 対応） | 実装 |
| 1.6.1 リスク評価（年 1 回・経営層レビュー） | — | 本書 §6 の 1 枚。年 1 回社長が見直す | — | 文書 |
| 1.6.2 インシデント対応計画（半年ごと見直し） | — | 本書 §7 の runbook。半年ごとに §8 へ日付 | — | 文書 |
| 1.6.3 24 時間以内に security@amazon.com へ通知 | — | 秘書が §7-2 の雛形で下書き → **社長が送信**（外部発信＝§4.1） | — | **一手**（発生時のみ） |
| 1.6.4 調査と記録 | — | §7-4 の記録票 | — | 文書 |
| 1.6.5 IMPOC（連絡窓口） | — | 社長。登録フォームの Contact と同じ | — | 文書 |
| 1.7 30 日以内の削除 | Amazon の要請・契約終了から 30 日以内 | `spapi_min.py purge`（DB ファイルと WAL を削除）。**削除は §4.1**なので、要請を受けたら秘書が即日 waiting に出し 30 日内に承認を得る | — | 実装＋文書 |
| 1.8 出所の識別 | 専用 DB か出所タグ | **専用 SQLite**（他データと混ぜない）＋全行に `source='SP-API'`・`fetched_at` | — | 実装 |
| §3 記録保持 | 契約中＋終了後 12 か月 | アクセスログを DB 内 `access_log` に保持。データ本体は 18 か月で自動失効（公式ガイダンスの Non-PII 上限） | — | 実装 |

Mac の画面ロックは実測 300 秒（5 分）で、ハルオ判定の「15 分ロック」を満たします（`sysadminctl -screenLock status`）。

DPP §2（PII）は **Restricted Role を申請しない限りかかりません**。当社の 3 エンドポイントに PII はありません。公式の「Key Security Control Guidance」ページにある月次脆弱性スキャン・年次ペネトレーションテスト等は §1・§2 が混ざった一覧で、拘束するのは DPP 本文です。本書は DPP §1 の文言だけを満たします（余分に作らない）。

---

## 2. リポジトリ側の境界

### 2-1. 構成図（1.1.3 用）

```
[社長の Mac 1 台・FileVault On・ローカルユーザー 1 名]
   ├─ macOS Keychain ──── client_id / client_secret / refresh_token（暗号化・リポ外）
   ├─ ~/Library/Application Support/satoy-spapi/spapi.sqlite（専用 DB・リポ外）
   └─ リポ（PUBLIC・30 分ごと自動 push）
        ├─ adapters/spapi_min.py（コードのみ。データ・鍵は含まない）
        └─ deliverables/（可否・件数・当社の決定だけ）
外部通信：api.amazon.com（LWA）・sellingpartnerapi-fe.amazon.com（JP）のみ。TLS 1.2+。待ち受けポートなし。
```

### 2-2. 置き場の原則：**リポの外**

`.gitignore` を信じる設計にしません（PUBLIC・自動 push・`git add -f` 一発で公開。memory `knowledge_public_repo_leak_prevention`）。SP-API 由来のデータはリポの外に置き、`.gitignore` は二重の保険にとどめます。

| 種類 | 置き場 | Git |
|---|---|---|
| 鍵（client_id／secret／refresh_token） | macOS Keychain（service `satoy-spapi`） | 外 |
| 生データ・派生集計・利益計算の中間表 | `~/Library/Application Support/satoy-spapi/spapi.sqlite` | 外 |
| 一時的な作業 CSV | `workspace/output/agent_output/spapi/`（既に ignore 対象） | 除外 |
| コード・本書・手順 | `adapters/spapi_min.py`・`deliverables/` | 追跡 |

### 2-3. deliverables に書いてよいもの／だめなもの

| 書いてよい | 書かない（AUP 4.6「individually labelled or aggregated」） |
|---|---|
| 当社の決定（発注する／しない、自社の出品価格） | NumberOfOffers・BuyBox 価格・最安値（ASIN 単位） |
| 件数（例「候補 27 件中ゲートあり 3 件」） | ASIN ごとの `reasonCode`・承認申請 URL |
| ゲート判定の**可否**（○／×）を ASIN 20 件未満の表に添える（ハルオのしきい値運用に揃える） | 手数料の金額・料率（ASIN 単位・平均とも） |
| 「SP-API で確認済み」という事実 | SP-API 値を使った利益額の一覧表（派生集計） |

利益額の表は SP-API の手数料を使った瞬間に派生物になります。本書は**載せない側**に倒しました。載せたい場合はハルオに「当社の意思決定の結果」として扱えるか確認してください（未判定）。

### 2-4. `.gitignore` 追加行案（**まだ適用しない**。社長判断後に秘書経由で）

```gitignore
# ── SP-API 由来データ（AUP 4.6：集計値も外部開示不可）。正は ~/Library/Application Support/satoy-spapi/ ──
**/spapi*.sqlite
**/spapi*.sqlite-wal
**/spapi*.sqlite-shm
**/spapi_*.csv
**/spapi_*.json
workspace/output/**/spapi/
```

pre-commit（`.githooks/pre-commit`）への追加候補：`Atzr|`・`Atza|`・`amzn1.application-oa2.client.` の後に 20 文字以上続く行を「強い印」として止める（値付きだけ検知＝実装コードは通す）。これも案のみ。

---

## 3. 雛形コード `adapters/spapi_min.py`

実体は同フォルダの [`05_adapters_spapi_min.py`](05_adapters_spapi_min.py)。**実行していません。鍵を要求しません。**`netsea.py` の流儀（docstring 先頭に用途制限・`is_live`／`last_error` で正直に・例外を握らない）に揃えています。

### 3-1. 作るもの／作らないもの

| 作る | 作らない（YAGNI） |
|---|---|
| LWA refresh_token → access_token（1 時間キャッシュ） | 通知 API・Feeds・Reports・注文 |
| `get_item_offers(asin)`・`get_listing_restrictions(asin)`・`get_fees_estimate(asin, price)` の 3 本 | v2022-05-01 `getCompetitiveSummary`（バッチ）。件数が増えたら検討 |
| エンドポイントごとのトークンバケット（0.5／5／1 rps） | 並列・非同期 |
| 専用 SQLite（`offers`・`restrictions`・`fees`・`access_log`・`key_rotation`） | ダッシュボード・UI |
| `purge`（1.7）・`expire`（18 か月）・`rotation-status`（1.4.2） | Web サーバ・外部公開 |
| 鍵は Keychain から `security find-generic-password` で読む | `.env`・環境変数・設定ファイル |

### 3-2. データ表

| 表 | 主キー | 列（抜粋） | 用途 |
|---|---|---|---|
| `offers` | asin, fetched_at | number_of_offers_json, buybox_price, lowest_price, sales_rank, source | 出品者数・カート価格の時点値 |
| `restrictions` | asin, fetched_at | reason_code, approval_url, source | ゲート判定 |
| `fees` | asin, price, is_fba, fetched_at | total_fees, fee_detail_json, source | 手数料の公式値 |
| `access_log` | id | ts, op, asin, http_status, note | §3 記録保持（12 か月以上） |
| `key_rotation` | id | rotated_at, what, by | 1.4.2 の年次ローテ記録 |

### 3-3. 工数（社長判断「実装 Go」後・成立 3 社以上で着手）

| 作業 | 人日 |
|---|---|
| LWA トークン更新＋Keychain 読み出し＋TLS 固定 | 0.5 |
| 3 エンドポイント＋レート制限＋エラーの正直な保存 | 1.0 |
| SQLite スキーマ・purge・expire・access_log | 0.5 |
| CLI＋録画レスポンスでのテスト（本番を叩かない） | 1.0 |
| ローテ手順の実機確認・runbook 検証 | 0.5 |
| 合計 | **3.5（3〜4）** |

---

## 4. 登録手順（社長の一手の分解）

出典：公式「Register as a Private SP-API Developer」「Register your Application」「Authorize Private Applications」（2026-09-13 取得）。前提：大口（2026-09-12 切替済み）・Primary User でログイン。

### 4-1. 画面の順番と、誰が何をするか

| # | 画面・操作 | 誰が | §4.1 | 備考 |
|---|---|---|---|---|
| 1 | Seller Central にログイン（memory の正規手順：`.com` 入口 → 日本切替） | 社長（ログイン＝本人のみ） | — | 「Solution Provider Portal に移行済み」の案内が出たら**進まず秘書に報告**（未確認の分岐） |
| 2 | メニュー → Apps and Services → **Develop Apps** | 秘書（ブラウザ操作） | — | **開くだけでは申請にならない**。フォームが表示されるだけ |
| 3 | Developer Profile の入力：Contact Information／Data Access＝「Private Developer」／Roles／Use Cases／Security Controls | 秘書が下書きを入力。社長は確認 | — | 入力内容は §4-2・§4-3。500 語以内・AUP/DPP の文言をコピーしない（公式の指示） |
| 4 | 同意チェック（Solution Provider Portal Agreement・AUP・DPP）→ **Register** | **社長** | **該当（法的拘束）** | **一手①**。ここで DPP §1 の義務が発生 |
| 5 | 審査待ち。追加照会は**5 日以内に返信**（過ぎると案件が閉じる） | 秘書が下書き・社長が送信 | 外部発信 | 一手②（照会があった場合のみ） |
| 6 | 承認後：Develop Apps → **Add new app client** → フォーム（アプリ名・API type＝SP-API・Roles） | 秘書が入力 | — | 送信すると **client_id／client_secret が発行**される |
| 7 | フォーム送信（＝API キー取得） | **社長** | **該当（API キー取得）** | **一手③**。表示された値は秘書が読まない。社長が Keychain へ投入（§4-4） |
| 8 | 同画面の **Authorize app** → refresh_token 表示 | **社長** | **該当** | **一手④**。ボタンを押した瞬間に発行される。**押すまでは何も起きない** |

「開くだけで申請になる画面」は**ありません**。送信になるのは #4 Register・#6 フォーム送信・#8 Authorize app の 3 つのボタンです。秘書は #2〜#3・#6 の入力までを行い、3 つのボタンは押しません。

### 4-2. 登録フォームに要る情報

| 項目 | 当社の値 | 出所 |
|---|---|---|
| 組織名・連絡先 | 屋号 Satoy Select／社長の氏名・メール・電話（Seller Central 登録と同じ） | 社長が確認 |
| Data Access | Private Developer: I build application(s) that integrate my own company with Amazon Services APIs | 公式手順 |
| Roles | Pricing／Product Listing（§4-3） | 確度中 |
| Use Cases（原文で・500 語以内） | 下書き：「自社の出品候補について、(1) 出品制限の有無 (2) 現在の出品者数とカート価格 (3) 手数料見積を、自社の仕入れ判断のために取得する。取得した情報は自社の Mac 1 台のローカル DB にのみ保存し、第三者に提供・公開しない。PII は取得しない。」（秘書が英訳・整形） | 本書 |
| Security Controls | §1 の表をそのまま答える（FileVault・Keychain・TLS1.2・1 名・ローカル DB・24h 通知・30 日削除） | 本書 |
| PII を扱うか | **扱わない**（Restricted Role を申請しない） | ハルオ 02 §1-7 |

Security Controls の設問の**正確な文面は未取得**（画面がログイン後）。W1「SP-API 登録画面の要件確認」で秘書が #2 まで開いて設問を写し、本書 §1 と対応づけてから #4 に進んでください。

### 4-3. Roles（確度中・要確認）

| エンドポイント | 要る Role（当職の理解） |
|---|---|
| `getItemOffers`・`getMyFeesEstimateForASIN` | Pricing |
| `getListingsRestrictions` | Product Listing |

公式「Role Mappings for Operations」ページは当職の環境から取得できず（404/403）。#3 の入力前に秘書がブラウザで確認してください。Role が足りないと 403 で、プロフィールの再提出になります。

### 4-4. 社長のターミナル操作（一手③④の続き。鍵を入れるのは本人だけ）

```bash
# 値は末尾の -w を空にしてプロンプトで入力（シェル履歴に残らない）。3 回。
security add-generic-password -s satoy-spapi -a client_id     -U -w
security add-generic-password -s satoy-spapi -a client_secret -U -w
security add-generic-password -s satoy-spapi -a refresh_token -U -w
```

1.2.2 のロックアウト（規約同意より前に。管理者権限が要るため社長のみ）：

```bash
pwpolicy -u "$USER" -setpolicy "maxFailedLoginAttempts=10"
```

ファイアウォール（1.1.1）はシステム設定 → ネットワーク → ファイアウォール → オン。

---

## 5. やらないこと

| やらない | 理由 |
|---|---|
| 履歴系（BSR・価格・出品者数の推移・ドロップ数）を SP-API で取る | Keepa で済んでいる（ハルオ 9/6・サトル③ 2-C）。SP-API は時点値しか返さない |
| 実装に着手する | 成立 3 社以上か SKU 10 件超まで着手しない（論点⑤）。`feedback_ship_dont_instrument` |
| Catalog Items・Reports・Orders・Notifications | 3 エンドポイントで用が足りる。Roles も増やさない（1.3） |
| 取得データを Claude に読ませて判断させる | BSA 4.2 が未確認（ハルオ）。判定が出るまで**人が SQLite の値を見る**運用 |
| クラウド／夜間自走セッションから叩く | 鍵が Mac の Keychain にしかない設計。クラウドには秘密の置き場がない（Keepa MCP と同じ割り切り） |
| PUBLIC リポに SP-API 由来の数値を置く | AUP 4.6 |

---

## 6. リスク評価（1.6.1・1 枚・年 1 回見直し）

| リスク | 起きたら | 対策 | 残余 |
|---|---|---|---|
| 鍵の漏洩（リポ push・ログ出力） | API 停止・出品アカウントへの波及は明文なし（SPPA 未取得） | Keychain のみ・平文禁止・pre-commit の値付き検知・ログに鍵を書かない実装 | 低 |
| Mac の紛失・盗難 | DB と鍵が第三者の手に | FileVault On・5 分ロック・パスワード 12 文字以上 | 低 |
| データの誤公開（deliverables に集計値） | AUP 4.6 違反 | §2-3 の線引き・DB をリポ外・`.gitignore` 案・pre-commit 案 | 中（人の判断が残る） |
| レート超過（429） | 一時停止 | トークンバケット・リトライは 1 回・失敗は `access_log` に正直に | 低 |
| 規約改定の見落とし | 義務が増える | 年 1 回の見直し日に AUP/DPP の更新日を確認（§8） | 中 |

## 7. インシデント対応 runbook（1.6.2〜1.6.5）

### 7-1. 「インシデント」と数えるもの

鍵（client_secret・refresh_token・access_token）の平文露出、DB ファイルの外部流出、Mac の紛失、SP-API 由来データの PUBLIC リポへの commit（push 前でも数える）。

### 7-2. 24 時間以内の手順

| 順 | 誰が | 何を |
|---|---|---|
| 1 | 発見者 | 秘書へ即報告。時刻を記録 |
| 2 | 社長 | Seller Central → Develop Apps → 当該アプリの認可を取消（refresh_token 失効）。client_secret をローテ |
| 3 | 社長 | Keychain の 3 項目を削除（`security delete-generic-password -s satoy-spapi -a <acct>`） |
| 4 | 秘書 | 下記雛形でメール下書き → **社長が security@amazon.com へ送信**（§4.1） |
| 5 | 秘書 | §7-4 の記録票を起票。チケット化 |

雛形（英文・秘書が事実で埋める）：
`Subject: Security Incident Notification – Private SP-API developer (Seller ID: <ID>)` ／ 本文：発見日時（JST/UTC）・何が露出したか・影響範囲（PII なし）・取った措置（認可取消・鍵ローテ・削除）・IMPOC 氏名と連絡先。

### 7-3. 認可取消・鍵ローテの手順（1.2.3・1.4.2 共用）

Seller Central → Apps and Services → Develop Apps → アプリ → 認可の取消／client_secret のローテ（Solution Provider Portal 側の「View credentials」）。新しい値は §4-4 で Keychain に上書き（`-U`）。`spapi_min.py rotation-status` が `key_rotation` に日付を残す。

### 7-4. 記録票（1.6.4）

日時／発見者／何が／どこまで／原因／措置／再発防止／Amazon 通知日時／クローズ日。`docs/security/incidents/YYYY-MM-DD.md`（鍵の値は書かない）。

## 8. 定期作業カレンダー

| 何を | 周期 | 次回 | 記録先 |
|---|---|---|---|
| 鍵ローテ（client_secret・refresh_token） | 12 か月 | 同意日＋1 年 | `key_rotation` 表 |
| リスク評価（§6）見直し | 12 か月 | 同意日＋1 年 | 本書 §8 に日付追記 |
| runbook（§7）見直し | 6 か月 | 同意日＋半年 | 同上 |
| Approved User 棚卸し（1 名の確認） | 四半期 | 同意日＋3 か月 | 同上 |
| DB の 18 か月失効（`expire`） | 月次（自動で可） | — | `access_log` |
| AUP/DPP の更新日確認 | 12 か月 | 同意日＋1 年 | 同上 |

## 9. 未確認（推測で埋めていない）

| 項目 | 状態 | 取得手段 |
|---|---|---|
| Security Controls 設問の文面 | 未取得（ログイン後） | 秘書ブラウザ（W1） |
| 3 エンドポイントの Role 対応 | 確度中 | 公式 Role Mappings for Operations（当職は 403/404） |
| SPPA 本文（制裁の出品アカウントへの波及） | 未取得 | ハルオ §4 と同じ |
| BSA 4.2（AI での処理可否） | 未取得 | 同上 |
| Solution Provider Portal への移行案内が当社に出るか | 未確認 | #2 を開いたときに分かる |
| Mac ログインパスワードの長さ | 未確認 | 社長のみ |

## 10. 出典

| # | 内容 | URL・取得日 |
|---|---|---|
| 1 | Data Protection Policy（§1 1.1〜1.8・§3） | https://sellercentral.amazon.com/mws/static/policy?documentType=DPP&locale=en_US（2026-09-13） |
| 2 | Register as a Private SP-API Developer（8 ステップ・5 日以内返信） | https://developer-docs.amazon/sp-api/docs/register-as-a-private-developer（2026-09-13） |
| 3 | SP-API Registration Overview（大口要件・500 語・原文で書く） | https://developer-docs.amazon/sp-api/docs/registering-as-a-developer（2026-09-13） |
| 4 | Register your Application（Add new app client） | https://developer-docs.amazon/sp-api/docs/registering-your-application（2026-09-13） |
| 5 | Authorize Private Applications（Authorize app・refresh_token・Primary User） | https://developer-docs.amazon/sp-api/docs/self-authorization（2026-09-13） |
| 6 | Connect to the SP-API（LWA・`x-amz-access-token`・SigV4 不要） | https://developer-docs.amazon/sp-api/docs/connecting-to-the-selling-partner-api（2026-09-13） |
| 7 | Key Security Control Guidance（Non-PII 18 か月・ログ 12 か月） | https://developer-docs.amazon/sp-api/docs/guidance-to-address-key-security-controls-in-sp-api-integration（2026-09-13） |
| 8 | SP-API Endpoints・Marketplace IDs（FE・`A1VC38T7YXB528`） | https://developer-docs.amazon/sp-api/docs/sp-api-endpoints ／ /marketplace-ids（2026-09-13） |
| 9 | 法務判定 §1-7 | `02_複合戦略_法務判定.md` |
| 10 | サトル③ §2-A（レート・取れるデータ・課金撤回） | `T-20260912-003/04_法務NO経路の再検討と適法な代替手段.md` |
| 11 | 当社 Mac の実測（FileVault・FW・ロック・pwpolicy・SIP・Python/TLS） | 2026-09-13 タカシ・読み取りコマンドのみ |
