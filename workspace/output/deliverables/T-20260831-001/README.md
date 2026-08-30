# T-20260831-001 成果物インデックス

| ファイル | Phase | 担当 | 中身 |
|---|---|---|---|
| `A_連絡先取得手段の棚卸し.md` / `.html` | A | リサーチャー サトル | **取得手段15種＋検索API7種の評価。英字526社／和名293社に分けたカバー率、実費、社長の手が要る申請。実測データつき** |
| `A_data/` | A | リサーチャー サトル | 実測データ4本（英字526社の日本シグナル判定・ドメイン推測237社・822社分類） |
| `B_連絡先収集の適法性判定.md` / `.html` | B | 法務ハルオ | **取得手段8種の可 / 条件付き可 / 不可 判定。実装制約はそのままコードに写せる粒度。先に読むこと** |
| `README.md`（本ファイル以下） / `run.py` / `pipeline/` / `tests/` / `state/` | C | IT タカシ | 連絡先エンリッチメント・パイプラインの骨格 |
| `contacts_v1.csv` | C | IT タカシ | 822社の連絡先CSV（現時点で埋まっているのは14社） |

> **実装前に Phase B の §10「実装してよい手段／使ってはいけない手段」と §4-4・§9-3 の制約を読んでください。** Amazon と Google 検索スクレイピングは **不可** です。
>
> **Phase A の要点（実装順）：** ①和名293社は国税庁 全件データ（0円・申請不要）→ gBizINFO（`company_url`）。②英字526社は公的DBが原理的に効かないので、`A_data/英字ブランド_日本シグナル.csv` の「日本シグナルあり145社」に絞る。③公式HP探索は **Gemini API の Grounding with Google Search（月5,000リクエスト無料）** が Google Custom Search の正規代替。**推奨構成の実費は0円。**

---

# メーカー連絡先エンリッチメント・パイプライン（T-20260831-001 / Phase C）

822社の連絡先欄を埋めるための骨格。**外部ソースはまだ1つも入っていません**（サトルの手段調査・ハルオの適法性判定が未確定のため）。ソースが決まったら `resolvers/` に1ファイル足すだけで動きます。

## いま出ている数字

| 項目 | 値 |
|---|---|
| 入力 | 822行（`T-20260817-005/v14/03_メーカー名寄せ.csv`） |
| 連絡先が1つ以上埋まった社 | **14社（1.7%）** |
| 内訳 | 公式HP 14 / 電話 9 / 問い合わせフォーム 12 / メール 2 |
| 埋まった根拠 | 既取得55社（T-20260804-001）とのマッチのみ。**新規取得はゼロ** |
| 名寄せ取りこぼし | 12ペア（822行の実体は810社。`state/STATUS.json` に一覧） |

### 822社の分類内訳

| 分類 | 件数 | 埋まり | 意味・効きそうなソース |
|---|---:|---:|---|
| 和名法人らしき | 289 | 13 | 日本の公的DB・和名検索が効く。本命 |
| 英字ブランド | 528 | 1 | ブランド名のみ。**法人を特定する一段階が要る**（最大の難所） |
| ノーブランド・個人らしき | 3 | 0 | 実体なし。**やっても引けない。捨ててよい** |
| 海外法人 | 2 | 0 | `CO.,LTD` 等が明示されている社のみ |

> 「英字ブランド」528の中には日本企業（`DUNLOP` `KADOKAWA`）と中国系（`Gudluky` `HUAKUA`）が混在しています。名前だけでは分けられないので、分類はここまで。分けるのは resolver の仕事です。

## 使い方

```bash
python3 run.py                  # 全件（処理済みはスキップ）
python3 run.py --limit 20       # 20社だけ試す
python3 run.py --list           # 登録済み resolver 一覧
python3 run.py --rebuild-csv    # state から CSV を作り直す（再取得しない）
python3 -m unittest discover -s tests   # テスト 65件
```

外部ライブラリなし（Python 3.9 標準ライブラリのみ）。

## ファイル

| パス | 中身 |
|---|---|
| `contacts_v1.csv` | 初期版。822行 × 15列。**社長・マリエが見るのはこれ** |
| `run.py` | エントリポイント |
| `pipeline/config.json` | ソース・アクセス間隔・ネットワーク可否の設定 |
| `pipeline/normalize.py` | 正規化・別名抽出・分類 |
| `pipeline/schema.py` | 列定義・確度・分類の定数 |
| `pipeline/merge.py` | 複数ソースの優先順位マージ |
| `pipeline/throttle.py` | ソース別アクセス間隔 |
| `pipeline/store.py` | 逐次保存・再開 |
| `pipeline/runner.py` | 本体ループ |
| `pipeline/resolvers/base.py` | resolver インターフェース＋レジストリ |
| `pipeline/resolvers/seed_contacts.py` | 既取得55社（オフライン） |
| `pipeline/resolvers/TEMPLATE_source.py` | **新ソースはこれをコピーして作る** |
| `state/records.jsonl` | 正データ（追記のみ）。CSV はここからの派生物 |
| `state/STATUS.json` | 進捗・埋まり率・名寄せ取りこぼし一覧 |

## 設計の要点

| 要件 | やり方 |
|---|---|
| 推測で埋めない | 取れなければ空欄＋`備考`に理由。`確度`は寄与ソースの**最弱**に合わせる |
| 冪等・再開可能 | 1社ごとに `records.jsonl` へ追記＋fsync。再実行で処理済みはスキップ |
| 電源断耐性 | 書きかけの壊れた最終行は読み飛ばして続行 |
| ソース差し替え | 1ソース=1モジュール。`resolve(MakerRow) -> ContactFields` だけ実装 |
| 優先順位マージ | 人手確認(5) > 公的DB(10) > 公式サイト(20) > 検索(30)。列ごとに強い方が勝ち、空欄は勝てない |
| アクセス間隔 | `throttle.py` で共通管理。秒数は `config.json`。resolver に sleep を書かせない |
| 法務ゲート | `allow_network: false` の間、`needs_network=True` の resolver は起動時に拒否 |

## 新しいソースの足し方（3ステップ）

1. `cp pipeline/resolvers/TEMPLATE_source.py pipeline/resolvers/<source>.py` → `resolve()` を実装
2. `pipeline/resolvers/__init__.py` に `from . import <source>` を1行足す
3. `pipeline/config.json` の `enabled` に名前、`throttle` に間隔（秒）を足す

外部に出る resolver は `needs_network = True` を立てること。ハルオの判定が出て `allow_network: true` にするまで実行されません。

## 制約・未了

- **外部アクセスは1回も行っていません。** Phase A（サトル）/ B（ハルオ）の結果待ちです
- 有料DBの契約・申込は §4.1（金銭）につき未実施
- 3,282社（`maker_ledger.csv`）への拡張は `config.json` の `input_csv` を差し替えるだけで動きますが、今回は走らせていません
- Googleシート反映は Phase D（マリエ）の担当
