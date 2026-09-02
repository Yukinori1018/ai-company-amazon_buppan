# 外部ソースの取り込み

YouTube・X から情報を取る必要が生じたときだけ読む。

## YouTube｜話の中身が欲しいとき（安い）

```bash
# 1. 候補をリスト化
yt-dlp "ytsearch30:〔キーワード〕" --skip-download \
  --print "%(id)s|%(upload_date)s|%(view_count)s|%(channel)s|%(title)s"

# 2. 選んだIDだけ字幕を取得（動画は落とさない）
yt-dlp --skip-download --write-auto-subs --write-subs \
  --sub-langs "ja" --convert-subs srt \
  -o "research/subs/%(id)s.%(ext)s" "URL"

# 3. タイムスタンプと重複行を除去
sed -e '/-->/d' -e '/^[0-9]*$/d' -e '/^$/d' file.srt | awk '!a[$0]++' > file.txt
```

`--list-subs URL` で字幕の有無を先に確認できる。
失敗し始めたら `pip install --upgrade yt-dlp`。

**自動字幕は固有名詞と数字を高確率で誤認する。**
字幕由来の数値は `字幕由来＝要検証` とマークし、概要欄か公式サイトで
裏取りするまで結論に使わない。

## YouTube｜画面の図表・実演が要るとき

Gemini API の YouTube URL 機能。2026年8月時点でプレビュー・課金なし。

- 無料枠は1日8時間分まで、公開動画のみ
- Gemini 2.5以降は1リクエスト最大10本
- トークンは動画1秒あたり約300。`media_resolution: low` で約100
- 話の中身を掴むだけなら low で十分
- 重い解析は1回だけ。JSONで書き出し、以降の加工は軽量モデルで

APIキーは AI Studio で取得。Google AI Pro の契約とAPI課金は別会計。
実際のレート制限は AI Studio のプロジェクト画面で確認する。

## YouTube Data API｜候補の選別

- 1日10,000ユニット。`search.list` は100、`videos.list` は1
- 特定チャンネルの動画一覧は uploads プレイリストに
  `playlistItems.list`（100→1ユニット）
- **他人の動画の字幕は取得不可**（captions は動画所有者のOAuthが必要）

## X

2026年以降は従量課金（読み取り約$0.005/件、最低$5）。
x.com は WebFetch がログイン壁でほぼ通らない。

**割り切り方**：X は一次ソースの在り処を見つける場所。
気になったポストの**リンク先**を raw に貯め、そちらを WebFetch する。

## Gemini CLI

2026年6月18日に個人向け（無料・AI Pro・AI Ultra）の提供が終了。
後継は Antigravity CLI（`agy`）。有料APIキー経由なら Gemini CLI は継続利用可。
