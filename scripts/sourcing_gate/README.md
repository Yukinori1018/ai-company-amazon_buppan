# sourcing_gate — 仕入れ前チェックの発注ゲート（T-20261004-001）

CLAUDE.md §3.5 の仕入れ前チェック（**v2・21項目**）が**全部埋まっていない ASIN を、発注案に書かせない**ための仕組み。
文章のルールは発注案を作る瞬間に照合されない（2026-10-04 成果物36 で蛍光灯のゲートが「要確認」のまま推奨に入った）ので、機械で止める。

## 部品

| ファイル | 役割 |
|---|---|
| `checklist_spec.json` | チェック項目の定義（v2・21項目。id・取り方・落とす条件・鮮度日数）。**項目の正はここ**。元は `deliverables/T-20261004-001/checklist_spec_v2.json`（タケシ） |
| `gate.py` | 判定ロジック。フック・pre-commit・`write_order_proposal.py` が共通で使う |
| `check_record.py` | 確認結果を記録・表示・検査する CLI |
| `.claude/hooks/order-gate-guard.py` | PreToolUse（Write/Edit/MultiEdit）。発注案を書く瞬間に止める |
| `.githooks/pre-commit` の `order_gate` | Bash/Python で書いた発注案を commit 時に止める |
| `.claude/hooks/tests/test_order_gate_guard.sh` | 回帰テスト |

記録の置き場：`workspace/output/agent_output/_sourcing_checks/<ASIN>.json`（.gitignore 済み。worktree から使っても**メインの作業ツリー側**の1か所に集まる）。卸値や購入先 URL を書いてよい。

## 使い方

```bash
# 項目の一覧と取り方
python3 scripts/sourcing_gate/check_record.py items

# 1項目ずつ記録（PASS / FAIL / UNKNOWN。出典と確認者は必須。日付の既定は今日）
python3 scripts/sourcing_gate/check_record.py set B01DBGGW8S gate_type \
  --value "ブランド型・書類申請で開く" --result PASS \
  --source "https://sellercentral-japan.amazon.com/productsearch/keywords/search?q=B01DBGGW8S" --by kazuyo

python3 scripts/sourcing_gate/check_record.py show   B01DBGGW8S          # 一覧
python3 scripts/sourcing_gate/check_record.py verify B01DBGGW8S B008FIPMP2  # 発注可なら exit 0
```

## 発注案の書き方

発注案（`workspace/output/` 配下でパスに「発注」「order_proposal」を含む .md/.html/.csv/.tsv/.txt、
または下のマーカーを含む文書）の先頭に、**発注する ASIN を全部**書く。

```
<!-- order-asins: B01DBGGW8S, B008FIPMP2 -->
```

次のどれかに当たると書き込み（と commit）が止まる。

- マーカーが無い／空
- マーカーの ASIN のどれかが、spec の必須項目について **欠落・FAIL・UNKNOWN・期限切れ**
- 発注する ASIN を含む**表の行**に「要確認／未確認／UNKNOWN／不明」が残っている（地の文の注意書きは止めない）

抜け道（例外マーカー・環境変数）は用意していない。記録を埋めれば通る。

## 項目を増やすとき

`checklist_spec.json` の `items` に1要素足すだけ（コードは触らない）。既存 id は変えない（記録が孤児になる）。
鮮度は2段＋1：**市場で動く事実は3日**（§3.3-26「判定データは4日で陳腐化」）、**商品・取引先の属性は14日**（仕入れ先の Amazon 出品可否・FBA 可否/危険物・期限/温度）、**生産終了は7日**。根拠は各項目の `why_age`。`stage`・`origin` キーは説明用で判定には使わない。

項目は ASIN ごとに記録する（アカウント単位の項目は v2 には無い）。「該当しない」項目は根拠を value に書いて PASS（例：`不要：ゲートなし`・`期限なし・常温`）。

## 残っている抜け道

- **マーカー無しの旧い発注案を Bash で書き換えて commit** — pre-commit は既存ファイルの変更をマーカー付きのときしか見ない（自動同期を止め続けないため）
- **商品名だけの表**（ASIN を書かない行）は「要確認」検査に掛からない。ASIN の照合はマーカー側で効く
- 旧スクリプト（`T-20260909-002/order_set.py` `T-20260904-004/build_order_sets.py` 等）は未対応。再実行したら新規ファイル扱いになる名前なら pre-commit で止まる
- `git commit --no-verify` は止められない
