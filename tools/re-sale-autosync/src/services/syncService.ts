import { prisma } from '../db.js';
import { getAuctionSnapshot, AuctionStatus } from '../yahoo/auctionMonitor.js';
import { setInStock, setOutOfStock } from '../amazon/listings.js';
import { logger } from '../logger.js';

/**
 * 無在庫(FBM)の在庫同期 = 「仕入れ可能性(procurability)」の監視。
 *
 * 本ツールの核心目的:「Amazonで売れたのに仕入れられない」注文を発生させないこと。
 *   → 仕入れ元(オークション)が仕入れ不能になった瞬間に Amazon 在庫を 0 にする。
 *
 * 判定（希望在庫）:
 *   ENDED / CANCELLED / NOT_FOUND        → 0（仕入れ元が消滅。この一点物はもう買えない）
 *   ACTIVE かつ 現在価格 > maxSourcePrice → 0（価格が損益分岐超過＝利益で仕入れ不能）
 *   ACTIVE かつ 価格が範囲内               → 1（仕入れ可能）
 *   UNKNOWN                              → 変更しない（誤停止/誤出品の双方を防ぐ）
 */
const UNKNOWN_FAIL_THRESHOLD = 3;

interface Decision {
  quantity: number | null; // null = 触らない
  reason: string;
}

function decide(
  status: AuctionStatus,
  currentPrice: number | null,
  maxSourcePrice: number,
): Decision {
  switch (status) {
    case 'ENDED':
      return { quantity: 0, reason: 'AUCTION_ENDED' };
    case 'CANCELLED':
      return { quantity: 0, reason: 'AUCTION_CANCELLED' };
    case 'NOT_FOUND':
      return { quantity: 0, reason: 'AUCTION_NOT_FOUND' };
    case 'ACTIVE':
      if (currentPrice != null && currentPrice > maxSourcePrice) {
        return { quantity: 0, reason: `PRICE_OVER_MAX(${currentPrice}>${maxSourcePrice})` };
      }
      return { quantity: 1, reason: 'PROCURABLE' };
    default:
      return { quantity: null, reason: 'UNKNOWN_SKIP' };
  }
}

/** 1 件の FBM Product＋Auction を同期する。 */
export async function syncOne(productId: string): Promise<void> {
  const product = await prisma.product.findUnique({
    where: { id: productId },
    include: { auction: true },
  });
  if (!product || !product.auction || !product.auction.active) return;

  const snap = await getAuctionSnapshot(product.auction.yahooAuctionId);
  const { quantity: desired, reason } = decide(snap.status, snap.currentPrice, product.maxSourcePrice);

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
    await log(productId, snap.status, reason, 'NO_CHANGE', product.quantity, product.quantity);
    return;
  }

  if (desired === product.quantity) {
    await log(productId, snap.status, reason, 'NO_CHANGE', product.quantity, desired);
    return;
  }

  try {
    const res = desired === 0 ? await setOutOfStock(product.sku) : await setInStock(product.sku);
    await prisma.product.update({
      where: { id: productId },
      data: { quantity: desired, listingState: desired === 0 ? 'INACTIVE' : 'ACTIVE' },
    });
    // 終了/取消でその一点物が消えたら監視終了（価格超過は復帰し得るので監視継続）
    if (snap.status === 'ENDED' || snap.status === 'CANCELLED' || snap.status === 'NOT_FOUND') {
      await prisma.auction.update({ where: { id: product.auction.id }, data: { active: false } });
    }
    await log(
      productId,
      snap.status,
      reason,
      desired === 0 ? 'SET_OUT_OF_STOCK' : 'SET_IN_STOCK',
      product.quantity,
      desired,
      res.status,
    );
    logger.info(
      { sku: product.sku, from: product.quantity, to: desired, status: snap.status, reason },
      'FBM synced',
    );
  } catch (err) {
    await prisma.product.update({ where: { id: productId }, data: { listingState: 'ERROR' } });
    await log(productId, snap.status, reason, 'ERROR', product.quantity, desired, undefined, (err as Error).message);
    throw err;
  }
}

async function log(
  productId: string,
  auctionStatus: string,
  reason: string,
  action: string,
  fromQuantity?: number,
  toQuantity?: number,
  spapiStatus?: string,
  message?: string,
): Promise<void> {
  await prisma.syncLog.create({
    data: { productId, auctionStatus, reason, action, fromQuantity, toQuantity, spapiStatus, message },
  });
}
