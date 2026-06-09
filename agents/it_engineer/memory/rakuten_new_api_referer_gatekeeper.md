# 楽天 新ポータルAPI（openapi.rakuten.co.jp / ichibams）の門番＝Origin検証（2026-06-05 実測）

T-20260521-005。Rakuten Ichiba Item Search の 2026 新エンドポイント
`https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260401` の403を実験で解析した結論。

## 実測でわかった門番の仕様（生レスポンスで確定）
- 認証: `applicationId` + `accessKey` をクエリパラメータで渡す（accessKeyはヘッダでも可だが門番はそこではない）。
- 門番が見るのは **HTTPの `Origin` ヘッダ**（Referer ではなく Origin が主）。実験的根拠:
  - `Origin` 無し・`Referer` だけ → `REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING`
  - `Origin=www.rakuten.co.jp` + `Referer=localhost`(矛盾) → それでも判定は Origin 基準
  - `Origin=localhost` → `503 Authentication service error`（＝Originの値は「許可リスト」を通過したが、localhostは認証側で検証不可）
  - `Origin=www.rakuten.co.jp` や `example.com` → `403 HTTP_REFERRER_NOT_ALLOWED`（＝そのアプリの許可リストに無い）
- つまり **`HTTP_REFERRER_NOT_ALLOWED` = 送ったOrigin値がそのアプリの「許可するWebサイト」に登録されていない**。
  ネットの「`https://www.rakuten.co.jp/`を入れれば誰でも通る」裏技は **2026新APIでは塞がれている**（実機で否定済み）。

## 結論: アプリ個別の登録ドメインと完全一致が必須 → 社長の管理画面操作が1つ必要
- 解決はコードでは不可。楽天デベロッパー管理画面でアプリの **「許可するWebサイト」** に
  公開可能なドメイン（例 `https://satoy-select.example.com`）を1つ登録し、
  **同じ値を `Origin`（＝.envの `RAKUTEN_REFERER`）に送る**ことで通る。
- localhost は 503 になるため不可（公開ドメイン必須）。「アプリケーションURL」欄ではなく
  **「許可するWebサイト」欄**が検証対象。

## 実装側の対応（確定済み・honesty設計）
- `adapters/rakuten_shopping.py`: `RAKUTEN_REFERER` を Referer/Origin 両方に送る。未設定/不一致なら
  `is_live=False` でサンプルへ正直にフォールバックし `last_error` に次アクションを残す（403を撒かない）。
- テスト14件パス（実API・Keepaトークン不使用）。.env は gitignore 済み。
- Yahoo は実APIで稼働中なので、楽天が許可待ちでも突合パイプライン自体は止まらない。
