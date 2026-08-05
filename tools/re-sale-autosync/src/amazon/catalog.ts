import { spapi } from './spapiClient.js';
import { config } from '../config.js';

/**
 * Catalog Items API（2022-04-01）— ASIN/キーワードから商品情報を取得。
 * リサーチ画面での「Amazon 側の商品情報表示」に使う。
 */

export interface CatalogItemSummary {
  asin: string;
  title: string;
  brand?: string;
  imageUrl?: string;
  productType?: string;
}

/** ASIN 単体取得。 */
export async function getCatalogItem(asin: string): Promise<CatalogItemSummary | null> {
  const res = await spapi.request<any>({
    method: 'GET',
    path: `/catalog/2022-04-01/items/${asin}`,
    params: {
      marketplaceIds: config.SPAPI_MARKETPLACE_ID,
      includedData: 'summaries,images,productTypes',
    },
  });
  const s = res?.summaries?.[0];
  if (!s) return null;
  return {
    asin,
    title: s.itemName ?? '',
    brand: s.brand,
    imageUrl: res?.images?.[0]?.images?.[0]?.link,
    productType: res?.productTypes?.[0]?.productType,
  };
}

/** キーワード検索。 */
export async function searchCatalogItems(keywords: string): Promise<CatalogItemSummary[]> {
  const res = await spapi.request<any>({
    method: 'GET',
    path: '/catalog/2022-04-01/items',
    params: {
      marketplaceIds: config.SPAPI_MARKETPLACE_ID,
      keywords,
      includedData: 'summaries,images,productTypes',
      pageSize: 10,
    },
  });
  return (res?.items ?? []).map((it: any) => ({
    asin: it.asin,
    title: it.summaries?.[0]?.itemName ?? '',
    brand: it.summaries?.[0]?.brand,
    imageUrl: it.images?.[0]?.images?.[0]?.link,
    productType: it.productTypes?.[0]?.productType,
  }));
}
