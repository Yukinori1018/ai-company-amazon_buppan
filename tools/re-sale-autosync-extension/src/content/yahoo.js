/**
 * ヤフオク!/フリマ 商品ページの content script。
 *  - この商品に対する「購入タスク(PENDING)」があれば、画面右下にオーバーレイを出す。
 *  - 半自動: 社長が「1クリックで購入確定」。上限価格(maxSourcePrice)を超えていたら購入させない。
 *  - DRY_RUN 中は実クリックせず「購入した体」で結果だけ返す（本番前検証用）。
 *
 * ※ ヤフオク側の購入ボタンの正確なセレクタはページ実物に合わせて調整が必要（TODO 参照）。
 *   自動購入は Yahoo の規約・アクセス負荷に配慮し、必ず人の確認(1クリック)を挟む設計。
 */
(function () {
  // URL から出品/商品IDを推定
  function currentItemId() {
    var m = location.href.match(/auction\/([a-zA-Z0-9]+)/) || location.href.match(/item\/([a-zA-Z0-9]+)/);
    return m ? m[1] : null;
  }

  // ページ DOM から現在価格を読む（監視の正規表現より正確）
  function readCurrentPrice() {
    var text = document.body ? document.body.innerText : '';
    var m = text.match(/(?:現在|即決|販売|落札)価格[^0-9]*([0-9,]+)\s*円/);
    return m ? Number(m[1].replace(/[^0-9]/g, '')) : null;
  }

  // Yahoo の購入導線をクリック（best-effort）。成功/失敗を boolean で返す。
  function clickBuy() {
    // TODO: 実ページに合わせて調整。「今すぐ落札」「購入手続きへ」「カートに入れる」等を探す。
    var labels = ['購入手続きへ', '今すぐ落札', '即決で落札', '購入する', 'カートに入れる'];
    var buttons = Array.prototype.slice.call(document.querySelectorAll('a,button,input[type=submit]'));
    for (var i = 0; i < buttons.length; i++) {
      var t = (buttons[i].innerText || buttons[i].value || '').trim();
      for (var j = 0; j < labels.length; j++) {
        if (t.indexOf(labels[j]) >= 0) { buttons[i].click(); return true; }
      }
    }
    return false;
  }

  function overlay(task) {
    if (document.getElementById('rsas-overlay')) return;
    var price = readCurrentPrice();
    var over = price != null && price > task.maxSourcePrice;

    var box = document.createElement('div');
    box.id = 'rsas-overlay';
    box.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:999999;background:#fff;border:2px solid #137333;border-radius:10px;padding:14px;width:300px;box-shadow:0 6px 24px rgba(0,0,0,.25);font-family:system-ui,sans-serif;font-size:13px;color:#222';
    box.innerHTML =
      '<div style="font-weight:bold;margin-bottom:6px;">Re-Sale AutoSync</div>' +
      '<div>Amazon注文に対応する仕入れです。</div>' +
      '<div style="margin:6px 0;">SKU: <b>' + task.sku + '</b></div>' +
      '<div>現在価格: <b style="color:' + (over ? '#c5221f' : '#137333') + '">' + (price != null ? '¥' + price.toLocaleString() : '不明') + '</b>' +
      ' / 上限: ¥' + task.maxSourcePrice.toLocaleString() + '</div>' +
      (over ? '<div style="color:#c5221f;margin-top:6px;">上限超過のため購入不可（赤字）。手動判断してください。</div>' : '') +
      '<div style="margin-top:10px;display:flex;gap:8px;">' +
        '<button id="rsas-buy" ' + (over ? 'disabled' : '') + ' style="flex:1;padding:8px;background:' + (over ? '#ccc' : '#137333') + ';color:#fff;border:0;border-radius:6px;cursor:pointer;">1クリックで購入確定</button>' +
        '<button id="rsas-skip" style="padding:8px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer;">後で</button>' +
      '</div>' +
      '<div id="rsas-msg" style="margin-top:8px;color:#666;"></div>';
    document.body.appendChild(box);

    document.getElementById('rsas-skip').onclick = function () { box.remove(); };
    var buyBtn = document.getElementById('rsas-buy');
    if (buyBtn) buyBtn.onclick = function () {
      var msg = document.getElementById('rsas-msg');
      var nowPrice = readCurrentPrice();
      if (nowPrice != null && nowPrice > task.maxSourcePrice) {
        msg.textContent = '価格が上限を超えました。中止します。';
        report(task.id, false, nowPrice, 'PRICE_OVER_MAX');
        return;
      }
      chrome.storage.local.get('settings', function (r) {
        var dryRun = !r.settings || r.settings.dryRun !== false;
        if (dryRun) {
          msg.textContent = '[DRY_RUN] 実購入せず成功として記録します。';
          report(task.id, true, nowPrice, null);
          setTimeout(function () { box.remove(); }, 1200);
          return;
        }
        // A1: 実購入は必ず background の事前承認を通す（日次上限・上限価格・タスク状態を検査）
        buyBtn.disabled = true;
        chrome.runtime.sendMessage({ type: 'CAN_PURCHASE', taskId: task.id, price: nowPrice }, function (auth) {
          if (!auth || !auth.allowed) {
            buyBtn.disabled = false;
            msg.textContent = '購入不可: ' + ((auth && auth.reason) || 'NOT_AUTHORIZED') + '（中止しました）';
            report(task.id, false, nowPrice, (auth && auth.reason) || 'NOT_AUTHORIZED');
            return;
          }
          var ok = clickBuy();
          if (ok) {
            msg.textContent = '購入導線をクリックしました。決済完了を確認してください。（残枠¥' + (auth.remaining || 0).toLocaleString() + '）';
            report(task.id, true, nowPrice, null);
          } else {
            buyBtn.disabled = false;
            msg.textContent = '購入ボタンが見つかりませんでした（手動購入してください）。';
            report(task.id, false, nowPrice, 'BUY_BUTTON_NOT_FOUND');
          }
        });
      });
    };
  }

  function report(taskId, success, price, error) {
    chrome.runtime.sendMessage({ type: 'PURCHASE_RESULT', taskId: taskId, success: success, price: price, error: error });
  }

  // このページに対応する PENDING タスクがあればオーバーレイ表示
  function init() {
    var itemId = currentItemId();
    if (!itemId) return;
    chrome.runtime.sendMessage({ type: 'GET_STATE' }, function (state) {
      if (!state || !state.tasks) return;
      var task = state.tasks.find(function (t) {
        return t.state === 'PENDING' && t.sourceUrl && t.sourceUrl.indexOf(itemId) >= 0;
      });
      if (task) overlay(task);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
