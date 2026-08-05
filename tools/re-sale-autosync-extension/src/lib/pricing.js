/**
 * 価格計算（無在庫/FBM）。サーバー版 pricing.ts と同じ式を素の JS に移植。
 * background(service worker)は importScripts で、content script は manifest の js 配列で読み込む。
 * どちらの実行環境でも self.RSAS に生やして共有する。
 */
(function (root) {
  root.RSAS = root.RSAS || {};

  /**
   * 販売価格 P と「損益分岐となる仕入れ元価格 maxSourcePrice」を算出。
   *   P = (落札 + 仕入送料 + その他) / (1 - referralRate - margin)
   *   maxSourcePrice = P*(1 - referralRate) - 仕入送料 - その他
   */
  root.RSAS.calcSellPrice = function calcSellPrice(input) {
    var referralRate = input.referralRate != null ? input.referralRate : 0.15;
    var otherCost = input.otherCost || 0;
    var roundTo = input.roundTo || 10;
    var cost = Number(input.assumedWinningBid) + Number(input.procurementShipping || 0) + Number(otherCost);

    var denom = 1 - referralRate - Number(input.targetMargin);
    if (denom <= 0) {
      throw new Error('利益率が高すぎます（referralRate + margin >= 1）');
    }

    var sellPrice = Math.ceil(cost / denom / roundTo) * roundTo;
    var referralFee = Math.round(sellPrice * referralRate);
    var estimatedProfit = sellPrice - cost - referralFee;
    var estimatedMargin = estimatedProfit / sellPrice;
    var maxSourcePrice = Math.floor(
      sellPrice * (1 - referralRate) - Number(input.procurementShipping || 0) - Number(otherCost)
    );

    return { sellPrice: sellPrice, cost: cost, referralFee: referralFee,
             estimatedProfit: estimatedProfit, estimatedMargin: estimatedMargin,
             maxSourcePrice: maxSourcePrice };
  };
})(typeof self !== 'undefined' ? self : this);
