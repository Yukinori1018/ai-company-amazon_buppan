import cron from 'node-cron';
import pLimit from 'p-limit';
import { prisma } from '../db.js';
import { syncOne } from '../services/syncService.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * 定期実行ワーカー（既定 20 分おき）— 無在庫(FBM)の仕入れ可能性の監視。
 *
 *   active な Auction を巡回し、仕入れ元の状態/価格に応じて Amazon 在庫を 0/1 に同期。
 *   目的は「Amazonで売れたのに仕入れられない」注文を出さないこと（アカウント健全性の保護）。
 *   - p-limit で同時実行数を絞る（ヤフオク/Amazon 双方の負荷・レート制御）
 *   - Promise.allSettled で 1 件の失敗が全体を止めないようにする
 *   - running フラグで多重起動を防止
 *
 * 監視間隔を詰めるほど「売れたのに買えない」窓は小さくなる（MONITOR_CRON で調整）。
 */

const limit = pLimit(config.MONITOR_CONCURRENCY);
let running = false;

export async function runMonitorCycle(): Promise<void> {
  if (running) {
    logger.warn('前回サイクル実行中のためスキップ');
    return;
  }
  running = true;
  const startedAt = Date.now();
  try {
    const targets = await prisma.auction.findMany({
      where: { active: true },
      select: { productId: true },
    });
    logger.info({ count: targets.length }, 'FBM monitor cycle start');

    const results = await Promise.allSettled(targets.map((t) => limit(() => syncOne(t.productId))));
    const failed = results.filter((r) => r.status === 'rejected').length;
    logger.info(
      { total: targets.length, failed, ms: Date.now() - startedAt },
      'FBM monitor cycle done',
    );
  } catch (err) {
    logger.error({ err: (err as Error).message }, 'monitor cycle fatal');
  } finally {
    running = false;
  }
}

export function startScheduler(): void {
  logger.info({ cron: config.MONITOR_CRON, dryRun: config.DRY_RUN }, 'scheduler starting');
  cron.schedule(config.MONITOR_CRON, () => {
    void runMonitorCycle();
  });
}

const isMain =
  process.argv[1]?.endsWith('monitorJob.ts') || process.argv[1]?.endsWith('monitorJob.js');
if (isMain) {
  startScheduler();
  void runMonitorCycle();
}
