/**
 * 販売価格の自動計算。
 *
 * 目標利益率 margin を満たすように Amazon 販売価格 P を逆算する。
 * 想定コスト構成:
 *   仕入原価 cost = 想定落札価格 + 仕入送料
 *   Amazon 販売手数料 = P * referralRate（カテゴリ既定 15%）
 *   出荷コスト（顧客への配送）= shipToCustomer
 *   利益 = P - cost - P*referralRate - shipToCustomer >= P * margin
 *
 * これを P について解くと:
 *   P * (1 - referralRate - margin) = cost + shipToCustomer
 *   P = (cost + shipToCustomer) / (1 - referralRate - margin)
 */
export interface PriceInput {
  assumedWinningBid: number; // 想定落札価格（円）
  procurementShipping: number; // 仕入れ送料（円）
  shipToCustomer?: number; // 顧客への配送コスト（円、FBM 自社負担分）
  targetMargin: number; // 目標利益率（0.20 = 20%）
  referralRate?: number; // Amazon 販売手数料率（既定 0.15）
  roundTo?: number; // 端数丸め単位（既定 10 円）
}

export interface PriceResult {
  sellPrice: number;
  cost: number;
  referralFee: number;
  estimatedProfit: number;
  estimatedMargin: number;
}

export function calcSellPrice(input: PriceInput): PriceResult {
  const referralRate = input.referralRate ?? 0.15;
  const shipToCustomer = input.shipToCustomer ?? 0;
  const roundTo = input.roundTo ?? 10;
  const cost = input.assumedWinningBid + input.procurementShipping;

  const denom = 1 - referralRate - input.targetMargin;
  if (denom <= 0) {
    throw new Error(
      `利益率が高すぎて価格計算が発散します（referralRate + margin >= 1）。margin=${input.targetMargin}`,
    );
  }

  const raw = (cost + shipToCustomer) / denom;
  const sellPrice = Math.ceil(raw / roundTo) * roundTo;

  const referralFee = Math.round(sellPrice * referralRate);
  const estimatedProfit = sellPrice - cost - referralFee - shipToCustomer;
  const estimatedMargin = estimatedProfit / sellPrice;

  return { sellPrice, cost, referralFee, estimatedProfit, estimatedMargin };
}
