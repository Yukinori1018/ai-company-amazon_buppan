---
description: 成果物カタログのGoogleスプレッドシートを最新化して開く（社長の入口）
---

# /amazon_buppan_catalog — 成果物カタログを開く

Amazon物販事業の**成果物カタログ（Googleスプレッドシート）を、最新状態にしてからブラウザで開く**ための入口コマンドです。社長がこのプロジェクトの作業を始めるときに使います。

- シートURL: https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit?gid=267140826#gid=267140826
- マスターCSV（真実）: `workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`
- 同期スクリプト: `scripts/catalog/sync_catalog_to_sheet.py`（連携詳細は `agents/general_affairs/skills/deliverables-catalog.md`）

## 手順（カズヨが実行）

1. **最新化（任意・接続があれば実施）**: `scripts/catalog/.catalog_sync.env` が存在すれば、
   `python3 scripts/catalog/sync_catalog_to_sheet.py` を実行してマスターCSVをシートへ全置換ミラー同期する。
   - 成功なら「同期 NN行」を1行で報告。
   - `.env` が無い（クラウド等）／同期失敗時は**止めずに**理由を1行添えて次へ進む（開くことを優先）。
2. **開く**: `open "https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit?gid=267140826#gid=267140826"` を実行してブラウザで表示する。
   - `open` が使えない環境（クラウド等）では、代わりに上記URLを**クリック可能なリンクとして提示**する。
3. **報告**: 「同期結果（あれば）＋開いた旨／URL」を簡潔に1〜2行で返す。

## 引数

- 引数 `nosync` が付いていたら手順1をスキップし、同期せず即開く（例: `/amazon_buppan_catalog nosync`）。
- 引数 `synconly` が付いていたら手順2をスキップし、同期だけ行う（ブラウザは開かない）。

## 注意

- このコマンドは§4.1に該当しない（社長自身のシートを開く・自身のCSVを同期するのみ）。承認不要で実行してよい。
- ブラウザで開けるのはローカル（社長Mac）セッションのみ。クラウドではURL提示に切り替える。
