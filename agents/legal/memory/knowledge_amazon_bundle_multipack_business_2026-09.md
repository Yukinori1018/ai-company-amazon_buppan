# Amazon セット品・まとめ売り・バーチャルバンドル・Bulk Service・Amazon Business の規約判定 — 結論と取得ノウハウ

初出：T-20260914-001（2026-09-14 ハルオ）。成果物 `workspace/output/deliverables/T-20260914-001/03_セット品規約と法人向け梱包_法務判定.md`。
9/13 判定（`knowledge_composite_strategy_legal_check_2026-09.md` A1）の「Amazon セット商品ポリシーは推測」を一次で埋めた回。

---

## 1. 再利用できる結論

| 手法 | 結論 | 決め手 |
|---|---|---|
| 異なる商品のセット（セット品） | 条件付き可 | 固有 JAN 必須（構成品 JAN 流用＝即時削除）。「complementary」＝使用を可能/強化 or 一緒に買うと便利。ブランド混在は可、禁止はジェネリック品混入。セットのブランド欄＝最高額構成品のブランド。作成後の構成変更不可。返品はセット一括。手数料は主商品カテゴリ |
| Satoy Select をセットのブランド欄に書く | 不可（SG 一次・JP 未確認） | "the bundle itself should be branded according to the highest priced item"。JP 実務はノーブランド申請。Satoy Select は販売者表示に留める |
| 同一商品 N 個パック | 可（IPQ ルート） | セット品ではなく「まとめ売り」。Amazon モデレーター FAQ：メーカー包装の JAN のまま商品パッケージ数を入力＋商品名に数量明記。ブランド認証不要。手数料割引なし |
| Amazon Bulk Service（旧 Amazon一括サービス）の 15〜25% 割引 | 条件付き可、当社の本丸では不可 | News_Amazon 2025-01-25：パッケージヒエラルキー作成に「ブランド認証が必要」、構成ごとに固有 GTIN、3,000 円（税込）以上＋（10 点以上 or 23,000cm³ or 16kg）。ブランド未登録メーカーの品では組めない |
| バーチャルバンドル | 日本提供あり／メーカー品の組み合わせには不可 | News_Amazon（9 か月前）「ブランド登録済み ASIN をまとめて販売」。自分がブランド所有者の ASIN 限定・FBA 新品・2〜5 点。当社の商標登録は Satoy Select の ASIN にしか効かない |
| Amazon Business 参加 | 可（規約同意＝§4.1） | sell.amazon.co.jp「大口プランの出品用アカウントがあれば追加費用なし」。法人価格は 5% OFF 以上推奨。適格請求書は登録番号があるときだけ Amazon が発行（当社はインボイス未登録＝法人購買者に不利。経理論点） |
| 外箱＋固有 JAN のセット（個装を開けない） | 条件付き可 | 表示 4 点：販売者/製造者の書き分け（PL 2 条 3 項 2 号回避）、化粧品は薬機法 62 条→51 条準用で 61 条事項を外箱に再掲（透明外装なら不要）、計量法 13 条の「密封」に当たれば内容量＋氏名住所、家表法表示 |
| 個装を開ける・詰め替え・小分け | 不可 | 化粧品は薬機法 13 条（製造業許可）。その他も PL 2 条 3 項 1 号「加工」・商標の品質保証機能 |
| メルカリ・ヤフオクの成約履歴を人が見て記録 | 条件付き可（確度中） | メルカリ規約 8 条は「本サービスに接したユーザー及び第三者」に禁止行為を適用＝非会員にも及ぶ。ガイド 900「弊社のサービス外のところで、商業目的で…情報…を利用」が広い。数値のみ手で記録・転記なし・社内限定・自動不可。差止通知で即中止 |

## 2. 取得ノウハウ

