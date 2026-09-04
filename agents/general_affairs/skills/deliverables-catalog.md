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

## 2. 列設計（厳守。ヘッダーは日本語・この順）**13列**

```
チケットID,ToDo/タスク名,成果物タイトル,内容（要約）,暫定結果,種別,GitHubリンク,リポジトリ相対パス,担当,形式,作成日,社長レビュー,備考
```

> **`暫定結果` は12列目までの後付けではなく、4列目の直後に挿入された5列目です（12列→13列）。**
> 社長が「このチケットの結果はどうなったか」をカタログ上で即確認できるようにするための列で、
> 2026-06-01 の社長依頼〔T-20260601-005〕で追加されました。**12列に戻さないこと。**

- 内容（要約）は**必ずファイルを読んで**1〜2行で書く（憶測禁止）。カンマ回避のため読点「、」を使う。
- **暫定結果**は当該チケットの現時点の結論を1行で。冒頭に状態を角括弧で立てる：
  `【確定】` / `【進行中】` / `【暫定】` / `【社長レビュー待ち】` / `【判断待ち】` / `【方針転換】` / `【不使用】`。
  結論が出ていないものを空欄にしない（**「未確定である」ことが結論**）。チケットの状態が動いたら、
  カタログ更新の締め作業としてこの列も最新化する（done化・方針転換・成果物の再生成時など）。
- GitHubリンクは `https://github.com/Yukinori1018/ai-company-amazon_buppan/blob/<branch>/<相対パス>`。
- リポジトリ相対パスはブランチ削除に強い恒久アンカー（こちらが本命）。
- CSV は RFC4180（カンマ/改行/" を含む値はダブルクォート囲み、内部の " は "" にエスケープ）。UTF-8。

### ⚠️ 書く前に、ヘッダー行を実物で確認すること

この節の記載は**2026-09-04 に実物とのズレ（12列記載／実物13列）を修正したもの**です。
同じズレを二度と作らないため、追記の前に必ず実物のヘッダーを読んでから列を組み立てます。

```bash
head -1 workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv
# 追記後の検算（全行が同じ列数か。1種類でなければ列ズレ）
python3 -c "import csv;r=list(csv.reader(open('workspace/output/deliverables/T-20260601-001/deliverables-catalog.csv',encoding='utf-8-sig')));print(set(len(x) for x in r))"
```

> 列が増減したら、**この節と実物の両方を同じ turn 内で更新する。**片方だけ直すと、
> 次に読む人が古い側を信じて列ズレを起こします（2026-09-04 に社内で同型の事故が3件出ています）。

## 3. 成果物が出たときの手順（定常）

0. **`git ls-files workspace/output/deliverables/<ticket_id>/` で追跡済みファイルの集合を取る。**
   チケット直下に `.gitignore` が置かれていることがある（PUBLIC リポに出せない行データを除外するため）。
   **追跡外のファイルで行を作ると GitHubリンクが 404 になる**ので、単独行にはせず、
   同チケットの追跡済みファイル（実測ログ・README など）の**備考欄に所在と除外理由を書いて逃がす**。
   初出＝2026-09-04 / T-20260904-004（NETSEA のサプライヤー社名を含む CSV 2件）。
1. 新しい成果物ファイルを Read で開き、内容を1〜2行で要約。
2. **マスターCSV に行を追記**（列設計どおり・13列）。ノイズ（.DS_Store / __pycache__ / .pyc / 空 __init__ / 作図スクリプト群）は除外、コード一式・スクリプト群は1行に集約。
3. **Googleスプレッドシートへ反映**（ローカル環境のみ）。
4. チケット完了の締め作業にこの①〜③を含める。

## 4. スプレッドシートへの反映手段（稼働中・T-20260601-003）

- **Apps Script Web App 連携**（2026-06-01 疎通済）。マスターCSVを更新したら次を実行するだけ:
  ```bash
  python3 scripts/catalog/sync_catalog_to_sheet.py            # 同一URLのシートを全置換ミラー更新
  python3 scripts/catalog/sync_catalog_to_sheet.py --dry-run  # 送信せず行数・先頭行プレビュー
  ```
- 仕組み: CSV を Web App へ POST → シートを全クリア→全行書き込み（**全置換ミラー・冪等**。差分計算不要・行重複なし）。**URLは固定**。
- 設定・手順書: [scripts/catalog/README.md](../../../scripts/catalog/README.md)。接続情報（URL・トークン）は `scripts/catalog/.catalog_sync.env`（**gitignore対象**・ローカルのみ）。
- **クラウド/夜間自走から実行する場合**: 認証はトークンのみで HTTPS POST するだけなので可能。ただし `.catalog_sync.env` はローカル限定のため、クラウド回は環境変数 `WEBAPP_URL` / `SHARED_TOKEN` を渡すか、CSV追記までに留めて次のローカル回で `sync_catalog_to_sheet.py` を流す。
- 初回生成（参考）: Google Drive コネクタ `create_file`（text/csv → スプレッドシート自動変換）で作成した。以後の更新は上記 Apps Script 連携を使う。

## 5. 検知の補助（任意・IT follow-up）

- `deliverables/` への新規ファイル追加を検知してカタログ更新を促すフック（`ticket-notion-sync-reminder.sh` の類似実装）をタカシが検討。実装されたらリマインドに従い未更新で turn を終えない。
