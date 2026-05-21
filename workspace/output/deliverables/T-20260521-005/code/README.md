# Sato-Scope Phase 1 コードベース

社長専用 Amazon 物販リサーチツール v0.2 の実装。Phase 1 では **API 接続前にできる最大限**（計算ロジック・FastAPI スケルトン・モックアダプタ・テスト）を構築しています。

## ディレクトリ構成

```
code/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI アプリ（/search, /health）
│   ├── calc/
│   │   ├── profit.py            # FBA / 自己発送 / MSS 真の利益計算（差別化の核）
│   │   └── score.py             # おすすめスコア + 🟢🟡🔴 判定
│   ├── adapters/
│   │   ├── keepa.py             # Keepa API アダプタ（モック付き）
│   │   ├── rakuten.py           # 楽天市場 API アダプタ（モック付き）
│   │   └── yahoo.py             # Yahoo!ショッピング API アダプタ（モック付き）
│   ├── compliance/
│   │   └── brand_warnings.py    # コンプラ警告マスタ（Sony/Apple/Nike 等）
│   └── static/
│       └── index.html           # モック HTML（v0.2）
├── tests/
│   └── test_profit.py           # 利益計算ユニットテスト
├── requirements.txt
├── .env.example
└── README.md
```

## セットアップ（社長 PC で動かす手順）

### 1. 必要なもの
- Python 3.10 以降（PC に入っているはず。`python3 --version` で確認）
- 1コマンドで動くので難しくありません

### 2. 仮想環境作成 + 依存インストール
```bash
cd ~/Claude\ Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/code
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 環境変数設定（モックモードならスキップ可）
```bash
cp .env.example .env
# .env を編集。API キー未設定の場合は自動的にモックモードで動きます
```

### 4. サーバ起動
```bash
uvicorn app.main:app --reload
```

→ ブラウザで http://localhost:8000/ を開くとモック画面が表示されます。
→ http://localhost:8000/search でバックエンドの JSON が見られます。
→ http://localhost:8000/health で稼働状況を確認できます。

### 5. テスト実行
```bash
pytest -v
```

## Phase 1 で実装済みのもの

- ✅ FBA / 自己発送 / MSS の3パターン真の利益計算（差別化の核）
- ✅ 利益額・利益率・月販・Drop30 を組み合わせた独自おすすめスコア
- ✅ 🟢🟡🔴 判定ロジック
- ✅ コンプラ警告マスタ（Sony・Panasonic・Apple・Nike 等）
- ✅ 楽天・Yahoo! の最安値選択ロジック
- ✅ ポイント込み実質価格計算
- ✅ FastAPI による `/search` `/health` エンドポイント
- ✅ モックアダプタ（8件サンプル）で**全機能が動く**
- ✅ ユニットテスト

## Phase 2 で実装予定（社長 GO 後）

- ⏳ Keepa API 実接続（**€49/月 課金 §4.1 承認後**）
- ⏳ 楽天市場 API 実接続（無料・社長 ApplicationID 登録）
- ⏳ Yahoo!ショッピング API 実接続（無料・社長 ApplicationID 登録）
- ⏳ SQLite で ★お気に入りの永続化
- ⏳ Keepa Product Finder の高度クエリ（カテゴリ・売れ筋）

## §4.1 承認が必要な事項

1. **Keepa API 月額 €49** の有料契約（カード決済）
2. 楽天/Yahoo! の ApplicationID 登録（無料だが社長個人アカウント連動）

Phase 2 着手前に改めて承認を取り直します。
