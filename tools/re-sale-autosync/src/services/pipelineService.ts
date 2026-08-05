import { prisma } from '../db.js';
import { calcSellPrice } from './pricing.js';
import { putListing } from '../amazon/listings.js';
import { logger } from '../logger.js';

/**
 * FBA 仕入れパイプライン（有在庫）の状態管理。
 *   SOURCED(仕入済) → INSPECTED(検品済) → RELABELED(ラベル貼替済)
 *     → INBOUND(FBA納品済) → LISTED(出品中) → SOLD_OUT(在庫切れ)
 *
 * ヤフオクのリアルタイム在庫監視は行わない（実物を保有しているため不要）。
 */
export const PIPELINE_STAGES = [
  'SOURCED',
  'INSPECTED',
  'RELABELED',
  'INBOUND',
  'LISTED',
  'SOLD_OUT',
] as const;
export type PipelineStage = (typeof PIPELINE_STAGES)[number];

export interface CreateProductInput {
  asin: string;
  sku: string;
  title?: string;
  productType?: string;
  purchasePrice: number;
  procurementShipping?: number;
  prepCost?: number;
  fbaFee?: number;
  targetMargin?: number;
  referralRate?: number;
  sourceUrl?: string;
  sourceRef?: string;
}

/** リサーチ結果から「仕入済(SOURCED)」商品を登録し、FBA 手数料込みで販売価格を確定する。 */
export async function createSourcedProduct(input: CreateProductInput) {
  const price = calcSellPrice({
    assumedWinningBid: input.purchasePrice,
    procurementShipping: input.procurementShipping ?? 0,
    prepCost: input.prepCost ?? 0,
    fbaFee: input.fbaFee ?? 0,
    targetMargin: input.targetMargin ?? 0.2,
    referralRate: input.referralRate,
  });

  const product = await prisma.product.create({
    data: {
      asin: input.asin,
      sku: input.sku,
      title: input.title,
      productType: input.productType,
      fulfillmentType: 'FBA',
      purchasePrice: input.purchasePrice,
      procurementShipping: input.procurementShipping ?? 0,
      prepCost: input.prepCost ?? 0,
      fbaFee: input.fbaFee ?? 0,
      targetMargin: input.targetMargin ?? 0.2,
      sellPrice: price.sellPrice,
      sourceUrl: input.sourceUrl,
      sourceRef: input.sourceRef,
      purchasedAt: new Date(),
      pipelineStage: 'SOURCED',
      listingState: 'DRAFT',
    },
  });
  await prisma.pipelineLog.create({
    data: { productId: product.id, toStage: 'SOURCED', note: '仕入れ登録' },
  });
  logger.info({ sku: product.sku, sellPrice: price.sellPrice }, 'product sourced');
  return { product, price };
}

/** 次の段階へ進める（順序を強制。飛び越し・逆行はエラー）。 */
export async function advanceStage(productId: string, toStage: PipelineStage, note?: string) {
  const product = await prisma.product.findUnique({ where: { id: productId } });
  if (!product) throw new Error('product not found');

  const fromIdx = PIPELINE_STAGES.indexOf(product.pipelineStage as PipelineStage);
  const toIdx = PIPELINE_STAGES.indexOf(toStage);
  if (toIdx === -1) throw new Error(`unknown stage: ${toStage}`);
  // 1 段階ずつ前進のみ許可（SOLD_OUT への遷移は LISTED からのみ）
  if (toIdx !== fromIdx + 1) {
    throw new Error(
      `不正な遷移: ${product.pipelineStage} → ${toStage}（1 段階ずつ前進のみ許可）`,
    );
  }

  const updated = await prisma.product.update({
    where: { id: productId },
    data: {
      pipelineStage: toStage,
      listingState:
        toStage === 'LISTED' ? 'LISTED' : toStage === 'SOLD_OUT' ? 'INACTIVE' : product.listingState,
    },
  });
  await prisma.pipelineLog.create({
    data: { productId, fromStage: product.pipelineStage, toStage, note },
  });
  logger.info({ sku: product.sku, from: product.pipelineStage, to: toStage }, 'stage advanced');
  return updated;
}

/**
 * FBA として Amazon に出品する（INBOUND 済みの商品を LISTED へ）。
 * FBA なので在庫は倉庫実数管理。putListing は fulfillment_channel_code=AMAZON_JP で登録。
 */
export async function listToFba(productId: string) {
  const product = await prisma.product.findUnique({ where: { id: productId } });
  if (!product) throw new Error('product not found');
  if (!product.productType) throw new Error('productType 未設定のため出品できません');

  const listing = await putListing({
    sku: product.sku,
    productType: product.productType,
    condition: 'used_good',
    price: product.sellPrice,
    fulfillmentType: 'FBA',
  });

  await prisma.product.update({
    where: { id: productId },
    data: {
      pipelineStage: 'LISTED',
      listingState: listing.status === 'DRY_RUN' ? 'DRAFT' : 'LISTED',
    },
  });
  await prisma.pipelineLog.create({
    data: { productId, fromStage: product.pipelineStage, toStage: 'LISTED', note: `FBA出品(${listing.status})` },
  });
  return listing;
}
