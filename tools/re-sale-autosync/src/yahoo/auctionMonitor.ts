import axios from 'axios';
import * as cheerio from 'cheerio';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * ヤフオク! オークションの生存確認。
 *
 * 【方針】
 *  - Yahoo! オークション公式 API は現在提供終了のため、商品ページの取得で状態判定する。
 *  - スクレイピングは規約・robots・負荷に配慮する:
 *      * User-Agent と連絡先を明示
 *      * リクエスト間隔（YAHOO_REQUEST_INTERVAL_MS）を空ける
 *      * 監視は「自分が出品連携した ID のみ」に限定（全件クロールしない）
 *  - HTML 構造は変わりやすいので、判定は「複数シグナルの多数決」で頑健にする。
 *  - JS レンダリング必須ページ向けに Puppeteer モードも用意（YAHOO_FETCH_MODE=puppeteer）。
 *
 * 返す status:
 *   ACTIVE     : 開催中（入札受付中）
 *   ENDED      : 終了（落札 or 期間満了）
 *   CANCELLED  : 取り消し
 *   NOT_FOUND  : ページが存在しない（削除等）
 *   UNKNOWN    : 判定不能（取得失敗・構造変化）— 誤って Amazon を止めないための保険
 */

export type AuctionStatus = 'ACTIVE' | 'ENDED' | 'CANCELLED' | 'NOT_FOUND' | 'UNKNOWN';

export interface AuctionSnapshot {
  yahooAuctionId: string;
  status: AuctionStatus;
  currentPrice: number | null;
  endTime: Date | null;
  raw?: string; // デバッグ用スニペット
}

let lastRequestAt = 0;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/**
 * ポライトネス: 前回リクエストから最低 interval を空ける。
 * さらに ±40% のランダムジッタを乗せ、一定間隔の機械的アクセスパターンを崩して
 * IP ブロックを受けにくくする。
 */
async function throttle(): Promise<void> {
  const base = config.YAHOO_REQUEST_INTERVAL_MS;
  const jitter = Math.floor((Math.random() - 0.5) * base * 0.8); // ±40%
  const target = Math.max(0, base + jitter);
  const wait = target - (Date.now() - lastRequestAt);
  if (wait > 0) await sleep(wait);
  lastRequestAt = Date.now();
}

function buildUrl(auctionId: string): string {
  return `${config.YAHOO_BASE_URL}${encodeURIComponent(auctionId)}`;
}

/** HTML 文字列から状態を判定する純粋関数（テストしやすいよう分離）。 */
export function parseAuctionHtml(auctionId: string, html: string): AuctionSnapshot {
  const $ = cheerio.load(html);
  const text = $('body').text();

  // --- 終了/取消の判定（複数シグナル） ---
  const endedSignals = [
    /このオークションは終了しています/,
    /終了日時/,
    /落札されました/,
    /オークションは終了しました/,
  ];
  const cancelledSignals = [/このオークションは削除されました/, /出品が取り消され/];
  const notFoundSignals = [/ページが見つかりません/, /指定されたURLは存在しません/];

  const isCancelled = cancelledSignals.some((re) => re.test(text));
  const isNotFound = notFoundSignals.some((re) => re.test(text));
  const endedHits = endedSignals.filter((re) => re.test(text)).length;

  // --- 価格の抽出（JSON-LD / meta / DOM の順にフォールバック） ---
  let currentPrice: number | null = null;
  $('script[type="application/ld+json"]').each((_, el) => {
    if (currentPrice != null) return;
    try {
      const data = JSON.parse($(el).contents().text());
      const offers = data?.offers ?? data?.['@graph']?.find((g: any) => g.offers)?.offers;
      const price = offers?.price ?? offers?.[0]?.price;
      if (price != null) currentPrice = Number(String(price).replace(/[^\d]/g, ''));
    } catch {
      /* JSON-LD が壊れていても他手段へ */
    }
  });

  // --- 終了時刻の抽出 ---
  let endTime: Date | null = null;
  const endMeta = $('meta[property="og:auction:end_time"]').attr('content');
  if (endMeta) {
    const d = new Date(endMeta);
    if (!Number.isNaN(d.getTime())) endTime = d;
  }

  let status: AuctionStatus;
  if (isNotFound) status = 'NOT_FOUND';
  else if (isCancelled) status = 'CANCELLED';
  else if (endedHits >= 1 && !/入札する|即決価格で落札|残り時間/.test(text)) status = 'ENDED';
  else if (/残り時間|入札する|即決/.test(text)) status = 'ACTIVE';
  else status = 'UNKNOWN';

  return { yahooAuctionId: auctionId, status, currentPrice, endTime };
}

