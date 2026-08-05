import { spapi } from './spapiClient.js';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * Listings Items API（2021-08-01）ラッパー。
 *  - putListing:    新規出品（FBM）を登録（フル PUT）
 *  - patchQuantity: 在庫数のみ部分更新（PATCH）— 停止=0 / 再開=1
 *
 * ドキュメント: Listings Items API v2021-08-01
 *   PUT   /listings/2021-08-01/items/{sellerId}/{sku}
 *   PATCH /listings/2021-08-01/items/{sellerId}/{sku}
 */

const API_BASE = '/listings/2021-08-01/items';
const commonParams = {
  marketplaceIds: config.SPAPI_MARKETPLACE_ID,
};

export type FulfillmentType = 'FBA' | 'FBM';

export interface PutListingInput {
  sku: string;
  productType: string; // 例: PET_SUPPLIES。getDefinitionsProductType で ASIN から取得推奨。
  condition: string; // new_new / used_like_new / used_very_good / used_good / used_acceptable
  price: number; // 円
  fulfillmentType?: FulfillmentType; // 既定 FBA（即時仕入れ→検品→ラベル→FBA 納品モデル）
  quantity?: number; // FBM 時の初期在庫。FBA は倉庫実数管理のため無視。
  fulfillmentLatencyDays?: number; // FBM のハンドリングタイム
}

/**
 * 新規出品。
 *  - FBA（既定）: fulfillment_channel_code = AMAZON_JP。在庫は Amazon 倉庫の実数で管理されるため
 *    quantity は指定しない（納品＝Inbound Shipment で反映される）。
 *  - FBM: fulfillment_channel_code = DEFAULT。自社在庫 quantity とハンドリングタイムを記述。
 * ※ attributes のキーはマーケットプレイス×productType で異なるため、実運用では
 *   getDefinitionsProductType のスキーマに合わせて動的に組み立てること。
 * ※ FBA 用マーケットプレイス別チャネルコード（日本=AMAZON_JP）は要確認。
 */
export async function putListing(input: PutListingInput): Promise<{ status: string; submissionId?: string }> {
  const fulfillmentType = input.fulfillmentType ?? 'FBA';
  const fulfillmentAvailability =
    fulfillmentType === 'FBA'
      ? [{ fulfillment_channel_code: 'AMAZON_JP' }] // FBA: 在庫は倉庫実数管理
      : [
          {
            fulfillment_channel_code: 'DEFAULT', // FBM（出品者出荷）
            quantity: input.quantity ?? 1,
            lead_time_to_ship_max_days: input.fulfillmentLatencyDays ?? 5,
          },
        ];

  const body = {
    productType: input.productType,
    requirements: 'LISTING',
    attributes: {
      condition_type: [{ value: input.condition }],
      purchasable_offer: [
        {
          currency: 'JPY',
          our_price: [{ schedule: [{ value_with_tax: input.price }] }],
          marketplace_id: config.SPAPI_MARKETPLACE_ID,
        },
      ],
      fulfillment_availability: fulfillmentAvailability,
    },
  };

  if (config.DRY_RUN) {
    logger.info({ sku: input.sku, body }, '[DRY_RUN] putListing skipped');
    return { status: 'DRY_RUN' };
  }

  const res = await spapi.request<{ submissionId: string; status: string }>({
    method: 'PUT',
    path: `${API_BASE}/${config.SPAPI_SELLER_ID}/${encodeURIComponent(input.sku)}`,
    params: commonParams,
    data: body,
  });
  logger.info({ sku: input.sku, status: res.status }, 'putListing submitted');
  return res;
}

/**
 * 在庫数のみを部分更新（PATCH）。
 * 停止 = 0、再開 = 1。fulfillment_availability の quantity を replace する。
 */
export async function patchQuantity(
  sku: string,
  quantity: number,
): Promise<{ status: string }> {
  const body = {
    productType: 'PRODUCT', // PATCH では汎用 PRODUCT で可（属性パスで対象を特定）
    patches: [
      {
        op: 'replace',
        path: '/attributes/fulfillment_availability',
        value: [
          {
            fulfillment_channel_code: 'DEFAULT',
            quantity,
          },
        ],
      },
    ],
  };

  if (config.DRY_RUN) {
    logger.info({ sku, quantity }, '[DRY_RUN] patchQuantity skipped');
    return { status: 'DRY_RUN' };
  }

  const res = await spapi.request<{ status: string }>({
    method: 'PATCH',
    path: `${API_BASE}/${config.SPAPI_SELLER_ID}/${encodeURIComponent(sku)}`,
    params: commonParams,
    data: body,
  });
  logger.info({ sku, quantity, status: res.status }, 'patchQuantity submitted');
  return res;
}

/** 停止（在庫 0）ショートカット。 */
export const setOutOfStock = (sku: string) => patchQuantity(sku, 0);
/** 再開（在庫 1）ショートカット。 */
export const setInStock = (sku: string) => patchQuantity(sku, 1);
