---
ticket_id: T-20260804-001
title: メーカー仕入れせどり｜Amazon売れ筋メーカー台帳（連絡先・想定仕入価格つき）
status: waiting
assignee: secretary
priority: high
created_at: 2026-08-04
updated_at: 2026-08-04
next_check_at: 2026-08-27
requires_approval: false
labels: [maker-shiire, research, keepa, spreadsheet, overnight]
related_tickets: [T-20260705-002, T-20260803-001, T-20260612-001]
---

## 依頼（社長・2026-08-04／プラン承認済）
前チケT-20260803-001は電脳せどり用（仕入先=楽天/Yahoo）で方向違い。今回は**メーカー仕入れせどり**。
Amazon売れ筋商品の**メーカー**をナレッジ基準で選別し、連絡先・想定仕入価格つきでリスト化。

## 承認済みプラン＋社長修正
- ランキング **50,000〜150,000位**（社長修正）
- ナレッジ3基準（[knowledge_maker_shiire_ecstars]）: ①Amazon本体不在 ②FBAライバル2人以上 ③ランク上記帯
- 中小メーカー狙い（大手・代理店卸は除外/フラグ）、規制カテゴリ除外（医薬品/化粧品/食品）、海外は正規代理店窓口フラグ
- **必須列**: ASIN / 現Amazon価格 / メーカー想定仕入価格(外注費・輸送費込みで利益が出る価格) / メーカー名 / 連絡先(電話・メール) / 月販数 / ライバルセラー数 ＋ 追加項目
- 独立スプレッドシートで納品（社長が空シートをSAへ共有→カズヨ流し込み、の段取り）

## 実装
- Phase A（自動・夜間）: Keepa Product Finder で本体不在×競合2+×ランク5万-15万を多カテゴリ抽出 → 詳細取得 → raw から brand/manufacturer 直読み（[knowledge_maker_extraction_keepa]）→ 利益から**想定仕入価格を逆算** → メーカー名寄せ。
- Phase B（ベストエフォート・Web）: メーカー連絡先(電話/メール/HP)をWeb探索で付与。取れない分は空欄/要確認（推測厳禁）。
- 想定仕入価格＝純利益率25%になる税込仕入上限（販売手数料+FBA+納品送料+梱包外注等を計上）。

## 注意（§4.1）
- メーカーへの実連絡・問い合わせメール送信は §4.1 該当＝**社長承認必須**。本チケットは台帳作成まで。

## 納品先（社長が用意・SA共有済）
- 📗 独立Googleシート「メーカー仕入れ台帳」（社長所有）: https://docs.google.com/spreadsheets/d/1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4/edit
- SA(sheets-writer@)へ編集者共有・書込疎通確認済（2026-08-04）。ここへ Phase A/B 完了後に流し込む。

## ログ
- 2026-08-04 起票・doing。プラン承認（ランク5万-15万修正）。Phase Aハーネス実装へ。
- 2026-08-04 16:00 Phase A起動（目標5,200・13カテゴリ）。スモークテスト合格（本体不在フィルタ・メーカー直読み・想定仕入価格逆算OK）。
- 2026-08-04 16:04 Finder完了＝母集団**5,197商品**。詳細取得（メーカー付与）へ。社長が空シート作成＋SA共有→書込疎通確認済。
- 2026-08-04 夜 電源断で中断（3,736行保存済）。ハーネスを再開対応化（asin_mapキャッシュ＋処理済スキップ＋逐次保存）。
- 2026-08-05 07:36 再起動→保存分スキップで再開。11:07 **Phase A完走＝売れ筋7,840商品／ユニークメーカー3,282社（中小候補3,181）**、各商品に想定仕入価格(利益率25%上限)付与。
- 2026-08-05 共有シート「メーカー仕入れ台帳」へ反映（サマリ/メーカー台帳3282/売れ筋商品7840）。大手/著名184社を再分類。
- 2026-08-05 **Phase B完了**：中小・国内 上位60社をサブエージェント4班で探索→**55社で連絡先取得**（電話/公式HP/メール・フォーム、出典URL付き）。台帳60社・商品578行へ反映。
- 2026-08-05 共有シートに **★連絡先取得済(優先)55社** タブを先頭追加。**waiting（社長レビュー待ち）へ**。

## 納品物（確定）
- 📗 共有Googleシート「メーカー仕入れ台帳」: https://docs.google.com/spreadsheets/d/1y1e15tdhm_o5-RfZxKIer96CWpijVPFUfIbK-W7q7X4/edit
  - タブ: **★連絡先取得済(優先)55社** / メーカー台帳3,282社 / 売れ筋商品7,840件 / サマリ・前提
- ローカル: maker_ledger.csv(3,282) / maker_products.csv(7,840) / contacts_batch1-4.json / maker_summary.json / スクリプト一式

## 社長の次アクション（waiting）
1. **★連絡先取得済(優先)** タブを見て、取引したい中小メーカーを選ぶ。
2. カズヨへ「このメーカーに連絡」と一言 → 問い合わせメール文面を作成しA/B提示。
3. **メーカーへの実送信は§4.1（第三者連絡）＝社長承認必須**。承認後に送信。
4. 連絡先の追加取得が必要なら、次バッチ（中小61位以下）を続行可能。
- 2026-08-21 棚卸し（マリエ／T-20260821-007）: next_check_at 2026-08-05 → 2026-08-27 に再設定。仕分け=A。理由: 本線。55社台帳は T-20260817-005 が消化月数順に再ソート中。単独レビューでなく合流後に出すのが筋

