# 担当ZZF：バクマ工業 1社の窓口集め（2026-10-25）

- 事実：公式サイト bakuma.co.jp の製品検索は JS で `ShohinCatalog/data-view.php?keywd=<語>&rdoval=0&dspkbn=0` を読み込む。WebFetch では結果が出ないが、この URL を直接 GET すると一覧が返る。詳細は `data-detail.php?pgrpcd=01&phinban=<品番>`
- 事実：「パラボラ」では0件、品番 `PB-400K` で1件（公式表記は PB400-K・品名は「パラボナ」と誤記）。**品名の語で引けないときは型番で引く**
- 窓口：フォーム（区分にお見積り）・電話・FAX。メール・販売店向け案内なし。営業所13拠点の電話/FAXは eigyo.php
- 手順の再利用形：①recheck の行を起点に ②会社概要・お問い合わせ・営業所の3ページ ③製品検索の裏の ajax URL で商品照合 ④ZZE のヘッダを csv.DictWriter で写して1行書く ⑤公開版は ZZE 公開版のヘッダ（代表の売価・カート保持セラー列なし）でセラー名を伏せる。Web検索は2回で足りた
