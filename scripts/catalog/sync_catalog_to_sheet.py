#!/usr/bin/env python3
"""
sync_catalog_to_sheet.py — 成果物カタログ CSV を Google スプレッドシートへ反映する。

仕組み:
  マスター CSV を読み込み、Apps Script Web App（catalog_sync.gs）の /exec URL へ
  JSON で POST する。Web App 側がシートを全クリア → 全行書き込み（ミラー更新）する。
  シートの URL は変わらない。

設定:
  scripts/catalog/.catalog_sync.env（gitignore 対象）に KEY=VALUE 形式で記述:
      WEBAPP_URL=https://script.google.com/macros/s/XXXX/exec
      SHARED_TOKEN=<Apps Script の Script Property と同じ値>
      SHEET_NAME=<任意。省略可。空なら Web App 側の先頭シート>

依存:
  Python 標準ライブラリのみ（urllib）。pip 追加インストール不要。

使い方:
  python3 scripts/catalog/sync_catalog_to_sheet.py            # 実送信
  python3 scripts/catalog/sync_catalog_to_sheet.py --dry-run  # 送信せず内容確認
  python3 scripts/catalog/sync_catalog_to_sheet.py --csv <path>  # CSV を指定
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# このスクリプトからの相対でリポジトリ構造を解決する。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
ENV_PATH = os.path.join(SCRIPT_DIR, ".catalog_sync.env")
DEFAULT_CSV = os.path.join(
    REPO_ROOT,
    "workspace", "output", "deliverables",
    "T-20260601-001", "deliverables-catalog.csv",
)


def load_env(path):
    """KEY=VALUE 形式の .env を素朴にパースする（標準ライブラリのみ）。"""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            # 値の前後の引用符を剥がす
            value = value.strip().strip('"').strip("'")
            env[key.strip()] = value
    return env


def read_csv_text(csv_path):
    if not os.path.exists(csv_path):
        sys.exit(f"[ERROR] マスター CSV が見つかりません: {csv_path}")
    with open(csv_path, "r", encoding="utf-8") as f:
        text = f.read()
    return text


def summarize(csv_text):
    """送信予定の行数・先頭2行をプレビュー用に整形する。"""
    lines = [ln for ln in csv_text.splitlines() if ln.strip() != ""]
    total = len(lines)
    header = lines[0] if lines else "(空)"
    first_data = lines[1] if len(lines) > 1 else "(データ行なし)"
    data_rows = max(total - 1, 0)
    return total, data_rows, header, first_data


def main():
    parser = argparse.ArgumentParser(description="成果物カタログをスプレッドシートへ同期")
    parser.add_argument("--csv", default=DEFAULT_CSV, help="送信するマスター CSV のパス")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="送信せず、送信予定の行数・先頭行のみ表示する",
    )
    args = parser.parse_args()

    csv_text = read_csv_text(args.csv)
    total, data_rows, header, first_data = summarize(csv_text)

    print(f"[INFO] CSV: {args.csv}")
    print(f"[INFO] 総行数（ヘッダー込み）: {total}  / データ行: {data_rows}")
    print(f"[INFO] ヘッダー: {header[:120]}")
    print(f"[INFO] 先頭データ行: {first_data[:120]}")

    env = load_env(ENV_PATH)
    webapp_url = env.get("WEBAPP_URL", "").strip()
    token = env.get("SHARED_TOKEN", "").strip()
    sheet_name = env.get("SHEET_NAME", "").strip()

    # --dry-run、または URL 未設定なら送信しない（親切に案内する）。
    if args.dry_run or not webapp_url:
        if not args.dry_run and not webapp_url:
            print()
            print("[DRY-RUN] WEBAPP_URL が未設定のため送信しません。")
            print(f"          設定ファイル: {ENV_PATH}")
            print("          手順は scripts/catalog/README.md を参照してください。")
            print("          見本: scripts/catalog/.catalog_sync.env.example")
        else:
            print()
            print("[DRY-RUN] --dry-run 指定のため送信しません。")
        print(f"[DRY-RUN] 送信予定: {total} 行（ヘッダー含む）を全置換で書き込み。")
        return 0

    if not token:
        print()
        sys.exit(
            "[ERROR] SHARED_TOKEN が未設定です。"
            f"\n        {ENV_PATH} に SHARED_TOKEN を設定してください。"
            "\n        （Apps Script の Script Property と同じ値）"
        )

    payload = {"token": token, "csv": csv_text}
    if sheet_name:
        payload["sheetName"] = sheet_name

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webapp_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print()
    print(f"[INFO] POST 送信中: {webapp_url}")
    try:
        # Apps Script は 302 リダイレクトを挟むことがあるが urllib は追従する。
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[INFO] HTTP {resp.status}")
            _print_result(body, total)
            return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[ERROR] HTTP {e.code}")
        print(f"[ERROR] レスポンス: {body[:500]}")
        return 1
    except urllib.error.URLError as e:
        print(f"[ERROR] 接続失敗: {e.reason}")
        print("        WEBAPP_URL が正しいか、デプロイのアクセス権が「全員」か確認してください。")
        return 1


def _print_result(body, expected_total):
    """Web App の JSON レスポンスを解釈して成否を表示する。"""
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        # 認可ページの HTML が返るケース（アクセス権設定ミス等）
        print("[WARN] JSON でないレスポンスを受信しました（認可/アクセス権の可能性）:")
        print(body[:500])
        return
    if result.get("ok"):
        print(
            f"[OK] 同期成功: シート='{result.get('sheetName')}', "
            f"書き込み {result.get('rowsWritten')} 行 x {result.get('colsWritten')} 列"
        )
        if result.get("rowsWritten") != expected_total:
            print(
                f"[WARN] 送信予定 {expected_total} 行と書き込み行数が一致しません。"
                " 空行の扱いを確認してください。"
            )
    else:
        print(f"[ERROR] Web App がエラーを返しました: {result.get('error')}")
        if result.get("message"):
            print(f"        詳細: {result.get('message')}")


if __name__ == "__main__":
    sys.exit(main())
