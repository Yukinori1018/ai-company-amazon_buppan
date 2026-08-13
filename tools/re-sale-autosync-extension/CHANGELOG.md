# Changelog — Re-Sale AutoSync 拡張

## v0.2.0 — 2026-08-12（リスクアセスメント反映・安全弁強化）

リスクアセスメント（`docs/RISK_ASSESSMENT.md`）に基づく自律改善の第1弾。

### 🔴 安全弁（金銭）
- **A1 日次購入上限を実発火**: 実購入直前に background の事前承認ゲート `CAN_PURCHASE` を必須化。
  タスクがPENDINGか・単価が損益分岐(maxSourcePrice)以内か・日次上限に収まるかを検査し、
  否なら購入を中止（従来 `canSpend()` は定義のみで未呼出だった）。残枠も表示。
- **A2 DRY_RUN では日次枠を消費しない**（検証中の擬似購入で判断が歪むのを防止）。
- **A3 `canSpend` の死コード除去**＋`remainingBudget()` 追加。

### 🟠 判定・パース
- **B1 ヤフオクHTML判定の優先順位を明確化**（NOT_FOUND>CANCELLED>ENDED>ACTIVE）。
  終了ページのおすすめ枠にある「カートに入れる／購入手続きへ」で**誤ACTIVEになる不具合を修正**。
  売り切れ/SOLD OUT等のフリマ終了語も追加。
- **B2 価格不明のACTIVE**は理由を `PROCURABLE_PRICE_UNKNOWN` に分離（可観測化）。

### 🟡 堅牢性
- **C2** セラーセントラルの注文読取を MutationObserver デバウンス(700ms)化（連打防止）。
- **C3** 在庫変更失敗時の no-op 空メッセージ（死コード）を除去し、警告ログに一本化。
- **D1** popup の通貨表示を未定義ガード付き `yen()` に（不正データでの白画面を防止）。
- **D4** 拡張起動時（onStartup）に監視を即1周（監視の空白を縮小）。

### テスト
- 依存ゼロのユニットテスト基盤を新設（`test/run.js` / `npm test`）。pricing・decide・parseYahooHtml・
  日次上限(canSpend/addSpend) を **27ケース** で検証。ヤフオクHTMLフィクスチャ5種を同梱。

### 未了（次イテレーション）
- C1 セレクタの options 外部化（実画面調整をコード改修不要に）＝次の本命。
- B3/B4 実HTMLでのパース検証、D2 ログエクスポート、E1 README ポリシー運用の明記。
