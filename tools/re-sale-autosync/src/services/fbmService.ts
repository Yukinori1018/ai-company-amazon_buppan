import { prisma } from '../db.js';
import { calcSellPrice } from './pricing.js';
import { putListing } from '../amazon/listings.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * FBM（無在庫）出品：ヤフオク落札前に Amazon へ出品し、監視対象オークションを紐付ける。
 * 以後 monitorJob が Auction を巡回し、終了/取消で在庫0、再出品で在庫1へ同期する。
 */
export interface CreateFbmInput {
  asin: string;
  sku: string;
  title?: string;
  productType: string;
  purchasePrice: number; // 想定落札価格
  procurementShipping?: number;
  prepCost?: number; // 自社発送費など
  targetMargin?: number;
  referralRate?: number;
  yahooAuctionId: string; // 監視対象
  condition?: string;
}

export async function createFbmListing(input: CreateFbmInput) {
  const price = calcSellPrice({
    assumedWinningBid: input.purchasePrice,
    procurementShipping: input.procurementShipping ?? 0,
    prepCost: input.prepCost ?? 0,
    fbaFee: 0,
    targetMargin: input.targetMargin ?? 0.2,
    referralRate: input.referralRate,
  });

  const listing = await putListing({
    sku: input.sku,
    productType: input.productType,
    condition: input.condition ?? 'used_good',
    price: price.sellPrice,
    fulfillmentType: 'FBM',
    quantity: 1,
  });

  const product = await prisma.product.create({
    data: {
      asin: input.asin,
      sku: input.sku,
      title: input.title,
      productType: input.productType,
      fulfillmentType: 'FBM',
      purchasePrice: input.purchasePrice,
      procurementShipping: input.procurementShipping ?? 0,
      prepCost: input.prepCost ?? 0,
      fbaFee: 0,
      targetMargin: input.targetMargin ?? 0.2,
      sellPrice: price.sellPrice,
      sourceUrl: `${config.YAHOO_BASE_URL}${input.yahooAuctionId}`,
      sourceRef: input.yahooAuctionId,
      quantity: 1,
      listingState: listing.status === 'DRY_RUN' ? 'DRAFT' : 'ACTIVE',
      auction: {
        create: {
          yahooAuctionId: input.yahooAuctionId,
          url: `${config.YAHOO_BASE_URL}${input.yahooAuctionId}`,
          status: 'ACTIVE',
          active: true,
        },
      },
    },
    include: { auction: true },
  });

  logger.info({ sku: product.sku, auctionId: input.yahooAuctionId }, 'FBM listed & monitoring');
  return { product, listing, price };
}
