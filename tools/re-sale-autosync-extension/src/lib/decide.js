/**
 * 仕入れ可能性(procurability)の判定と、ヤフオク商品ページHTMLのパース（正規表現ベース）。
 * background(service worker)には DOMParser が無いため、監視取得は fetch → 正規表現で状態/価格を判定する。
 * （実購入時は content script 側で DOM を使う）
 */
(function (root) {
  root.RSAS = root.RSAS || {};

  /**
   * ヤフオク/フリマの HTML から状態と価格を推定。
   * 構造変化に強くするため複数シグナルの多数決＋UNKNOWNフォールバック。
   * returns { status, currentPrice }
   *   status: ACTIVE | ENDED | CANCELLED | NOT_FOUND | UNKNOWN
   */
  root.RSAS.parseYahooHtml = function parseYahooHtml(html) {
    if (!html) return { status: 'UNKNOWN', currentPrice: null };
    var text = html.replace(/<[^>]+>/g, ' '); // タグ除去してテキスト判定

    var notFound = /ページが見つかりません|指定されたURL|お探しのページ/.test(text);
    var cancelled = /削除されました|出品(が)?取り消/.test(text);
    var ended = /(このオークションは)?終了(しています|しました)|落札されました|入札は締め切/.test(text);
    var active = /残り時間|入札する|即決|今すぐ落札|購入手続きへ|カートに入れる/.test(text);

    // 価格抽出: JSON-LD の "price" → "現在価格/即決/販売価格 ¥1,234" の順
    var price = null;
    var ld = html.match(/"price"\s*:\s*"?([0-9,]+)"?/);
    if (ld) price = Number(ld[1].replace(/[^0-9]/g, ''));
    if (price == null) {
      var m = text.match(/(?:現在|即決|販売|落札)価格[^0-9]*([0-9,]+)\s*円/);
      if (m) price = Number(m[1].replace(/[^0-9]/g, ''));
    }

    var status;
    if (notFound) status = 'NOT_FOUND';
    else if (cancelled) status = 'CANCELLED';
    else if (ended && !active) status = 'ENDED';
    else if (active) status = 'ACTIVE';
    else status = 'UNKNOWN';

    return { status: status, currentPrice: price };
  };

  /**
   * 希望在庫の決定。
   *   ENDED/CANCELLED/NOT_FOUND → 0（消滅＝もう買えない）
   *   ACTIVE かつ 現在価格 > maxSourcePrice → 0（利益で買えない）
   *   ACTIVE かつ 価格範囲内 → 1
   *   UNKNOWN → null（触らない）
   * returns { quantity, reason }
   */
  root.RSAS.decide = function decide(status, currentPrice, maxSourcePrice) {
    switch (status) {
      case 'ENDED': return { quantity: 0, reason: 'AUCTION_ENDED' };
      case 'CANCELLED': return { quantity: 0, reason: 'AUCTION_CANCELLED' };
      case 'NOT_FOUND': return { quantity: 0, reason: 'AUCTION_NOT_FOUND' };
      case 'ACTIVE':
        if (currentPrice != null && maxSourcePrice != null && currentPrice > maxSourcePrice) {
          return { quantity: 0, reason: 'PRICE_OVER_MAX(' + currentPrice + '>' + maxSourcePrice + ')' };
        }
        return { quantity: 1, reason: 'PROCURABLE' };
      default: return { quantity: null, reason: 'UNKNOWN_SKIP' };
    }
  };
})(typeof self !== 'undefined' ? self : this);
