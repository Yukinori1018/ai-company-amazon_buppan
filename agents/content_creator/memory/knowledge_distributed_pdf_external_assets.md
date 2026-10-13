# 配布用 HTML→PDF は外部ファイル参照を持たせない（2026-10-13 / T-20260930-001）

## 何が起きたか
会社概要PDF（T-20260817-006/会社概要_配布用）の左上ロゴが「画像切れ」アイコンで、メーカー打診に添付する寸前に社長が発見。
`profile.html` が `assets/logo-mark.svg` を相対参照していたが、配布用フォルダには `assets/` が無い。
公開用フォルダには assets があるため、サイト側では気づけなかった。10/12 の再生成時、自分（ヒデアキ）は PDF を画像で見ていなかった。

## 型
1. **配布用（単体で開く・PDF化する）HTML の画像は data URI で埋め込む。** `<img>` は残し `src` だけ差し替えると、既存 CSS のサイズ指定がそのまま効き、触る範囲が最小になる（インライン SVG だとサイズ CSS を書き足す必要がある）
2. **生成物だけでなくテンプレ（site/profile.html）も直す。** 生成物だけ直すと次の render_public.py／fill.py で再発する
3. **PDF を作ったら必ず pdftoppm で画像化して目で見る。** 加えて `pdftotext` で旧版と diff し、本文が変わっていないことを機械で確かめる
4. 確認コマンド：`grep -n 'src="assets/\|href="assets/' profile.html` が PDF に効く参照で0件であること（favicon は PDF に出ないので許容）

## 手順（再利用）
- 退避：`agent_output/<ticket>/70_work/backup_会社概要_配布用_<YYYYMMDD>/`
- PDF：`Google Chrome --headless --disable-gpu --user-data-dir=<scratch> --no-pdf-header-footer --print-to-pdf=<dst> file://<profile.html>`（fill.py の make_pdf と同じ。`--no-sandbox`＋`rm -rf` を1コマンドに混ぜると権限で拒否されたので分ける）
- 配布用フォルダは住所・電話入りで .gitignore 対象。commit しない
