# SP-API 同意前の最小構成 — DPP §1 を「1台の Mac・1人」に当てはめた型

記録：タカシ ／ 2026-09-13 ／ T-20260912-002（親・論点⑤⑪）
成果物：`workspace/output/deliverables/T-20260912-002/05_SP-API_同意前の最小構成.md`＋`05_adapters_spapi_min.py`

## 結論（次に「規約同意が先で実装は後」の API が来たらこれ）

- **同意した瞬間から安全管理義務が始まる API がある。** SP-API の DPP §1 は PII 不問・実装の有無不問。「登録だけ先に」でも整備は先。ハルオ判定 02 §1-7 の条件。
- 整備は**文書 8・実測 6・社長の一手 3・実装 1** に分解できた。18 要件のうちコードで満たすのは 1 つだけ（鍵ローテ記録）。**新しい観測系は作らない**（`feedback_ship_dont_instrument`）が守れる規模。
- 「規約同意より前に済ませる社長の一手」は **ファイアウォール ON と `pwpolicy` のロック方針**の 2 つ。macOS 既定では両方 OFF／未設定（実測）。FileVault・SIP・画面ロック 5 分は既定で満たしていた。

## 設計で決めたこと（理由つき）

| 決定 | 理由 |
|---|---|
| 鍵は Keychain（service `satoy-spapi`）。`.env` を使わない | Keepa MCP で既定化済み（`knowledge_mcp_secret_storage_design`）。netsea.py は `.env` 方式だが、PUBLIC リポ＋自動 push の環境では Keychain が既定 |
| DB は `~/Library/Application Support/satoy-spapi/spapi.sqlite`（リポ外）。`.gitignore` は二重の保険 | `.gitignore` を信じない（`knowledge_public_repo_leak_prevention`）。AUP 4.6 は集計値も外部開示不可＝ **Keepa の「統計なら白」が使えない** |
| deliverables に書くのは「可否・件数・当社の決定」だけ。利益額の一覧表は載せない側に倒す | 手数料（SP-API 値）を使った瞬間に派生物。ハルオ未判定なので安全側 |
| 3 エンドポイント固定（getItemOffers／getListingsRestrictions／getMyFeesEstimateForASIN）。Roles は Pricing・Product Listing のみ申請 | AUP「not necessary for your Application's functionality」＋DPP 1.3 最小権限。増やすなら Profile 再提出 |
| `purge` は §4.1（不可逆な削除）。要請を受けたら即日 waiting、30 日内に承認 | DPP 1.7 の 30 日と社内の承認ルールを両立させる唯一の順序 |
| 取得データを Claude に読ませない（人が SQLite を見る） | BSA 4.2（AI/ML でのモデル改善禁止）が一次未取得。判定が出るまで安全側 |
| クラウド／夜間セッションからは叩かない | 鍵が Mac の Keychain にしかない。Keepa MCP と同じ割り切り |

## 登録手順で分かったこと（公式 2026-09-13）

- 「開くだけで申請になる画面」は**無い**。送信になるのは Register・Add new app client のフォーム送信・Authorize app の 3 ボタン。秘書は入力まで、ボタンは社長。
- refresh_token は Authorize app を押した瞬間に発行・表示される。**押すまで何も起きない**。表示値は秘書が読まず、社長が `security add-generic-password ... -w`（値なし末尾＝プロンプト入力）で Keychain へ。
- 審査中の追加照会は **5 日以内に返信**しないと案件が閉じる。社長の在席確認を先に。
- Use Case は 500 語以内・原文で・AUP/DPP の文言をコピーしない（公式の指示）。
- SigV4 は不要（LWA の `x-amz-access-token` だけ）。日本は FE エンドポイント `sellingpartnerapi-fe.amazon.com`・Marketplace `A1VC38T7YXB528`。
- 費用 0 円（第三者開発者向け年 1,400 ドルは 2026-05 に撤回。一次告知ページは未特定＝二次）。

## 取れなかったもの（推測で埋めていない）

Security Controls 設問の文面（ログイン後）／3 エンドポイントの Role 対応（公式 Role Mappings が 403/404）／SPPA 本文（制裁の出品アカウントへの波及）／BSA 4.2 逐語／Solution Provider Portal 移行案内の有無。→ 05 §9。

## 手順として再利用できる形

1. 規約（AUP・DPP 相当）の条項を**1 行 1 要件**の表にする。要件→当社の実装→実測・根拠→状態（済／文書／一手／実装）。
2. Mac の実測は読み取りコマンドだけで取る：`fdesetup status`・`socketfilterfw --getglobalstate`・`csrutil status`・`sysadminctl -screenLock status`・`pwpolicy -u $USER -getaccountpolicies`・`python3 -c 'import ssl;print(ssl.OPENSSL_VERSION)'`。設定は変えない（変えるのは社長の一手）。
3. リポの境界は「鍵＝Keychain／データ＝リポ外／コードと可否＝リポ」の 3 行で書く。`.gitignore` 追加行と pre-commit 検知語は**案のまま**残し、適用は社長判断後。
4. 雛形コードは `import` しても何もしない形（関数本体 `NotImplementedError`・`__main__` は SystemExit）。docstring 先頭に用途制限（netsea.py の流儀）。
5. HTML は `agents/content_creator/skills/md_to_standalone_html.py`。**Markdown リンク `[x](y)` は未対応**＝生成後に anchor へ置換して、原稿全行の照合を回す。