/**
 * Cheerio（軽量 HTTP 取得）でのスナップショット取得。
 * 429（レート制限）/503（一時的拒否）は指数バックオフ + Retry-After 尊重で最大 2 回再試行。
 * それでもダメなら UNKNOWN を返し、Amazon 在庫は触らない（誤停止防止）。
 */
async function fetchWithCheerio(auctionId: string, attempt = 0): Promise<AuctionSnapshot> {
  await throttle();
  const url = buildUrl(auctionId);
  try {
    const res = await axios.get<string>(url, {
      headers: {
        'User-Agent': config.YAHOO_USER_AGENT,
        'Accept-Language': 'ja,en;q=0.8',
      },
      timeout: 20_000,
      // 404/429/503 も例外にせず自前で判定・制御する
      validateStatus: () => true,
    });

    if (res.status === 404) {
      return { yahooAuctionId: auctionId, status: 'NOT_FOUND', currentPrice: null, endTime: null };
    }

    // レート制限・一時的拒否はバックオフ再試行
    if ((res.status === 429 || res.status === 503) && attempt < 2) {
      const retryAfter = Number(res.headers?.['retry-after']);
      const backoff = Number.isFinite(retryAfter)
        ? retryAfter * 1000
        : (2 ** attempt) * config.YAHOO_REQUEST_INTERVAL_MS;
      logger.warn({ auctionId, status: res.status, backoff }, 'yahoo throttled; backing off');
      await sleep(backoff);
      return fetchWithCheerio(auctionId, attempt + 1);
    }

    if (res.status >= 400) {
      logger.warn({ auctionId, status: res.status }, 'yahoo fetch non-OK; UNKNOWN');
      return { yahooAuctionId: auctionId, status: 'UNKNOWN', currentPrice: null, endTime: null };
    }

    return parseAuctionHtml(auctionId, res.data);
  } catch (err) {
    logger.warn({ auctionId, err: (err as Error).message }, 'yahoo fetch(cheerio) failed');
    return { yahooAuctionId: auctionId, status: 'UNKNOWN', currentPrice: null, endTime: null };
  }
}

/**
 * Puppeteer（JS レンダリング）でのスナップショット取得。
 * puppeteer は optionalDependency。未インストール時は cheerio にフォールバック。
 */
async function fetchWithPuppeteer(auctionId: string): Promise<AuctionSnapshot> {
  await throttle();
  const url = buildUrl(auctionId);
  let browser: any;
  try {
    const puppeteer = (await import('puppeteer')).default;
    browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
    const page = await browser.newPage();
    await page.setUserAgent(config.YAHOO_USER_AGENT);
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    if (resp && resp.status() === 404) {
      return { yahooAuctionId: auctionId, status: 'NOT_FOUND', currentPrice: null, endTime: null };
    }
    const html = await page.content();
    return parseAuctionHtml(auctionId, html);
  } catch (err) {
    logger.warn(
      { auctionId, err: (err as Error).message },
      'yahoo fetch(puppeteer) failed; falling back to cheerio',
    );
    return fetchWithCheerio(auctionId);
  } finally {
    if (browser) await browser.close();
  }
}

/** 公開 API: 1 オークションの現在状態を取得。 */
export async function getAuctionSnapshot(auctionId: string): Promise<AuctionSnapshot> {
  return config.YAHOO_FETCH_MODE === 'puppeteer'
    ? fetchWithPuppeteer(auctionId)
    : fetchWithCheerio(auctionId);
}
