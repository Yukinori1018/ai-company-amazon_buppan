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

export interface PutListingInput {
  sku: string;
  productType: string; // 例: PET_SUPPLIES。getDefinitionsProductType で ASIN から取得推奨。
  condition: string; // new_new / used_like_new / used_very_good / used_good / used_acceptable
  price: number; // 円
  quantity: number; // 初期在庫（無在庫なので通常 1）
  fulfillmentLatencyDays?: number; // ハンドリングタイム（無在庫は長めに設定して仕入れ猶予を確保）
  merchantShippingGroup?: string;
}

/**
 * 新規出品（FBM）。出品者出荷なので fulfillment_availability に自社在庫を記述。
 * ※ attributes のキーはマーケットプレイス×productType で異なるため、実運用では
 *   getDefinitionsProductType のスキーマに合わせて動的に組み立てること。
 */
export async function putListing(input: PutListingInput): Promise<{ status: string; submissionId?: string }> {
  const body = {
    productType: input.productType,
    requirements: 'LISTING',
    attributes: {
      condition_type: [{ value: input.condition }],
      merchant_suggested_asin: undefined, // ASIN 相乗り時は existing offer に紐づくので通常不要
      purchasable_offer: [
        {
          currency: 'JPY',
          our_price: [{ schedule: [{ value_with_tax: input.price }] }],
          marketplace_id: config.SPAPI_MARKETPLACE_ID,
        },
      ],
      fulfillment_availability: [
        {
          fulfillment_channel_code: 'DEFAULT', // FBM（出品者出荷）
          quantity: input.quantity,
          lead_time_to_ship_max_days: input.fulfillmentLatencyDays ?? 5,
        },
      ],
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
