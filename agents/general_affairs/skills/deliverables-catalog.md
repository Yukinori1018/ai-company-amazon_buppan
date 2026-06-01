# スキル：成果物カタログ運用（庶務マリエ）

> **責務者は庶務マリエ。** 成果物が `workspace/output/deliverables/` に出るたび、
> カタログ（マスターCSV＋Googleスプレッドシート）を最新化する定常責務。
> 起点チケット: T-20260601-001（社長依頼 2026-06-01）。

## 0. なぜマリエの責務か

- 成果物が各チケットフォルダに散らばり「どこに何があるか」が分からなくなる問題への対策。
- ToDo（チケット）に紐づけて「タイトル・内容・アウトプットURL」が一覧で引ける状態を保つのは庶務の本分。

## 1. 真実とミラーの関係

- **真実** = `workspace/output/deliverables/<ticket_id>/` 配下の成果物ファイル（Git 管理）。
- **マスターCSV**（リポ内の真実の表現）= `workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv`。
- **Googleスプレッドシート**（社長閲覧用ミラー、ローカル環境のみ生成可）。
  - タイトル: `成果物カタログ_Amazon物販事業`
  - Drive file id: `1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY`
  - URL: https://docs.google.com/spreadsheets/d/1xXfKbgbbiRUns-U40sgWNUWzwvu1s2aS3Gr1Ouy5MQY/edit
  - 所有: 社長アカウント（satoyukinori1018@gmail.com）/ My Drive 直下。

## 2. 列設計（厳守。ヘッダーは日本語・この順）

```
チケットID,ToDo/タスク名,成果物タイトル,内容（要約）,種別,GitHubリンク,リポジトリ相対パス,担当,形式,作成日,社長レビュー,備考
```

- 内容（要約）は**必ずファイルを読んで**1〜2行で書く（憶測禁止）。カンマ回避のため読点「、」を使う。
- GitHubリンクは `https://github.com/Yukinori1018/ai-company-amazon_buppan/blob/<branch>/<相対パス>`。
- リポジトリ相対パスはブランチ削除に強い恒久アンカー（こちらが本命）。
- CSV は RFC4180（カンマ/改行/" を含む値はダブルクォート囲み、内部の " は "" にエスケープ）。UTF-8。

## 3. 成果物が出たときの手順（定常）

1. 新しい成果物ファイルを Read で開き、内容を1〜2行で要約。
2. **マスターCSV に行を追記**（列設計どおり）。ノイズ（.DS_Store / __pycache__ / .pyc / 空 __init__ / 作図スクリプト群）は除外、コード一式・スクリプト群は1行に集約。
3. **Googleスプレッドシートへ反映**（ローカル環境のみ）。
4. チケット完了の締め作業にこの①〜③を含める。

## 4. スプレッドシートへの反映手段（現状と制約）

- 接続は **Google Drive コネクタ（MCP）**。社長は認証済みで追加OAuth不要。
- 新規生成は `create_file`（contentMimeType=`text/csv`、textContent=CSV全文、変換オプション無指定 → `application/vnd.google-apps.spreadsheet` に自動変換）。
- **制約**: この Drive コネクタは**セル単位の追記・更新APIを持たない**（create / read / copy / metadata のみ）。
  - そのため増分追記を既存シートへ in-place で反映できない。
  - **暫定運用**: マスターCSV を真実として追記 → ローカルで社長に増分を提示 →（行数が増えた節目で）CSV から再生成 or 社長が手動でシートに貼り付け。
  - **follow-up（タカシ/IT）**: append/update 可能な Google Sheets 連携を整備し、URL を変えずに増分反映できるようにする。整備後はこの節を更新。
- **クラウドセッションでは Google に繋げない**。クラウドで成果物が出た回は **CSV 追記まで**を行い、次のローカルセッション冒頭でシートへ追いつかせる。

## 5. 検知の補助（任意・IT follow-up）

- `deliverables/` への新規ファイル追加を検知してカタログ更新を促すフック（`ticket-notion-sync-reminder.sh` の類似実装）をタカシが検討。実装されたらリマインドに従い未更新で turn を終えない。
