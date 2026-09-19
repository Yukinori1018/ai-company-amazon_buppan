# maker_list — メーカーリストに電話番号・HP・品目・EC有無を埋める

社長が「1行見れば電話をかけられる」状態にするための一式です（T-20260920-002 S-F）。
元になったのは T-20260915-003 の `01_メーカー一覧_業界団体名簿.csv`（1,006行）。
このCSVは**社名しか抜いていなかった**ため、社長から「これでは電話がかけられない」と
差し戻されました。同じ名簿ページに電話番号もHPも品目も載っています。

## 使い方（この順に3コマンド）

```bash
python3 scripts/maker_list/build_associations.py   # (a) 名簿から抽出（ネット非接続）
python3 scripts/maker_list/crawl_maker_sites.py    # (b) メーカー自社HPを巡回
python3 scripts/maker_list/merge_list.py           # 統合してCSV/HTMLを出力
```

(b) は時間がかかるので分割実行できます（**1ホストあたりの間隔は変わりません**。
会社ごとにホストが違うため、分割しても相手サーバへの負荷は増えません）。

```bash
W=workspace/output/agent_output/T-20260920-002/S-F
for i in 0 1 2 3 4 5; do
  nohup python3 scripts/maker_list/crawl_maker_sites.py \
    --shard $i --of 6 --out $W/maker_pages_s$i.jsonl > $W/crawl_s$i.log 2>&1 &
done
```

途中で止めても、済んだ社は次回スキップされます（1社ごとに JSONL へ追記）。

## 出力

| ファイル | 中身 | Git |
|---|---|---|
| `…/deliverables/T-20260920-002/out/10_メーカーリスト_全項目.csv` | 監査用。値ごとに出典URLと取得日が付く | **追跡しない** |
| `…/out/11_メーカーリスト_電話用.csv` / `.html` | 社長用。列を11に絞り、優先度順に並べたもの | **追跡しない** |
| `…/out/summary.json` | 充足件数 | 追跡しない |

電話番号入りの完成リストを PUBLIC リポに置いてよいかは未承認のため、
`out/` は `.gitignore` に入れてあります（T-20260831-001 でハルオが挙げた論点1）。

## 構成

```
config.py      取得ポリシー（間隔・UA・時間帯・上限・追ってよいパス）を1箇所に集約
fetcher.py     行儀のよいHTTP取得（robots.txt尊重・ホスト単位の間隔・キャッシュ）
extract/
  phone.py     電話/FAX の抽出・正規化・種別判定（純関数・テストあり）
  ec.py        EC信号とモール出店の判定（純関数・テストあり）
  htmlutil.py  HTML→テキスト、リンク抽出、社名の名寄せ
parsers/
  associations.py  業界団体9名簿のパーサ（1団体1関数。HTMLの作りが全部違う）
build_associations.py  (a) 名簿から抽出
crawl_maker_sites.py   (b) メーカー自社HPを巡回
merge_list.py          統合して2種類のCSV＋HTMLを出力
tests/test_extract.py  27件
```

テスト: `python3 -m unittest discover -s scripts/maker_list/tests -t .`

## 守っている制約（勝手に緩めないこと）

`config.py` の値は法務判定をそのまま写したものです。数字を変える前に判定を確認してください。

- **メーカー公式サイトのみ**低速クロール。robots.txt 尊重・同一ホスト2.5秒以上・UA明示・
  会社概要/問い合わせ系ページ限定・1社最大3ページ（T-20260831-001 Phase B / ハルオ 2026-08-31）
- **楽天・Yahoo!・Amazon には1リクエストも送らない。** モール出店の判定は、
  メーカー自身のHPに貼られた外部リンクを読んでいるだけです。したがってモール列は
  「有」か「未確認」しか取らず、「無」とは書きません（リンクが無いだけかもしれないため）
- **業界団体サイトへの新規アクセスはしていない。** (a) は 2026-09-15 に取得済みの
  保存HTMLを読んでいるだけです。NAPAC と日本金属ハウスウェア（燕）は各社の詳細ページに
  しか連絡先が無く、ここは法務判定（`05_リスト拡充の法務判定.md`）が出るまで保留です
- **個人の携帯番号（070/080/090）は既定で捨てる**（`phone.find_all`）
- gBizINFO は**実装していない**（API利用申請が §4.1 で未承認）。規模区分の列だけ用意して空で通します
