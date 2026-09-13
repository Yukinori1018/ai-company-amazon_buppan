# 日本の商標の有無を非ログイン・0円で調べる（T-20260912-002 S-e・2026-09-13）

## 1. 経路の結論

| 経路 | 使えるか | 理由 |
|---|---|---|
| J-PlatPat（機械取得） | 使わない | JS 描画で curl/WebFetch は本文0件。INPIT「利用上のご案内」§2 が大量DL・ロボットアクセスを禁止。内部 API を叩く案は取らない |
| 特許庁 特許情報取得 API | 使えない | 令和6年8月9日で新規申込受付終了（ip-data.jpo.go.jp）。申込自体が規約同意＝§4.1 でもある |
| **TMview（EUIPO・JPO 提供データ）** | **使える** | 登録不要・JSON。JP データは detail の `officeLastUpdateDate` で鮮度が分かる（2026-09-13 時点で 09-11） |
| WIPO Global Brand DB / Toreru / IPForce | 未使用 | JS シェルのみ返る（1.7KB）／JS／URL 構造不明。TMview で足りた |

## 2. TMview API の使い方（実測・2026-09-13）

- 検索: `POST https://www.tmdn.org/tmview/api/search/results?translate=true`、`Content-Type: application/json`
  - 商標名: `{"page":"1","pageSize":"100","criteria":"C","basicSearch":"<語>","offices":["JP"]}`
  - 出願人名: `{"page":"1","pageSize":"100","criteria":"C","appName":["<社名>"],"offices":["JP"]}`（**配列**。文字列だと 400。キー名は `applicantName` ではなく `appName`）
  - `criteria:"E"` は 0 件になる（使えない）。`fields` 指定は無視される（現況は一覧に無い）
- 詳細: `GET https://www.tmdn.org/tmview/api/trademark/detail/<ST13>?translate=true`。**cookie（トップページ取得）＋ `Referer: https://www.tmdn.org/tmview/` が無いと 403**。`tradeMark.markCurrentStatusCode`（Registered／Application published／Application refused／Expired／Ended）・`expiryDate`・`applicants[].fullName/fullAddress` が取れる
- オートコンプリート: `GET …/api/search/autocomplete/applicantName?text=<3文字以上>`。**網羅性なし**（七福タオル・金野タオルを返さない）
- 1ページ上限 100 件。`totalResults` > 100 なら打ち切りを表に書く

## 3. 罠

1. **「含む」検索はあいまい一致**。「大橋量器」→「伊良部大橋」が混ざる。取得後に出願人名／商標名の**文字列包含**（NFKC・大小無視）で絞る
2. **短縮キーの取りこぼし**。`appName:["七福タオル"]` は 0 件、`["七福タオル株式会社"]` で 1 件。**0 件は「商標なし」の証明にならない**。0 件は正式名称でも再検索し、それでも 0 なら「TMview 0件・J-PlatPat 要再確認」と書く
3. 一覧の `registrationNumber` あり ≠ 存続。大橋量器の2件は登録5年後に「Ended」（分割納付の後期未納と読める）、木村硝子店の1986年登録は Expired。現況は詳細 API で確認する
4. 全角英数（ＣＯＢＩＴＳＵ）で返る。照合前に NFKC
5. EUIPN Legal notices は学術以外の TDM／スクレイピングを留保。**閲覧目的の数十クエリに留め、定常運用にするならハルオ判定**

## 4. J-PlatPat 手動手順（秘書に渡す型）

商標検索 →「その他の検索キーワード」検索項目「出願人/権利者/名義人」部分一致 → 社名。商標名は「商標（検索用）」が完全一致なので前方一致は末尾 `?`。出典: 特許庁「J-PlatPat の操作方法について」2025-08 p.9〜12、INPIT 講習会 Q&A A10。

## 5. 今回の結果の要点（第一陣20社）

- 自社名義の存続登録商標あり 15社＋窓口会社名義 1社（田中帽子店＝ビスポーク）。TMview 0件 4社（宇野刷毛・木内籐材・清水硝子・本野はきもの）
- Amazon ブランド名と一致する存続商標あり 6社（七福・北尾・廣田(英字)・河野・側島(SOBAJIMA)・田中帽子店(ビスポーク)）、出願中 1社（金野タオル 2025-04）
- **S-d「ブランド登録していないらしい」と「商標を持っていない」は別の軸**。商標はあるがブランド登録していない社（七福・北尾・河野）が3社。A5 が最も素直に通る型
- 独占交渉の相手は商標権者で見る（田中帽子店の商標は窓口会社ビスポーク名義）

## 6. S-b の学び

- 「支払いが保留中」は 2026-09-12 にカズヨが実画面で否定済み（残高 ¥0）。**依頼が来たら先にチケット検索（`grep -rn "保留" workspace/tickets`）**。今回も社内に答えがあった
- 留保ポリシーの一次は非ログイン PDF `m.media-amazon.com/images/G/09/rainier/help/Funds_disbursement_eligibility_policy_JP.pdf`（2024-10-18 発効・異議申立は留保日から60日後）。ヘルプ本文（G9RA9LYBJ3QP27M6）はログイン後のみ
