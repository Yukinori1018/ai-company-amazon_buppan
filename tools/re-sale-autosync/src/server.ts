import express from 'express';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { logger } from './logger.js';
import { prisma } from './db.js';
import { getCatalogItem, searchCatalogItems } from './amazon/catalog.js';
import { calcSellPrice } from './services/pricing.js';
import { getAuctionSnapshot } from './yahoo/auctionMonitor.js';
import {
  PIPELINE_STAGES,
  PipelineStage,
  createSourcedProduct,
  advanceStage,
  listToFba,
} from './services/pipelineService.js';
import { createFbmListing } from './services/fbmService.js';
import { runMonitorCycle } from './jobs/monitorJob.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// --- 画面: FBM 監視一覧 ＋ FBA パイプラインボード ---
app.get('/', async (_req, res) => {
  const [fbm, fba] = await Promise.all([
    prisma.product.findMany({
      where: { fulfillmentType: 'FBM' },
      include: { auction: true },
      orderBy: { updatedAt: 'desc' },
      take: 200,
    }),
    prisma.product.findMany({
      where: { fulfillmentType: 'FBA' },
      orderBy: { updatedAt: 'desc' },
      take: 300,
    }),
  ]);
  const board: Record<string, typeof fba> = {};
  for (const stage of PIPELINE_STAGES) board[stage] = [];
  for (const p of fba) (board[p.pipelineStage ?? 'SOURCED'] ??= []).push(p);
  res.render('index', { fbm, board, stages: PIPELINE_STAGES });
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
    if (keyword) return res.json({ items: await searchCatalogItems(keyword) });
    return res.status(400).json({ error: 'asin か keyword を指定してください' });
  } catch (err) {
    logger.error({ err: (err as Error).message }, 'amazon search failed');
    res.status(502).json({ error: 'Amazon 検索に失敗しました' });
  }
});

// --- API: ヤフオク! の状態/相場取得（FBM 監視・FBA リサーチ共用） ---
app.get('/api/source/yahoo/:auctionId', async (req, res) => {
  try {
    res.json(await getAuctionSnapshot(req.params.auctionId));
  } catch {
    res.status(502).json({ error: 'ヤフオク取得に失敗しました' });
  }
});

// --- API: 価格プレビュー（FBM/FBA 共通・手数料込み試算） ---
app.post('/api/price/preview', (req, res) => {
  try {
    const { purchasePrice, procurementShipping, prepCost, fbaFee, targetMargin } = req.body;
    res.json(
      calcSellPrice({
        assumedWinningBid: Number(purchasePrice),
        procurementShipping: Number(procurementShipping ?? 0),
        prepCost: Number(prepCost ?? 0),
        fbaFee: Number(fbaFee ?? 0),
        targetMargin: Number(targetMargin ?? 0.2),
      }),
    );
  } catch (err) {
    res.status(400).json({ error: (err as Error).message });
  }
});

// ============================ FBM（無在庫） ============================

// --- API: FBM 出品＋監視紐付け ---
app.post('/api/fbm/list', async (req, res) => {
  try {
    const b = req.body;
    if (!b.asin || !b.sku || !b.productType || !b.yahooAuctionId || b.purchasePrice == null) {
      return res
        .status(400)
        .json({ error: 'asin, sku, productType, yahooAuctionId, purchasePrice は必須です' });
    }
    const result = await createFbmListing({
      asin: b.asin,
      sku: b.sku,
      title: b.title,
      productType: b.productType,
      purchasePrice: Number(b.purchasePrice),
      procurementShipping: Number(b.procurementShipping ?? 0),
      prepCost: Number(b.prepCost ?? 0),
      targetMargin: Number(b.targetMargin ?? 0.2),
      yahooAuctionId: String(b.yahooAuctionId),
    });
    res.json(result);
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

// --- API: FBM 監視を今すぐ 1 サイクル実行 ---
app.post('/api/monitor/run', async (_req, res) => {
  await runMonitorCycle();
  res.json({ ok: true });
});

// ============================ FBA（有在庫） ============================

// --- API: 仕入れ登録（SOURCED として起票） ---
app.post('/api/products', async (req, res) => {
  try {
    const b = req.body;
    if (!b.asin || !b.sku || b.purchasePrice == null) {
      return res.status(400).json({ error: 'asin, sku, purchasePrice は必須です' });
    }
    res.json(
      await createSourcedProduct({
        asin: b.asin,
        sku: b.sku,
        title: b.title,
        productType: b.productType,
        purchasePrice: Number(b.purchasePrice),
        procurementShipping: Number(b.procurementShipping ?? 0),
        prepCost: Number(b.prepCost ?? 0),
        fbaFee: Number(b.fbaFee ?? 0),
        targetMargin: Number(b.targetMargin ?? 0.2),
        sourceUrl: b.sourceUrl,
        sourceRef: b.sourceRef,
      }),
    );
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

// --- API: 段階を1つ進める ---
app.post('/api/products/:id/advance', async (req, res) => {
  try {
    res.json(await advanceStage(req.params.id, String(req.body.toStage) as PipelineStage, req.body.note));
  } catch (err) {
    res.status(400).json({ error: (err as Error).message });
  }
});

// --- API: FBA 出品（INBOUND → LISTED） ---
app.post('/api/products/:id/list', async (req, res) => {
  try {
    res.json(await listToFba(req.params.id));
  } catch (err) {
    res.status(500).json({ error: (err as Error).message });
  }
});

app.listen(config.PORT, () => {
  logger.info(
    { port: config.PORT, dryRun: config.DRY_RUN },
    `Re-Sale AutoSync (FBM+FBA) on http://localhost:${config.PORT}`,
  );
});
