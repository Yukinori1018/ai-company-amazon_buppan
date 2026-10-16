# 問い合わせフォームの一括入力スクリプト作り（T-20260930-001・2026-10-16）

## 何をしたか（再利用できる手順）
1. 対象URLを CSV から集める（76 の状態列・79 の本文材料・81 の A 判定のうち http で始まる窓口だけ。メール窓口は除く）。
2. **ヘッドレス Chrome の `--dump-dom --virtual-time-budget=10000` で描画後の DOM を取る**（bs4/playwright が無い環境でも動く。xargs -P 8 で並列）。JS 描画のフォーム（formrun・Next.js・Elementor）も取れる。
3. 自作の HTMLParser で input/select/textarea を抜き、**直前40字のテキストをラベル代わり**にする。これで名前がハッシュの欄（松村商店 m7747…）も意味が読める。
4. 項目0件のページは「2段目」を探す：iframe の埋め込み先（smoothcontact・BowNow・form-mailer）、外部フォームへのリンク（太陽油脂→krs.bz）、区分別のサブページ（セイリン /contact/sales_general、ペットライン /business-form/）。
5. 分岐を書いたら **CDP（node の fetch＋WebSocket、追加ライブラリ不要）で実ページに空打ち**する。値を入れて戻り値を見るだけで送信はしない。

## ハマった点
- `document.querySelector('[name="description"]')` は **`<meta name="description">` に当たる**。setter が Illegal invocation で落ちた（日興リカ・セイリン）。**q() は `input,textarea,select` に限定する**。
- 必須欄の検査は**見えている欄だけ・本文と同じ form の中だけ**に絞る。でないとヘッダの検索窓や条件付きで隠れた欄（桂精機の型番欄）が「未入力の必須」に出る。
- **罠の欄（honeypot）**：ケミコートの location/honeypot-37/date、`_wpcf7_ak_hp_textarea`、formrun の `_formrun_gotcha`、EM研究所の h_check_field。**触らない**。ラベルに「空のままに」とあるのが目印。
- form-mailer の埋め込み（pro.form-mailer.jp/fms/…）が **404＝フォーム削除済み**の社があった（新日配薬品）。外から見ると「iframe があるのに空」。
- 迷惑メール対策の合言葉欄（五條良品「五條の霧水と入力」）は CAPTCHA と同じ扱いで**スクリプトでは入れない**（社長が入力）。
- 本文に URL を書くと送れない社（ペンギン食堂）は URL とメールアドレスを抜いた版を用意する。

## 設計の判断
- 戻り値を「本文字数 / 見つからない欄 / 未入力の必須 / 未選択の必須ラジオ」にした。フォームが改修されたら秘書がその場で気づける（黙って一部だけ入る、を防ぐ）。
- 本文欄の maxLength が本文より短ければ自動で短い版に切り替える（社ごとに分岐を書かない）。
- 項目を事前に取れない社（同意しないと出ないフォーム・Cloudflare）は、ラベル推定の汎用入力 `auto()` に回し、戻り値に「要目視」と出す。
- 区分の選択は秘書指定の「取引・卸・法人・その他」順。近いものが無いときは「その他」。迷った選択（ショーワ＝購入方法（代理店等）、ウメケン＝その他）は CSV の注意に残すべきだった→次回は判断理由列を作る。
