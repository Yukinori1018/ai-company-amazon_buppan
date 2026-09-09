#!/usr/bin/env python3
"""
serve_deliverables.py — 成果物フォルダを社長の Mac の中だけに配信する小さな HTTP サーバ。

なぜ要るのか（1行）:
    Google スプレッドシートのハイパーリンクは `file://` を開けない。
    そこで `http://localhost:<port>/…` で**ローカルの実ファイル**を返す。

配信するもの:
    workspace/output/deliverables/ 配下だけ。ここより上は絶対に出さない。

安全側の作り（この3つは緩めないこと）:
    1. **127.0.0.1 にだけ bind する。** このリポには卸値・取引先名を含む成果物が実在する。
       0.0.0.0 にしたら同じ Wi-Fi の全員に配ることになる。
    2. **配信ルートより上に出るパスは 403。** `..` も、シンボリックリンクの飛び先も、
       最終的な realpath がルート配下かどうかで判定する。
    3. **書き込み系メソッドを持たない。** GET と HEAD だけ。

使い方:
    python3 scripts/catalog/serve_deliverables.py            # 前景で起動（Ctrl-C で停止）
    python3 scripts/catalog/serve_deliverables.py --status   # 起動しているか確認
    python3 scripts/catalog/serve_deliverables.py --port 17325
    python3 scripts/catalog/serve_deliverables.py --root <dir>

    停止（前景でないとき）:
    pkill -f serve_deliverables.py

Mac ログイン時の自動起動は launchd で行う。plist の雛形と手順は
scripts/catalog/com.aicompany.catalog-server.plist.example / README.md を参照。
（設置は社長の承認が要るので、このスクリプトは自分では何も入れない）
"""

from __future__ import annotations

import argparse
import http.server
import mimetypes
import os
import posixpath
import socket
import sys
import urllib.parse

# ── 設定 ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
DEFAULT_ROOT = os.path.join(REPO_ROOT, "workspace", "output", "deliverables")

# ポート 17325 を選んだ理由:
#   - 1024 以上（非特権。sudo 不要）
#   - macOS のエフェメラルポート範囲 49152–65535 の外（OS に横取りされない）
#   - 主要ツールの既定ポート（3000/4000/5000/5173/8000/8080/8787/8888/9000）から離れている
#     ※ 5000 は macOS の AirPlay Receiver、8787 は wrangler dev が使う
#   - IANA 登録の薄い帯で、実務で衝突を見たことがない
# 変更する場合は build_catalog.py の CATALOG_PORT と必ず揃えること（環境変数 CATALOG_PORT）。
DEFAULT_PORT = int(os.environ.get("CATALOG_PORT", "17325"))

# ブラウザで「読ませたい」もの。text/plain で返して画面に出す。
INLINE_AS_TEXT = {".md", ".txt", ".py", ".sh", ".js", ".css", ".gs", ".yml", ".yaml"}
# ブラウザで開かず「保存させたい」もの。Excel 等で開く前提のファイル。
FORCE_DOWNLOAD = {".csv", ".xlsx", ".xls", ".zip", ".pptx", ".docx", ".numbers"}


class DeliverablesHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler に「ルート外を出さない」保証と MIME 調整を足したもの。"""

    server_version = "CatalogServer/1.0"
    root_dir = DEFAULT_ROOT

    # --- パス解決 ---------------------------------------------------------
    def translate_path(self, path: str) -> str:
        """
        URL パス → ローカル絶対パス。

        親クラスの実装は cwd 起点で、かつ `..` の除去に頼っている。
        ここでは root_dir 起点に直したうえで、**最後に realpath で境界を確認**する。
        パーセントエンコードされた日本語（`%E6%88%90%E6%9E%9C`）は unquote で戻る。
        """
        path = path.split("?", 1)[0].split("#", 1)[0]
        trailing_slash = path.endswith("/")
        try:
            path = urllib.parse.unquote(path, errors="surrogatepass")
        except UnicodeDecodeError:
            path = urllib.parse.unquote(path)

        parts = [p for p in posixpath.normpath(path).split("/") if p not in ("", ".", "..")]
        abs_path = os.path.join(self.root_dir, *parts)
        if trailing_slash:
            abs_path += os.sep
        return abs_path

    def _inside_root(self, abs_path: str) -> bool:
        """realpath がルート配下か。シンボリックリンクの飛び先もここで弾く。"""
        root = os.path.realpath(self.root_dir)
        target = os.path.realpath(abs_path)
        return target == root or target.startswith(root + os.sep)

    # --- 応答 -------------------------------------------------------------
    def send_head(self):
        abs_path = self.translate_path(self.path)
        if not self._inside_root(abs_path):
            self.send_error(403, "Forbidden: outside deliverables root")
            return None
        return super().send_head()

    def guess_type(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext in INLINE_AS_TEXT:
            return "text/plain; charset=utf-8"
        if ext in (".html", ".htm"):
            return "text/html; charset=utf-8"
        if ext == ".json":
            return "application/json; charset=utf-8"
        guessed = mimetypes.guess_type(path)[0]
        return guessed or "application/octet-stream"

    def end_headers(self):
        ext = os.path.splitext(self.translate_path(self.path))[1].lower()
        if ext in FORCE_DOWNLOAD:
            name = os.path.basename(self.translate_path(self.path))
            quoted = urllib.parse.quote(name)
            # RFC 5987。日本語ファイル名でも保存名が化けないようにする。
            self.send_header(
                "Content-Disposition", f"attachment; filename*=UTF-8''{quoted}"
            )
        # ローカル専用。検索エンジンにもキャッシュにも渡さない。
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        # 既定の stderr ログは残す（launchd のログに出る）。うるさければ pass にする。
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))


def is_running(port: int) -> bool:
    """そのポートで誰かが listen しているか。TCP 接続を1回試すだけ。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="成果物フォルダをローカル限定で配信する")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--root", default=DEFAULT_ROOT, help="配信ルート（既定: deliverables）")
    ap.add_argument("--status", action="store_true", help="起動しているかだけ確認して終了")
    args = ap.parse_args()

    if args.status:
        up = is_running(args.port)
        print(f"port {args.port}: {'起動中' if up else '停止中'}")
        return 0 if up else 1

    root = os.path.abspath(os.path.expanduser(args.root))
    if not os.path.isdir(root):
        sys.exit(f"[ERROR] 配信ルートがありません: {root}")

    DeliverablesHandler.root_dir = root
    # ThreadingHTTPServer にしておかないと、HTML が読む画像や CSS で詰まる。
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), DeliverablesHandler)
    httpd.daemon_threads = True

    print(f"[OK] 配信ルート : {root}")
    print(f"[OK] URL        : http://localhost:{args.port}/")
    print("[OK] bind       : 127.0.0.1 のみ（LAN には出しません）")
    print("停止は Ctrl-C。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[OK] 停止しました。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
