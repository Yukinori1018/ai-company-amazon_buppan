---
ticket_id: T-20260907-001
title: Search Console「インデックス未登録の新しい要因」通知（satoy-select.com）の原因特定と対応
status: waiting
assignee: secretary
priority: low
created_at: 2026-09-07
updated_at: 2026-09-07
next_check_at: 2026-09-10
requires_approval: true
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