| 対象 | 通る | 通らない |
|---|---|---|
| Amazon 出品規約の英語全文 | `https://m.media-amazon.com/images/G/65/rainier/help./Product_Bundling_Policy.pdf`（Amazon ホスト・SG 店）。WebSearch で `"Product Bundling Policy" full text` を引くと出る。**`m.media-amazon.com/images/G/<店番号>/rainier/help./<Policy>.pdf` は他の規約でも試す価値あり**（G/09 日本は 404 だった） | `sellercentral.amazon.{co.jp,com,ca}/help/hub/reference/external/<ID>`・`/gp/help/external/<ID>`・`help.html?itemID=`・`?language=ja_JP`・`?mons_sel_locale=`・Googlebot UA：全部 SPA の殻（200・`<title>Amazon</title>`） |
| Amazon 自身の日本語一次 | **セラーフォーラム**（`sellercentral.amazon.co.jp/seller-forums/discussions/t/<id>`）は curl で本文が取れる。`News_Amazon`／`Forum_Moderator` の投稿は Amazon の発言として一次に使える。WebSearch `site:sellercentral.amazon.co.jp <語>` で当てる | 出品者の回答は二次（規約の逐語引用でも転記精度は保証されない） |
| ヘルプ ID の特定 | フォーラム HTML から `grep -o 'G[0-9A-Z]\{6,\}'`。今回：G200492770（セット品 UPC ガイドライン）／G200494020（IPQ）／G87HAE6PMKKM23Z7（バーチャルセット品）／GG7X74YD2PZLZN9R（バーチャルバンドル売上レポート）／201740310（法人限定出品）／G200141500（FBA 梱包要件）／GQ4S7SV9K4GXH3WX（package hierarchies・US） | — |
| e-Gov 法令 API | `https://laws.e-gov.go.jp/api/1/lawdata/<法令ID>`（`elaws.e-gov.go.jp` は 301。curl に `-L` 必須。9/13 に取れていたのは -L 付きだったから） | `elaws.e-gov.go.jp/api/1/...` を -L 無しで叩くと 0 byte |
| メルカリ規約 | `https://www.mercari.com/jp/tos/` → `static.jp.mercari.com/tos`（538KB・本文あり）。ガイドは `help.jp.mercari.com/guide/articles/<n>/`（900＝その他不適切、prohibited_conduct＝一覧） | `jp.mercari.com/tos`＝404 |
| LINE ヤフー共通利用規約 | `https://www.lycorp.co.jp/ja/company/terms/` curl 可（§2.1・2.2・14） | — |

## 3. 型として固定したもの

1. **「規約はログイン後」で止めない。** 同じ規約の他国版が Amazon 自身のホストに PDF で置かれていることがある。日本版と構造が一致すれば「翻訳と見る・確度中」で判定を出し、JP 本文は秘書ブラウザの消し込み対象にする。
2. **Amazon の機能は「誰のブランドか」で使える範囲が変わる。** バーチャルバンドル・Bulk Service・（9/13 の）ブランド登録は全部「自分が所有するブランドの ASIN」が前提。当社の本丸（ブランド未登録メーカーの品の再販）には効かない。他 AI の資料は「ブランド登録後は使える」と書きがちだが、当社の商標は Satoy Select の ASIN にしか効かない。
3. **セットの「ブランド」と「販売者」を混ぜない。** 商標を取っても、メーカー品セットのブランド欄に自社名は書けない（SG 規約・商標法・不競法の三重）。自社名は「販売者：」の表示に留める。
4. **外箱で法定表示を隠すなら外箱に再掲。** 薬機法 51 条準用の「透かして容易に見ることができないとき」が判定軸。透明シュリンクは楽、不透明箱は表示作業が増える。
5. **フリマ規約は「非会員にも及ぶ」書き方が標準**（メルカリ 8 条「接したユーザー及び第三者」、LINE ヤフー 2.2）。「会員でないから規約は関係ない」は Makuake 型（1 条で会員と利用者を分ける）にしか使えない。9/13 の型 1 に例外を追加。

## 4. 依頼範囲外で見つけた指摘（秘書へ）

- PDF p.8 の 3 記述は条件が抜けている（バーチャルバンドル＝自社ブランド ASIN 限定／大口梱包の割引＝ブランド認証＋固有 GTIN＋3,000 円・10 点等／ブランド混在は違反ではない）。
- Amazon Business の適格請求書は当社のインボイス未登録（免税事業者「いいえ」設定）だと発行されない。法人購買者の仕入税額控除に不利。登録すれば納税義務。ハジメの論点。

## 5. 未確認のまま残した最大のもの

JP セット品規約 G201645990 本文（ブランド欄の扱い・タイトル文言の日本語版・審査の実務）と Business Essentials GVWZ8QXXLY9Y9Z4B。BSA §4.2・§19・Agent Policy（9/13 §6）も継続未取得。次の法務案件でログイン後に取る。
