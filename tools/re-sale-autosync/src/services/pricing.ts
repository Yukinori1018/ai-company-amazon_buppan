/**
 * 販売価格と「仕入れ可能性ガード（損益分岐となる仕入れ元価格）」の計算（無在庫/FBM）。
 *
 * 想定コスト構成:
 *   仕入原価 cost = 落札価格 + 仕入送料 + 自社発送費等(other)
 *   Amazon 販売手数料 = P * referralRate（カテゴリ既定 15%）
 *   利益 = P - cost - P*referralRate >= P * margin
 *
 * 販売価格 P（目標利益率 margin を満たす）:
 *   P = (assumedBid + shipping + other) / (1 - referralRate - margin)
 *
 * 損益分岐となる仕入れ元価格 maxSourcePrice（この販売価格 P で、落札額がここを超えると赤字）:
 *   0 = P - (source + shipping + other) - P*referralRate
 *   maxSourcePrice = P*(1 - referralRate) - shipping - other
 *
 * 監視側は「現在の落札価格 > maxSourcePrice」を検知したら在庫0にする（利益で仕入れ不能）。
 */
export interface PriceInput {
  assumedWinningBid: number; // 想定落札価格（円）
  procurementShipping: number; // 仕入れ送料（円）
  otherCost?: number; // 自社発送費・梱包等（円）
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
  maxSourcePrice: number; // 損益分岐となる仕入れ元価格（監視ガードに使用）
}

export function calcSellPrice(input: PriceInput): PriceResult {
  const referralRate = input.referralRate ?? 0.15;
  const otherCost = input.otherCost ?? 0;
  const roundTo = input.roundTo ?? 10;
  const cost = input.assumedWinningBid + input.procurementShipping + otherCost;

  const denom = 1 - referralRate - input.targetMargin;
  if (denom <= 0) {
    throw new Error(
      `利益率が高すぎて価格計算が発散します（referralRate + margin >= 1）。margin=${input.targetMargin}`,
    );
  }

  const sellPrice = Math.ceil(cost / denom / roundTo) * roundTo;
  const referralFee = Math.round(sellPrice * referralRate);
  const estimatedProfit = sellPrice - cost - referralFee;
  const estimatedMargin = estimatedProfit / sellPrice;

  // 損益分岐となる仕入れ元価格（落札額がこれを超えたら赤字＝在庫0にすべき）
  const maxSourcePrice = Math.floor(
    sellPrice * (1 - referralRate) - input.procurementShipping - otherCost,
  );

  return { sellPrice, cost, referralFee, estimatedProfit, estimatedMargin, maxSourcePrice };
}
