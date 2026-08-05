import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { logger } from './logger.js';
import { prisma } from './db.js';
import { getCatalogItem, searchCatalogItems } from './amazon/catalog.js';
import { putListing } from './amazon/listings.js';
import { calcSellPrice } from './services/pricing.js';
import { getAuctionSnapshot } from './yahoo/auctionMonitor.js';
import { runMonitorCycle } from './jobs/monitorJob.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// --- 画面: 監視中ダッシュボード ---
app.get('/', async (_req, res) => {
  const products = await prisma.product.findMany({
    include: { auction: true },
    orderBy: { updatedAt: 'desc' },
    take: 100,
  });
  res.render('index', { products });
});

// --- API: Amazon 商品情報の検索（ASIN or キーワード） ---
app.get('/api/amazon/search', async (req, res) => {
  try {
    const asin = String(req.query.asin ?? '').trim();
    const keyword = String(req.query.keyword ?? '').trim();
    if (asin) {
      const item = await getCatalogItem(asin);
      return res.json({ items: item ? [item] : [] });
    }
    if (keyword) {
      return res.json({ items: await searchCatalogItems(keyword) });
    }
    return res.status(400).json({ error: 'asin か keyword を指定してください' });
  } catch (err) {
    logger.error({ err: (err as Error).message }, 'amazon search failed');
    res.status(502).json({ error: 'Amazon 検索に失敗しました' });
  }
});

// --- API: ヤフオク! オークションの現在状態 ---
app.get('/api/yahoo/:auctionId', async (req, res) => {
  try {
    const snap = await getAuctionSnapshot(req.params.auctionId);
    res.json(snap);
  } catch (err) {
    res.status(502).json({ error: 'ヤフオク取得に失敗しました' });
  }
});

// --- API: 価格プレビュー（出品前の試算） ---
app.post('/api/price/preview', (req, res) => {
  try {
    const { assumedWinningBid, procurementShipping, shipToCustomer, targetMargin } = req.body;
    const result = calcSellPrice({
      assumedWinningBid: Number(assumedWinningBid),
      procurementShipping: Number(procurementShipping ?? 0),
      shipToCustomer: Number(shipToCustomer ?? 0),
      targetMargin: Number(targetMargin ?? 0.2),
    });
    res.json(result);
  } catch (err) {
    res.status(400).json({ error: (err as Error).message });
  }
});

// --- API: 出品実行（Amazon 出品 + 監視紐付け保存） ---
app.post('/api/list', async (req, res) => {
  try {
    const {
      asin,
      sku,
      productType,
      condition = 'used_good',
      assumedWinningBid,
      procurementShipping = 0,
      shipToCustomer = 0,
      targetMargin = 0.2,
      yahooAuctionId,
    } = req.body;

    if (!asin || !sku || !yahooAuctionId || !productType) {
      return res.status(400).json({ error: 'asin, sku, productType, yahooAuctionId は必須です' });
    }

    const price = calcSellPrice({
      assumedWinningBid: Number(assumedWinningBid),
      procurementShipping: Number(procurementShipping),
      shipToCustomer: Number(shipToCustomer),
      targetMargin: Number(targetMargin),
    });

    // Amazon へ出品（DRY_RUN 時はスキップされ status=DRY_RUN が返る）
    const listing = await putListing({
      sku,
      productType,
      condition,
      price: price.sellPrice,
      quantity: 1,
    });

    // DB へ紐付け保存（SKU ⇔ yahooAuctionId）
    const product = await prisma.product.create({
      data: {
        asin,
        sku,
        productType,
        costPrice: Number(assumedWinningBid),
        shippingCost: Number(procurementShipping),
        targetMargin: Number(targetMargin),
        sellPrice: price.sellPrice,
        quantity: 1,
        listingState: listing.status === 'DRY_RUN' ? 'PENDING' : 'ACTIVE',
        auction: {
          create: {
            yahooAuctionId: String(yahooAuctionId),
            url: `${config.YAHOO_BASE_URL}${yahooAuctionId}`,
            status: 'ACTIVE',
            active: true,
          },
        },
      },
      include: { auction: true },
    });

    res.json({ product, listing, price });
  } catch (err) {
    logger.error({ err: (err as Error).message }, 'list failed');
    res.status(500).json({ error: (err as Error).message });
  }
});

// --- API: 監視を今すぐ 1 サイクル手動実行（デバッグ/運用用） ---
app.post('/api/monitor/run', async (_req, res) => {
  await runMonitorCycle();
  res.json({ ok: true });
});

app.listen(config.PORT, () => {
  logger.info(
    { port: config.PORT, dryRun: config.DRY_RUN },
    `Re-Sale AutoSync listening on http://localhost:${config.PORT}`,
  );
});
