# HP（satoy-select.com）を部分修正して出し直す手順

- 2026-10-05 / T-20260930-001（食品の取扱い文言修正・電話番号追加）で実施

## 構造（ここを知っていれば迷わない）
- テンプレ：`workspace/output/deliverables/T-20260817-006/site/`（Git追跡・PUBLIC）。個人情報は `{{TEL}}` `{{OWNER_NAME}}` `{{EMAIL}}` 等のプレースホルダ
- `site/fill.py`（対話式）がテンプレ → `公開用/`（本番に上がる・gitignore）と `会社概要_配布用/`（profile.html＋PDF・gitignore・アップロードしない）を生成
- 本番＝`公開用/` そのもの（2026-10-05 時点で live と完全一致を curl で確認済み）
- `deploy.sh`（既定はチェックのみ／`--deploy` で wrangler pages deploy）

## 電話番号などの本人特定情報をリポに載せない方法
- **最初から設計済み**：テンプレは `{{TEL}}` のまま。値は fill.py 実行時の入力→gitignore側の生成物にだけ入る。新しい仕組みは不要だった
- fill.py は空欄の項目の行ごと消す（`strip_empty_blocks`）。8/23 は TEL 空で生成したので about.html・profile.html から電話行が消えていた
- **fill.py を再実行しない**：対話入力（フォームURL・GSCトークン等）を全部再現する必要があり、取り違えると本番が壊れる。部分修正は「テンプレを直す＋生成物に同じパッチ」で行い、`count==1` を assert してから置換する
- PDF だけの再生成は `python3 -c "import sys; sys.path.insert(0,'site'); import fill; print(fill.make_pdf())"`（T-20260817-006 ディレクトリで実行。headless Chrome で1〜2分かかる＝Bash は run_in_background で）。確認は `pdftotext`

## 詰まった点
- **wrangler の OAuth トークンは失効する**（8/23 ログイン → 10/05 失効）。非対話環境では `wrangler login` できず、`CLOUDFLARE_API_TOKEN` も無い → デプロイ不能
  - 再ログインは社長の承認クリック（OAuth）＝本人にしかできない一手。認証待ち約2分なので社長の在席確認から（T-20260823-002 の教訓）
  - 恒久策の候補：Pages 編集権限だけの API トークンを作り `~/.config/satoy-select/cloudflare.env` に置く（作成は社長の手作業・無料）。次回のデプロイ前に提案する価値あり
- 「受付時間：平日 10:00〜18:00」はテンプレの既存文言。社長の携帯なので実態と合っているかは社長確認事項
- 2026-10-05 追記：受付時間はカズヨ判断で「不在時は折り返しご連絡します」に変更（社長は本業中に電話に出られない）。テンプレ about/profile と生成物の両方を差し替え、PDF 再生成済み
