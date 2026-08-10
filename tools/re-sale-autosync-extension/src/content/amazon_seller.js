/**
 * セラーセントラルの content script。
 *  1) 注文管理ページを開いていると、新規注文の SKU/注文ID/数量を拾って background へ送る
 *     → background が該当 SKU の購入タスクを作成（半自動購入のトリガ）。
 *  2) 在庫管理ページで background からの SET_STOCK 指示を受け、該当 SKU の在庫数を変更（best-effort）。
 *
 * ※ セラーセントラルの DOM 構造は変わりやすく地域/画面で異なるため、セレクタは実画面に合わせて
 *   要調整（TODO）。Amazon は UI 自動化を推奨しないため、確実性重視なら将来 SP-API 併用が望ましい。
 */
(function () {
  var href = location.href;

  // ---- 1) 注文の読み取り ----
  function scrapeOrders() {
    // TODO: 実際の注文管理ページの行セレクタに合わせる。
    // ここでは data 属性や見出しから SKU と 注文ID を拾う汎用ロジックの雛形。
    var rows = document.querySelectorAll('[data-test-id="order-card"], .order-card, tr.order-row');
    var orders = [];
    rows.forEach(function (row) {
      var text = row.innerText || '';
      var orderId = (text.match(/\b\d{3}-\d{7}-\d{7}\b/) || [])[0];        // Amazon注文ID形式
      var skuEl = row.querySelector('[data-test-id="sku"], .sku');
      var sku = skuEl ? skuEl.innerText.trim() : (text.match(/SKU[:：]\s*(\S+)/) || [])[1];
      var qty = Number((text.match(/数量[:：]?\s*(\d+)/) || [])[1] || 1);
      if (orderId && sku) orders.push({ amazonOrderId: orderId, sku: sku, qty: qty });
    });
    return orders;
  }

  function reportOrders() {
    var orders = scrapeOrders();
    if (orders.length) chrome.runtime.sendMessage({ type: 'AMAZON_ORDERS', orders: orders });
  }

  // 注文ページなら読み取り（初回＋DOM変化を監視）
  if (/orders|注文/.test(href) || document.querySelector('[data-test-id="order-card"], .order-card, tr.order-row')) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', reportOrders);
    else reportOrders();
    var mo = new MutationObserver(function () { reportOrders(); });
    if (document.body) mo.observe(document.body, { childList: true, subtree: true });
  }

  // ---- 2) 在庫変更の受信 ----
  function setStockForSku(sku, quantity) {
    // TODO: 在庫管理ページで SKU 行を特定し、数量入力に quantity を書き込んで保存する。
    var rows = document.querySelectorAll('[data-test-id="inventory-row"], tr');
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if ((row.innerText || '').indexOf(sku) < 0) continue;
      var input = row.querySelector('input[name*="quantity"], input[type="number"]');
      if (input) {
        input.value = String(quantity);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        var saveBtn = row.querySelector('button[type="submit"], .save-button');
        if (saveBtn) saveBtn.click();
        return true;
      }
    }
    return false;
  }

  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type !== 'SET_STOCK') return;
    if (msg.dryRun) {
      console.log('[RSAS][DRY_RUN] would set stock', msg.sku, '→', msg.quantity);
      sendResponse({ ok: true, dryRun: true });
      return;
    }
    var ok = setStockForSku(msg.sku, msg.quantity);
    if (!ok) {
      chrome.runtime.sendMessage({
        type: 'AMAZON_ORDERS', orders: [] // no-op；在庫行が見つからない場合は手動対応を促す通知に委ねる
      });
    }
    sendResponse({ ok: ok });
  });
})();
