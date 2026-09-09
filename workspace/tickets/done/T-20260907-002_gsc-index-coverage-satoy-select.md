---
ticket_id: T-20260907-002
title: Search Console「インデックス未登録の新しい要因」通知（satoy-select.com）の原因特定と対応
status: done
assignee: secretary
priority: low
created_at: 2026-09-07
updated_at: 2026-09-07
next_check_at: 2026-09-14
requires_approval: false
labels: [website, seo, satoy-select]
related_tickets: [T-20260817-006, T-20260825-001]
---

## 発端

2026-09-07 05:50、Google Search Console から社長宛に通知メール（Message type: WNC-20237597）。

> サイト satoy-select.com のページがインデックスに登録されない新しい要因
> ・代替ページ（適切な canonical タグあり）
> ・ページにリダイレクトがあります

## 調査結果（2026-09-07・カズヨが実測）

**結論：どちらも設計どおりの挙動であり、公開8ページの index 登録を妨げていない。緊急の修正は不要。**

### 要因① 代替ページ（適切な canonical タグあり）＝ www ホスト

| 検証 | 結果 |
|---|---|
| `https://www.satoy-select.com/` | **200**（リダイレクトせず実体を返す） |
| www 側8ページの canonical | すべて `https://satoy-select.com/...`（apex を指す） |

www と apex の両方が同じ中身を 200 で返しているため、Google は www 側を「重複だが canonical が正しく付いている代替ページ」と判定している。**canonical が正しいので apex 側が正規URLとして索引される。** 通知文の「適切な canonical タグあり」がまさにそれ。

### 要因② ページにリダイレクトがあります＝旧 `.html` URL

| 検証 | 結果 |
|---|---|
| `https://satoy-select.com/about.html` | **308** → `/about` |
| `https://satoy-select.com/index.html` | **308** → `/` |
| `http://satoy-select.com/` | **301** → `https://satoy-select.com/` |

Cloudflare Pages が拡張子付きURLを拡張子なしURLへ正規化している。Google が拾った `.html` 付きURLの出所は、旧版サイト（`site_backup_20260820/`）の canonical が `https://{{DOMAIN}}/about.html` だった名残。**現行版は canonical・sitemap・内部リンクとも拡張子なしに統一済み**（公開用フォルダ内の `href="*.html"` は0件、sitemap も8URLすべて拡張子なし）。放置しても旧URLは自然に落ちる。

### 現行構成の健全性（実測）

- `robots.txt`：`Allow: /` ＋ sitemap 宣言あり。ブロックなし
- `sitemap.xml`：8URL（`/` `/partners` `/guides` `/guide-cutting-board` `/guide-bottle` `/business` `/about` `/contact`）。すべて 200
- 内部リンクに `.html` 残存：0件

## 残タスク（社長判断が必要 → waiting）

**www → apex の 301 リダイレクトを設定するか。**

- やる価値：Search Console のこの警告が消え、重複ホストがなくなる。リンク評価も apex に一本化される
- やらない場合の実害：**ほぼ無い**（canonical が正しく効いているため）
- 実装：Cloudflare ダッシュボードの Redirect Rules（Single Redirect）で `hostname eq "www.satoy-select.com"` → `https://satoy-select.com/${path}` を 301。Pages 側の `_redirects` ではホスト単位の分岐ができないためダッシュボード設定になる
- 制約：**Cloudflare アカウントへのログインは社長の一手**、かつアカウント設定変更のため §4.1 に準じて承認を取る

→ 社長の Go が出れば、ログインだけお願いしてカズヨが設定を入れる。

## ログ

- 2026-09-07 カズヨ：メール受領 → 原因特定（curl による実測）→ 「実害なし」と判定。www 301 の可否のみ社長判断待ちとして waiting へ
- 2026-09-07 マリエ：Notion カンバンへ新規カード作成（waiting 列 / page 3d4b0a40-44fa-8110-86e3-e5be348bcbe9）。labels は Notion の選択肢に合わせて `homepage`→`website`、`search-console`→`seo` へ統合し、`website` `seo` `satoy-select` の3オプションを新設（既存44件を全保持して47件へ）。owner-tasks.md に社長タスク1件（www→apex 301 の Go/NoGo）を追記

