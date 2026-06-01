# 成果物カタログ → Google スプレッドシート 書き込み連携

成果物カタログのマスター CSV を、**URL を変えずに**同じ Google スプレッドシートへ
反映するための連携です。仕組みは「Apps Script Web App に CSV を POST → シートを
全クリアして全行書き込み（ミラー更新）」。

- 対象シート: <https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit>
- マスター CSV（真実）: `workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`
- 認証情報をローカルに置かない（OAuth/サービスアカウント不要）。共有トークンのみ。

---

## 構成ファイル

| ファイル | 役割 |
|---|---|
| `catalog_sync.gs` | シート側に貼る Apps Script。POST を受けてシートを全置換する |
| `sync_catalog_to_sheet.py` | ローカルから CSV を読んで POST するヘルパー（標準ライブラリのみ） |
| `.catalog_sync.env.example` | 設定見本。これをコピーして `.catalog_sync.env` を作る |
| `.catalog_sync.env` | 実設定（URL・トークン）。**gitignore 対象** |

---

## 社長の一度きり初期設定（クリック単位・全10ステップ）

> 所要 5〜10 分。一度やれば以降は秘書が `python3` 一発で同期できます。

1. 対象スプレッドシートをブラウザで開く。
2. 上部メニュー **拡張機能 → Apps Script** をクリック（新しいタブでエディタが開く）。
3. 既存の `コード.gs` の中身を全選択して削除し、リポジトリの
   `scripts/catalog/catalog_sync.gs` の中身を**全部コピペ**して、フロッピーアイコン（保存）をクリック。
4. 左側の歯車 **プロジェクトの設定** をクリック → 下部の **スクリプト プロパティ** →
   **スクリプト プロパティを追加** をクリック。
   - プロパティ名: `SHARED_TOKEN`
   - 値: 任意の長いランダム文字列（例: `Kx9aQ2m...` 24文字以上推奨）→ **スクリプト プロパティを保存**。
   - ※この値は後でステップ9で `.env` にも貼るので控えておく。
5. 右上 **デプロイ → 新しいデプロイ** をクリック。
6. 「種類の選択」の歯車 → **ウェブアプリ** を選択。
7. 設定を以下にする:
   - 説明: 任意（例: catalog sync v1）
   - 次のユーザーとして実行: **自分**
   - アクセスできるユーザー: **全員**
     （トークンで保護するため。「全員」でないとローカルから叩けません）
8. **デプロイ** をクリック → 初回は **アクセスを承認** を求められるので、
   自分の Google アカウントを選び、「詳細 → （プロジェクト名）に移動 → 許可」で認可する。
9. 表示される **ウェブアプリ URL**（末尾 `/exec`）を**コピー**。
10. リポジトリで `scripts/catalog/.catalog_sync.env.example` を
    `scripts/catalog/.catalog_sync.env` にコピーし、
    `WEBAPP_URL=` にステップ9の URL、`SHARED_TOKEN=` にステップ4の値を貼って保存。

これで設定完了です。

---

## 同期の実行（設定後・秘書が回す）

```bash
# 送信せず内容だけ確認（行数・先頭行のプレビュー）
python3 scripts/catalog/sync_catalog_to_sheet.py --dry-run

# 実送信（シートを全置換でミラー更新）
python3 scripts/catalog/sync_catalog_to_sheet.py

# 別の CSV を指定する場合
python3 scripts/catalog/sync_catalog_to_sheet.py --csv path/to/other.csv
```

成功すると `[OK] 同期成功: シート=..., 書き込み NN 行 x 12 列` と表示されます。

---

## トラブルシュート

| 症状 | 原因と対処 |
|---|---|
| `WEBAPP_URL が未設定` と出て送信されない | `.catalog_sync.env` 未作成。ステップ10をやり直す |
| JSON でない（HTML）レスポンス | デプロイのアクセス権が「全員」でない。ステップ7を修正し再デプロイ |
| `unauthorized` | `.env` の `SHARED_TOKEN` と Script Property の値が不一致 |
| 接続失敗 | URL の末尾が `/exec` か確認。`/dev` ではない |
| コードを直したのに反映されない | Apps Script で **デプロイ → デプロイを管理 → 編集（鉛筆）→ バージョン「新バージョン」→ デプロイ**。URL は変わりません |

## 設計メモ

- 行追記ではなく**全置換**。マスター CSV が常に真実で、シートはそのミラー。
  差分計算が不要で冪等（何度流しても同じ結果）。
- HTTP ステータスは Apps Script の制約で常に 200 系。成否はレスポンス JSON の
  `ok` フラグで判定している（`sync_catalog_to_sheet.py` 側で処理）。
- 列数が不揃いな行は Web App 側で右パディングしてから書き込む。
