# Sato-Scope Lite 使い方ガイド（社長向け）

副業初心者の社長が、ERESA PRO で見つけた仕入れ候補を **Sato-Scope Lite** に通して「本当に儲かるか／販売してOKか」を判定するための手順書です。

---

## このツールが何をしてくれるのか（3行で）

1. **ERESA で絞り込んだ候補リスト（CSV）を読み込み**、
2. **MSS（自己発送マケプレ配送）込みの真の利益／実質仕入れ価格／コンプラ警告**を全行に付与し、
3. **拡張 CSV を出力**します。最終的にどれを仕入れるかは、社長がこの拡張 CSV を見て決めます。

ERESA は FBA 前提で利益を出すため、**大型商品で本当は MSS のほうが儲かるケース**を見逃します。そこを Lite が補います。

---

## 0. 「ターミナル」とは何か（一度だけ読んでください）

「ターミナル」は、Mac の中にあるアプリで、**キーボードでパソコンに命令を出すための窓**です。普段はマウスでクリックして操作しますが、ターミナルでは文字を打ち込んで Enter を押して操作します。

- 開き方：`command (⌘) + space` → 「ターミナル」と入力 → Enter
- 黒い／白い画面が出ます。`$` や `%` という記号の右側に文字を打って Enter で実行
- 怖い見た目ですが、**打ち込んだコマンドが「初めての時だけ」効くものと、「毎回必要」なものがあります**。本ガイドではどちらかを明示します

---

## 1. 初回セットアップ（一度だけ）

ターミナルを開いて、以下を **1行ずつコピペして Enter** してください。

### 1-1. Lite フォルダに移動

```bash
cd "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260527-002/sato-scope-lite"
```

> `cd` は「change directory（フォルダを移動する）」の意味。

### 1-2. Python の仮想環境を作る（このフォルダ専用の砂場を作るイメージ）

```bash
python3 -m venv .venv
```

### 1-3. 砂場に入る

```bash
source .venv/bin/activate
```

> 成功するとプロンプトの左端に `(.venv)` と表示されます。

### 1-4. 必要なライブラリを入れる

```bash
pip install -r requirements.txt
```

> `pandas` と `pytest` の2つが入ります。1〜2分かかります。

これで初回セットアップは完了です。

---

## 2. 毎回の使い方（仕入れ判断のたび）

### 2-1. ERESA PRO で候補リストを CSV エクスポート

- ERESA PRO の詳細検索でカテゴリ・利益率・ランキング等で絞り込み
- 結果を CSV としてエクスポート（例: `Downloads/eresa_export_20260527.csv`）

### 2-2. ターミナルを開いて、Lite フォルダに入る

```bash
cd "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260527-002/sato-scope-lite"
source .venv/bin/activate
```

> 上の2行は**毎回必要**です。「砂場に入る」工程。

### 2-3. CLI を実行

**還元なしで利益だけ計算する場合:**

```bash
python cli.py ~/Downloads/eresa_export_20260527.csv -o ~/Downloads/eresa_lite.csv
```

**楽天 SPU 5% 込みで実質仕入れ価格まで計算する場合:**

```bash
python cli.py ~/Downloads/eresa_export_20260527.csv -o ~/Downloads/eresa_lite.csv --point-preset rakuten_spu_basic
```

利用できるプリセット：

| プリセット名 | 内容 |
|------------|------|
| `none` | 還元なし（デフォルト） |
| `rakuten_spu_basic` | 楽天 SPU 基本 5% |
| `rakuten_spu_max` | 楽天 SPU + マラソン上限想定 20% |
| `paypay_basic` | PayPay 5% |
| `paypay_max` | PayPay 還元上限想定 15% |

### 2-4. 結果を見る

`~/Downloads/eresa_lite.csv` を Excel または Numbers で開きます。元の ERESA 列の右側に、以下の列が追加されます：

| 列名 | 意味 |
|------|------|
| `profit_fba` | FBA で出した場合の利益（円） |
| `profit_self` | 自己発送（通常宅配）の利益 |
| `profit_mss` | **MSS（マケプレ配送）の利益 ← Lite の本命** |
| `rate_mss_%` | MSS の利益率 |
| `best_mode` | 一番儲かるモード（`fba` / `self` / `self_mss`） |
| `best_profit` | 一番儲かるモードでの利益額 |
| `mss_floor_price` | MSS で利益0円になる最低販売価格（=ここまで値下げ可能） |
| `effective_cost` | 還元込みの実質仕入れコスト |
| `point_back` | 戻ってくるポイント額 |
| `compliance_warning` | 🚨 が付いていたら出品許可申請やリスク確認が必要 |

### 2-5. 仕入れ判断のコツ

1. **`compliance_warning` 列が空の行**から見る（🚨 が付いている行は法務ハルオに相談してから）
2. **`best_mode` が `self_mss`** の行をマーク。ERESA だけ見ていたら気づかなかった金脈の可能性
3. **`best_profit` が想定利益を超える行**を仕入れ候補に
4. **`mss_floor_price` を見て**、Amazon 出品時に値下げ競争に巻き込まれてもどこまで耐えられるかを確認

---

## 3. 動作確認（迷ったらこれ）

「ちゃんと動くか確かめたい」時は、付属のサンプルでテストできます。

```bash
cd "/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260527-002/sato-scope-lite"
source .venv/bin/activate
python cli.py sample_eresa.csv -o /tmp/test.csv --point-preset rakuten_spu_basic
```

`完了: 10 行を処理 → /tmp/test.csv` と表示されれば OK です。

---

## 4. よくあるトラブル

| 症状 | 原因 | 対処 |
|------|------|------|
| `command not found: python3` | Python 未インストール | `brew install python3` または公式サイトから |
| `No module named pandas` | 砂場に入っていない | `source .venv/bin/activate` を実行 |
| `売値列が見つかりません` | CSV の列名が想定外 | カズヨに連絡。`COLUMN_ALIASES` を追加します |
| 利益が全部マイナス | 仕入れ値・手数料の入力が想定と違う | 入力 CSV の `仕入` 列の中身を確認 |

---

## 5. このツールの「やらないこと」

- ERESA の代わりはしません。**候補発見は ERESA でやってから**このツールに渡してください
- 楽天やヤフーから自動で商品を取ってきません（Phase 1 でやろうとして中止）
- スコアリング（🟢🟡🔴 のおすすめ判定）はしません。仕入れ判断は社長の責任

迷ったら**カズヨに「Lite の出力を見て」と一言**ください。一緒に判断します。

---

## 補足：ファイルの場所

| 用途 | パス |
|------|------|
| Lite 本体 | `/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260527-002/sato-scope-lite/` |
| サンプル CSV | 同フォルダ内 `sample_eresa.csv` |
| Phase 1 退避 | `/Users/yukinori/Claude Code/ai-company-amazon_buppan/workspace/output/deliverables/T-20260521-005/archive/satoscope-phase1/` |
| この使い方ガイド | `~/Documents/AI Company Outputs/Amazon物販事業/T-20260527-002/usage-guide.md` |
