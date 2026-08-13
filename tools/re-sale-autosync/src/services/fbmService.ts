import { prisma } from '../db.js';
import { calcSellPrice } from './pricing.js';
import { putListing } from '../amazon/listings.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * 無在庫(FBM)出品：ヤフオク落札前に Amazon へ出品し、監視対象オークションを紐付ける。
 * 以後 monitorJob が Auction を巡回し、仕入れ不能（終了/取消/価格超過）で在庫0、
 * 再度仕入れ可能になれば在庫1へ同期する。
 */
export interface CreateFbmInput {
  asin: string;
  sku: string;
  title?: string;
  productType: string;
  purchasePrice: number; // 想定落札価格
  procurementShipping?: number;
  otherCost?: number; // 自社発送費・梱包等
  targetMargin?: number;
  referralRate?: number;
  yahooAuctionId: string; // 監視対象
  condition?: string;
}

export async function createFbmListing(input: CreateFbmInput) {
  const price = calcSellPrice({
    assumedWinningBid: input.purchasePrice,
    procurementShipping: input.procurementShipping ?? 0,
    otherCost: input.otherCost ?? 0,
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
      purchasePrice: input.purchasePrice,
      procurementShipping: input.procurementShipping ?? 0,
      otherCost: input.otherCost ?? 0,
      targetMargin: input.targetMargin ?? 0.2,
      sellPrice: price.sellPrice,
      maxSourcePrice: price.maxSourcePrice,
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

  logger.info(
    { sku: product.sku, auctionId: input.yahooAuctionId, maxSourcePrice: price.maxSourcePrice },
    'FBM listed & monitoring',
  );
  return { product, listing, price };
}
