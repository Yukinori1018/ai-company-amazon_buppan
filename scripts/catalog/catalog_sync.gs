/**
 * catalog_sync.gs — 成果物カタログ書き込み連携（Apps Script Web App）
 *
 * 役割:
 *   ローカル（または将来クラウド）から POST された CSV 文字列を受け取り、
 *   対象シートの中身を全クリアしてからヘッダー＋全行を書き込む「ミラー更新」を行う。
 *   シートの URL を変えずに中身だけ差し替える設計（行追記ではなく全置換）。
 *
 * 認証:
 *   素人なりの共有シークレット方式。Script Property "SHARED_TOKEN" と
 *   POST ボディの token を突き合わせる。一致しなければ 403。
 *   トークンはコードにハードコードせず Script Property から読む。
 *
 * セットアップ（詳細は scripts/catalog/README.md）:
 *   1. このシートを開く → 拡張機能 → Apps Script
 *   2. このコードを貼り付けて保存
 *   3. プロジェクトの設定 → スクリプト プロパティ で SHARED_TOKEN を登録
 *      （任意の長いランダム文字列。後で .env にも同じ値を入れる）
 *   4. デプロイ → 新しいデプロイ → 種類「ウェブアプリ」
 *      実行ユーザー=自分 / アクセス=「全員」（トークンで保護するため）
 *   5. 発行された /exec URL を .env の WEBAPP_URL に貼る
 *
 * 想定 POST ボディ（application/json）:
 *   { "token": "<SHARED_TOKEN>", "csv": "<CSV 全文（改行込み）>", "sheetName": "<任意・省略可>" }
 */

// 既定で書き込むシート名。空文字なら「先頭シート（getSheets()[0]）」を使う。
// POST ボディで sheetName を渡せばそちらが優先される。
var DEFAULT_SHEET_NAME = '';

function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return _json({ ok: false, error: 'no_post_body' }, 400);
    }

    var body;
    try {
      body = JSON.parse(e.postData.contents);
    } catch (parseErr) {
      return _json({ ok: false, error: 'invalid_json' }, 400);
    }

    // --- 認証 ---
    var expected = PropertiesService.getScriptProperties().getProperty('SHARED_TOKEN');
    if (!expected) {
      return _json({ ok: false, error: 'server_token_not_configured' }, 500);
    }
    if (!body.token || body.token !== expected) {
      return _json({ ok: false, error: 'unauthorized' }, 403);
    }

    // --- CSV 取得 ---
    var csv = body.csv;
    if (typeof csv !== 'string' || csv.length === 0) {
      return _json({ ok: false, error: 'empty_csv' }, 400);
    }

    // Apps Script 標準の CSV パーサ。引用符・改行込みセルを正しく扱う。
    var rows = Utilities.parseCsv(csv);
    if (!rows || rows.length === 0) {
      return _json({ ok: false, error: 'csv_parsed_empty' }, 400);
    }

    // --- 対象シート決定 ---
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheetName = body.sheetName || DEFAULT_SHEET_NAME;
    var sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getSheets()[0];
    if (!sheet) {
      return _json({ ok: false, error: 'sheet_not_found', sheetName: sheetName }, 404);
    }

    // --- 全クリア → 全書き込み ---
    sheet.clearContents();

    // 各行の列数が不揃いだと setValues が失敗するため、最大列数に右パディングする。
    var maxCols = 0;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].length > maxCols) maxCols = rows[i].length;
    }
    for (var j = 0; j < rows.length; j++) {
      while (rows[j].length < maxCols) rows[j].push('');
    }

    sheet.getRange(1, 1, rows.length, maxCols).setValues(rows);
    SpreadsheetApp.flush();

    return _json({
      ok: true,
      sheetName: sheet.getName(),
      rowsWritten: rows.length,   // ヘッダー含む
      colsWritten: maxCols
    }, 200);

  } catch (err) {
    return _json({ ok: false, error: 'exception', message: String(err) }, 500);
  }
}

// 動作確認用。デプロイ後にブラウザで /exec を開くと簡単な ping が返る。
function doGet() {
  return _json({ ok: true, service: 'catalog_sync', hint: 'POST JSON to write.' }, 200);
}

// JSON レスポンスを返すヘルパー。
// 注意: Apps Script の Web App は HTTP ステータスコードを任意に設定できないため、
// status はボディに含めるだけ（HTTP 上は常に 200 系）。クライアントは ok フラグで判定する。
function _json(obj, status) {
  obj.status = status;
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