## 成果物

- 📁 **[T-20260804-001/](../../output/deliverables/T-20260804-001/)** — 成果物フォルダ（24件）
  - [`SOURCE.md`](../../output/deliverables/T-20260804-001/SOURCE.md) — 出所カード — T-20260804-001（卸価格プローブ）（1.8KB）
  - [`asin_map.json`](../../output/deliverables/T-20260804-001/asin_map.json) — JSONデータ（185.9KB）
  - [`build_maker_sheet.py`](../../output/deliverables/T-20260804-001/build_maker_sheet.py) — メーカー台帳 → 社長所有の共有Googleシート(1y1e15…)へ流し込み。 タブ: サマリ・前提 / メーカー台帳 / 売れ筋商品。連絡先はPhase B（5.6KB）
  - [`contacts_batch1.json`](../../output/deliverables/T-20260804-001/contacts_batch1.json) — JSONデータ（5.2KB）
  - [`contacts_batch2.json`](../../output/deliverables/T-20260804-001/contacts_batch2.json) — JSONデータ（5.3KB）
  - [`contacts_batch3.json`](../../output/deliverables/T-20260804-001/contacts_batch3.json) — JSONデータ（4.8KB）
  - [`contacts_batch4.json`](../../output/deliverables/T-20260804-001/contacts_batch4.json) — JSONデータ（5.0KB）
  - [`maker_contact_shortlist.csv`](../../output/deliverables/T-20260804-001/maker_contact_shortlist.csv) — 100行 × 5列（maker・brands・top_asin・n_products ほか）（6.2KB）
  - [`maker_ledger.csv`](../../output/deliverables/T-20260804-001/maker_ledger.csv) — 3282行 × 14列（maker・brands・n_products・n_criteria_ok ほか）（362.1KB）
  - [`maker_products.csv`](../../output/deliverables/T-20260804-001/maker_products.csv) — 7840行 × 20列（asin・name・category・amazon_price ほか）（2.2MB）
  - [`maker_scan.py`](../../output/deliverables/T-20260804-001/maker_scan.py) — メーカー仕入れせどり｜Amazon売れ筋メーカー抽出ハーネス（Phase A・T-20260804-001）。 ナレッジ3基準（EC STARs/中西）: ①A（16.6KB）
  - [`maker_scan_progress.log`](../../output/deliverables/T-20260804-001/maker_scan_progress.log) — 実行ログ（11.7KB）
  - [`maker_scan_run.log`](../../output/deliverables/T-20260804-001/maker_scan_run.log) — 実行ログ（22.3KB）
  - [`maker_summary.json`](../../output/deliverables/T-20260804-001/maker_summary.json) — JSONデータ（611B）
  - [`monthlysold.csv`](../../output/deliverables/T-20260804-001/monthlysold.csv) — 7840行 × 3列（asin・main_rank・※Keepa固有の加工値(月間ドロップ数/過去最安値/365日最安/月間販売数/実セラー数)と卸値の列は規約上の理由でリポジトリから除外。完全版は ~/Docume…
  - [`monthlysold_progress.log`](../../output/deliverables/T-20260804-001/monthlysold_progress.log) — 実行ログ（10.5KB）
  - [`monthlysold_refetch.py`](../../output/deliverables/T-20260804-001/monthlysold_refetch.py) — 実測月販(Keepa monthlySold=Amazon"◯◯+個購入")を全商品ぶん取り直す。 出力: monthlysold.csv (asin, mon（3.5KB）
  - [`monthlysold_run.log`](../../output/deliverables/T-20260804-001/monthlysold_run.log) — 実行ログ（10.7KB）
  - [`target_sheet_id.txt`](../../output/deliverables/T-20260804-001/target_sheet_id.txt) — テキスト（134B）
  - [`wholesale_probe.csv`](../../output/deliverables/T-20260804-001/wholesale_probe.csv) — 55行 × 8列（maker・asin・jan・amazon_price ほか）（6.5KB）
  - [`wholesale_probe.log`](../../output/deliverables/T-20260804-001/wholesale_probe.log) — 実行ログ（331B）
  - [`wholesale_probe.py`](../../output/deliverables/T-20260804-001/wholesale_probe.py) — 実仕入値の実態調査（Phase C）。 優先55社の代表商品について、Keepaで JAN と 参考価格(listPrice/定価) を取り直し、 NETSEA（4.6KB）
  - [`wholesale_probe_run.log`](../../output/deliverables/T-20260804-001/wholesale_probe_run.log) — 実行ログ（606B）
  - [`損益分岐シミュレータ_メーカー仕入れ.xlsx`](../../output/deliverables/T-20260804-001/損益分岐シミュレータ_メーカー仕入れ.xlsx) — Excel（14.8KB）
- 社長の閲覧口（Finder）：`~/Documents/AI Company Outputs/Amazon物販事業/T-20260804-001/`
