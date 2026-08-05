import cron from 'node-cron';
import pLimit from 'p-limit';
import { prisma } from '../db.js';
import { syncOne } from '../services/syncService.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * 定期実行タスク（既定 20 分おき）。
 *  - active な監視対象を全件取得し、同時実行数を絞って（p-limit）順に同期。
 *  - 1 件の失敗が全体を止めないよう allSettled で握る。
 *  - 多重起動防止フラグで、前回ジョブが長引いた場合の重複実行を回避。
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
    logger.info({ count: targets.length }, 'monitor cycle start');

    const results = await Promise.allSettled(
      targets.map((t) => limit(() => syncOne(t.productId))),
    );

    const failed = results.filter((r) => r.status === 'rejected').length;
    logger.info(
      { total: targets.length, failed, ms: Date.now() - startedAt },
      'monitor cycle done',
    );
  } catch (err) {
    logger.error({ err: (err as Error).message }, 'monitor cycle fatal');
  } finally {
    running = false;
  }
}

/** cron スケジューラを起動（worker プロセスとして常駐）。 */
export function startScheduler(): void {
  logger.info({ cron: config.MONITOR_CRON, dryRun: config.DRY_RUN }, 'scheduler starting');
  cron.schedule(config.MONITOR_CRON, () => {
    void runMonitorCycle();
  });
}

// このファイルを直接実行したときはスケジューラ常駐 + 起動時に 1 回実行
const isMain = process.argv[1]?.endsWith('monitorJob.ts') || process.argv[1]?.endsWith('monitorJob.js');
if (isMain) {
  startScheduler();
  void runMonitorCycle();
}
