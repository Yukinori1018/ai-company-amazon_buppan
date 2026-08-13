/**
 * セラーセントラルの content script。
 *  1) 注文管理ページを開いていると、新規注文の SKU/注文ID/数量を拾って background へ送る
 *     → background が該当 SKU の購入タスクを作成（半自動購入のトリガ）。
 *  2) 在庫管理ページで background からの SET_STOCK 指示を受け、該当 SKU の在庫数を変更（best-effort）。
 *
 * ※ C1: DOM セレクタは options（設定）で外部化。実画面に合わせた調整をコード改修なしで行える。
 *   settings.selectors が無ければ下記 FALLBACK を使う。Amazon は UI 自動化を非推奨のため、
 *   確実性重視なら将来 SP-API 併用が望ましい。
 */
(function () {
  var href = location.href;

  // settings.selectors が読めるまでのフォールバック（store.js の DEFAULT_SELECTORS と一致させる）
  var FALLBACK = {
    amazonOrderRow: '[data-test-id="order-card"], .order-card, tr.order-row',
    amazonSku: '[data-test-id="sku"], .sku',
    amazonInventoryRow: '[data-test-id="inventory-row"], tr',
    amazonQtyInput: 'input[name*="quantity"], input[type="number"]',
    amazonSaveBtn: 'button[type="submit"], .save-button'
  };
  var SEL = Object.assign({}, FALLBACK);

  function loadSelectors(cb) {
    chrome.storage.local.get('settings', function (r) {
      var s = (r && r.settings && r.settings.selectors) || {};
      Object.keys(FALLBACK).forEach(function (k) { if (s[k]) SEL[k] = s[k]; });
      cb();
    });
  }

  // ---- 1) 注文の読み取り ----
  function scrapeOrders() {
    var rows = document.querySelectorAll(SEL.amazonOrderRow);
    var orders = [];
    rows.forEach(function (row) {
      var text = row.innerText || '';
      var orderId = (text.match(/\b\d{3}-\d{7}-\d{7}\b/) || [])[0];        // Amazon注文ID形式
      var skuEl = row.querySelector(SEL.amazonSku);
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

  // C2: DOM変化のたびに連打しないようデバウンス
  var _debTimer = null;
  function reportOrdersDebounced() {
    if (_debTimer) clearTimeout(_debTimer);
    _debTimer = setTimeout(reportOrders, 700);
  }

  // ---- 2) 在庫変更 ----
  function setStockForSku(sku, quantity) {
    var rows = document.querySelectorAll(SEL.amazonInventoryRow);
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if ((row.innerText || '').indexOf(sku) < 0) continue;
      var input = row.querySelector(SEL.amazonQtyInput);
      if (input) {
        input.value = String(quantity);
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        var saveBtn = row.querySelector(SEL.amazonSaveBtn);
        if (saveBtn) saveBtn.click();
        return true;
      }
    }
    return false;
  }

  // SET_STOCK は同期応答が要るので、リスナは即時登録（SEL はロード後に更新される）
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type !== 'SET_STOCK') return;
    if (msg.dryRun) {
      console.log('[RSAS][DRY_RUN] would set stock', msg.sku, '→', msg.quantity);
      sendResponse({ ok: true, dryRun: true });
      return;
    }
    var ok = setStockForSku(msg.sku, msg.quantity);
    if (!ok) {
      // C3: 在庫行が見つからない場合は手動対応を促す（background側の通知に委ね、ここでは結果のみ返す）
      console.warn('[RSAS] 在庫行が見つからず在庫変更できません sku=', msg.sku, '→ 手動で在庫を', msg.quantity, 'にしてください');
    }
    sendResponse({ ok: ok });
  });

  // セレクタをロードしてから注文監視を開始
  loadSelectors(function () {
    if (/orders|注文/.test(href) || document.querySelector(SEL.amazonOrderRow)) {
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', reportOrders);
      else reportOrders();
      var mo = new MutationObserver(reportOrdersDebounced);
      if (document.body) mo.observe(document.body, { childList: true, subtree: true });
    }
  });
})();
