import cron from 'node-cron';
import { prisma } from '../db.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * 定期実行ワーカー（FBA 有在庫モデル・任意 / Phase 2）。
 *
 * FBA では在庫は Amazon 倉庫の実数で管理されるため、無在庫時代の
 * 「ヤフオク在庫→Amazon在庫0/1 リアルタイム同期」は不要（廃止済み）。
 *
 * 代わりにこのワーカーが担う想定の Phase 2 タスク（未実装のプレースホルダ）:
 *   - LISTED 商品の FBA 在庫残数チェック（FBA Inventory API）→ 在庫僅少で再仕入れアラート
 *   - Amazon 価格追随（Product Pricing API）→ 想定利益を割る価格になったら通知
 *
 * 現状は LISTED 商品を集計してログするだけの安全なスタブ。
 */
export async function runMonitorCycle(): Promise<void> {
  const listed = await prisma.product.count({ where: { pipelineStage: 'LISTED' } });
  const inbound = await prisma.product.count({ where: { pipelineStage: 'INBOUND' } });
  logger.info(
    { listed, inbound },
    'monitor cycle (Phase2 stub): FBA在庫/価格監視は未実装。LISTED/INBOUND件数のみ集計。',
  );
  // TODO(Phase2): FBA Inventory API で在庫残数を取得し、閾値割れをアラート。
  // TODO(Phase2): Product Pricing API で現在価格を取得し、利益割れをアラート。
}

export function startScheduler(): void {
  logger.info({ cron: config.MONITOR_CRON }, 'scheduler starting (FBA phase2 stub)');
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