---

## 対応完了（2026-09-07・社長ログイン → カズヨが設定）

### Search Console の実データ（当初の見立てを訂正）

`.html` 付き旧URLは**1件も含まれていなかった**。未登録4件は**すべて www ホスト**。

| 区分 | 件数 | 実際のURL |
|---|---|---|
| 登録済み | 9 | 公開ページは正常に索引済み |
| 代替ページ（canonical あり） | 3 | `https://www.satoy-select.com/contact` `/business` `/` |
| ページにリダイレクトがあります | 1 | `http://www.satoy-select.com/` |

→ 当初「`.html` の名残」と推測して報告したが、**実データと違った。推測を事実として書いた誤り。**

### 実施したこと

Cloudflare ダッシュボード → satoy-select.com → Rules → Redirect Rules で、テンプレート「WWWからルートへのリダイレクト」から Single Redirect を1本デプロイ。

- ルール名: `WWWからルートへのリダイレクト [テンプレート]`
- リクエストURL: `https://www.*`（ワイルドカードパターン）
- 対象URL: `https://${1}` / ステータスコード **301**
- **「クエリ文字列を保持する」にチェック**（utm 等のパラメータを落とさないため）
- デプロイ時に「DNS が www をプロキシしていない可能性がある」警告が出たが、www は実際に応答していたため *Ignore and deploy rule anyway* を選択 → **実測で正常動作を確認済み**

### 検証（デプロイ15秒後・curl 実測）

| URL | 結果 |
|---|---|
| `https://www.satoy-select.com/` | 301 → `https://satoy-select.com/` |
| `https://www.satoy-select.com/contact` | 301 → `https://satoy-select.com/contact` |
| `https://www.satoy-select.com/business` | 301 → `https://satoy-select.com/business` |
| `https://www.satoy-select.com/guides?utm_source=test` | 301 → `…/guides?utm_source=test`（**クエリ保持 OK**） |
| `http://www.satoy-select.com/` | 301 → `https://www.satoy-select.com/`（→ さらに apex へ。2ホップ） |
| `https://satoy-select.com/` `/contact` | **200**（apex は影響なし） |

Search Console 側では「代替ページ（適切な canonical タグあり）」の**修正の検証を開始**（2026-09-07 開始）。

### 残る注意点（誤解しないための記録）

**「未登録4件」は今後もゼロにはならない。** www の4URLは「代替ページ」から「**ページにリダイレクトがあります**」へ分類が移るだけで、未登録カウントには残り続ける。これは**正しい最終形**であってエラーではない。リダイレクト先の apex が索引されていれば目的は達成されている。

→ 「未登録が消えない」を理由に再度いじらないこと。

## ログ

- 2026-09-07 カズヨ：メール受領 → curl で原因特定 → 「実害なし」と判定。www 301 の可否のみ社長判断待ちとして waiting へ
- 2026-09-07 カズヨ：Search Console 実データで当初の見立てを訂正（`.html` 由来はゼロ、全4件が www）
- 2026-09-07 社長：Cloudflare へログイン（本人にしかできない一手）
- 2026-09-07 カズヨ：Redirect Rule をデプロイ → curl 6パターンで動作確認 → GSC で修正の検証を開始 → **done**


## 2026-09-09 採番の訂正

本チケットは起票時に **T-20260907-001** を名乗っていたが、同 ID が `doing/T-20260907-001_pack-size-resolution.md`（入数突合）と重複していた。Notion は 1 ID につき 1 枚しか持てないため、**稼働中の pack-size 側がボードに出せない**状態になっていた。

**本チケット（完了済み・成果物フォルダなし）を T-20260907-002 へ振り直す。** pack-size 側は `workspace/output/deliverables/T-20260907-001/` を保有しているため動かさない。

## 成果物

（なし — 外部での手続き・作業が成果のため、成果物ファイルなし）
