import { prisma } from '../db.js';
import { getAuctionSnapshot, AuctionStatus } from '../yahoo/auctionMonitor.js';
import { setInStock, setOutOfStock } from '../amazon/listings.js';
import { logger } from '../logger.js';

/**
 * FBM（無在庫）専用：ヤフオク状態 → Amazon 在庫の同期。
 *   ACTIVE                         → 在庫 1（出品中）
 *   ENDED / CANCELLED / NOT_FOUND  → 在庫 0（停止）
 *   UNKNOWN                        → 変更しない（誤停止防止。連続失敗が閾値超で人手確認）
 *
 * FBA 商品は Auction を持たないため、この同期の対象にならない。
 */
const UNKNOWN_FAIL_THRESHOLD = 3;

function desiredQuantity(status: AuctionStatus): number | null {
  switch (status) {
    case 'ACTIVE':
      return 1;
    case 'ENDED':
    case 'CANCELLED':
    case 'NOT_FOUND':
      return 0;
    default:
      return null; // UNKNOWN = 触らない
  }
}

/** 1 件の FBM Product＋Auction を同期する。 */
export async function syncOne(productId: string): Promise<void> {
  const product = await prisma.product.findUnique({
    where: { id: productId },
    include: { auction: true },
  });
  if (!product || !product.auction) return;
  if (product.fulfillmentType !== 'FBM') return; // FBA は同期対象外
  if (!product.auction.active) return;

  const snap = await getAuctionSnapshot(product.auction.yahooAuctionId);
  const desired = desiredQuantity(snap.status);

  await prisma.auction.update({
    where: { id: product.auction.id },
    data: {
      status: snap.status,
      currentPrice: snap.currentPrice ?? undefined,
      endTime: snap.endTime ?? undefined,
      lastCheckedAt: new Date(),
      checkFailCount: snap.status === 'UNKNOWN' ? product.auction.checkFailCount + 1 : 0,
    },
  });

  if (desired === null) {
    if (product.auction.checkFailCount + 1 >= UNKNOWN_FAIL_THRESHOLD) {
      logger.error(
        { productId, auctionId: product.auction.yahooAuctionId },
        'UNKNOWN が連続。手動確認が必要',
      );
    }
    await log(productId, snap.status, 'NO_CHANGE', product.quantity, product.quantity, 'UNKNOWN: skip');
    return;
  }

  if (desired === product.quantity) {
    await log(productId, snap.status, 'NO_CHANGE', product.quantity, desired);
    return;
  }

  try {
    const res = desired === 0 ? await setOutOfStock(product.sku) : await setInStock(product.sku);
    await prisma.product.update({
      where: { id: productId },
      data: { quantity: desired, listingState: desired === 0 ? 'INACTIVE' : 'ACTIVE' },
    });
    if (snap.status === 'ENDED' || snap.status === 'CANCELLED') {
      await prisma.auction.update({ where: { id: product.auction.id }, data: { active: false } });
    }
    await log(
      productId,
      snap.status,
      desired === 0 ? 'SET_OUT_OF_STOCK' : 'SET_IN_STOCK',
      product.quantity,
      desired,
      res.status,
    );
    logger.info(
      { sku: product.sku, from: product.quantity, to: desired, status: snap.status },
      'FBM synced',
    );
  } catch (err) {
    await prisma.product.update({ where: { id: productId }, data: { listingState: 'ERROR' } });
    await log(productId, snap.status, 'ERROR', product.quantity, desired, undefined, (err as Error).message);
    throw err;
  }
}

async function log(
  productId: string,
  auctionStatus: string,
  action: string,
  fromQuantity?: number,
  toQuantity?: number,
  spapiStatus?: string,
  message?: string,
): Promise<void> {
  await prisma.syncLog.create({
    data: { productId, auctionStatus, action, fromQuantity, toQuantity, spapiStatus, message },
  });
}
