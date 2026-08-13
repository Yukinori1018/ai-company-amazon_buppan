/**
 * chrome.storage.local の薄いラッパ。監視対象(watches)・購入タスク(tasks)・設定(settings)・ログを管理。
 */
(function (root) {
  root.RSAS = root.RSAS || {};

  // C1: DOMセレクタを設定として外部化。実画面に合わせた調整をコード改修なしで行える。
  //     content script は settings.selectors を読み、未設定はこの既定にフォールバック。
  var DEFAULT_SELECTORS = {
    amazonOrderRow: '[data-test-id="order-card"], .order-card, tr.order-row',
    amazonSku: '[data-test-id="sku"], .sku',
    amazonInventoryRow: '[data-test-id="inventory-row"], tr',
    amazonQtyInput: 'input[name*="quantity"], input[type="number"]',
    amazonSaveBtn: 'button[type="submit"], .save-button',
    yahooBuyLabels: ['購入手続きへ', '今すぐ落札', '即決で落札', '購入する', 'カートに入れる']
  };

  var DEFAULT_SETTINGS = {
    dryRun: true,                 // true の間は実購入・実在庫変更を行わずログのみ
    referralRate: 0.15,
    monitorIntervalMin: 20,       // 監視間隔（分）
    dailySpendCapJPY: 20000,      // 1日の自動購入上限（半自動でも上限で保護）
    spentTodayJPY: 0,
    spentDate: '',                // YYYY-MM-DD
    sellerCentralInventoryUrl: 'https://sellercentral.amazon.co.jp/inventory',
    unknownStreakAlert: 3,        // 取得不能(UNKNOWN)がこの回数連続したら手動確認を促す
    selectors: DEFAULT_SELECTORS
  };

  function get(keys) {
    return new Promise(function (resolve) { chrome.storage.local.get(keys, resolve); });
  }
  function set(obj) {
    return new Promise(function (resolve) { chrome.storage.local.set(obj, resolve); });
  }

  var Store = {
    async getSettings() {
      var r = await get('settings');
      var merged = Object.assign({}, DEFAULT_SETTINGS, r.settings || {});
      merged.selectors = Object.assign({}, DEFAULT_SELECTORS, (r.settings && r.settings.selectors) || {}); // selectorsは深くマージ
      return merged;
    },
    async saveSettings(patch) {
      var s = await Store.getSettings();
      var merged = Object.assign(s, patch);
      await set({ settings: merged });
      return merged;
    },
    async getWatches() { return (await get('watches')).watches || []; },
    async saveWatches(watches) { await set({ watches: watches }); },
    async upsertWatch(watch) {
      var list = await Store.getWatches();
      var i = list.findIndex(function (w) { return w.id === watch.id; });
      if (i >= 0) list[i] = watch; else list.push(watch);
      await Store.saveWatches(list);
      return watch;
    },
    async updateWatch(id, patch) {
      var list = await Store.getWatches();
      var i = list.findIndex(function (w) { return w.id === id; });
      if (i < 0) return null;
      list[i] = Object.assign(list[i], patch);
      await Store.saveWatches(list);
      return list[i];
    },
    async getTasks() { return (await get('tasks')).tasks || []; },
    async saveTasks(tasks) { await set({ tasks: tasks }); },
    async addTask(task) {
      var list = await Store.getTasks();
      // 冪等: 同一 amazonOrderId + sku の PENDING/BOUGHT は重複追加しない（二重購入防止）
      var dup = list.find(function (t) {
        return t.amazonOrderId === task.amazonOrderId && t.sku === task.sku && t.state !== 'CANCELLED' && t.state !== 'FAILED';
      });
      if (dup) return dup;
      list.push(task);
      await Store.saveTasks(list);
      return task;
    },
    async updateTask(id, patch) {
      var list = await Store.getTasks();
      var i = list.findIndex(function (t) { return t.id === id; });
      if (i < 0) return null;
      list[i] = Object.assign(list[i], patch);
      await Store.saveTasks(list);
      return list[i];
    },
    async log(entry) {
      var r = await get('logs');
      var logs = r.logs || [];
      logs.unshift(Object.assign({ at: new Date().toISOString() }, entry));
      if (logs.length > 500) logs = logs.slice(0, 500);
      await set({ logs: logs });
    },
    async getLogs() { return (await get('logs')).logs || []; },
    // 1日の購入上限管理
    async canSpend(amount, todayStr) {
      var s = await Store.getSettings();
      var spent = s.spentDate === todayStr ? s.spentTodayJPY : 0; // 日跨ぎは0にリセット
      return spent + Number(amount || 0) <= s.dailySpendCapJPY;
    },
    async remainingBudget(todayStr) {
      var s = await Store.getSettings();
      var spent = s.spentDate === todayStr ? s.spentTodayJPY : 0;
      return Math.max(0, s.dailySpendCapJPY - spent);
    },
    async addSpend(amount, todayStr) {
      var s = await Store.getSettings();
      var spent = s.spentDate === todayStr ? s.spentTodayJPY : 0;
      await Store.saveSettings({ spentTodayJPY: spent + amount, spentDate: todayStr });
    }
  };

  root.RSAS.Store = Store;
})(typeof self !== 'undefined' ? self : this);
