/**
 * 販売価格の自動計算（即時仕入れ→検品→ラベル貼替→FBA モデル対応）。
 *
 * 目標利益率 margin を満たすように Amazon 販売価格 P を逆算する。
 * 想定コスト構成（FBA）:
 *   仕入原価         cost   = 想定落札価格 + 仕入送料
 *   外注プレップ費   prep   = 検品・ラベル貼替（外注先）+ FBA 入庫までの送料
 *   Amazon 販売手数料        = P * referralRate（カテゴリ既定 15%）
 *   FBA 配送代行手数料 fbaFee = サイズ/重量で決まる固定額（円/個）
 *   利益 = P - cost - prep - P*referralRate - fbaFee >= P * margin
 *
 * これを P について解くと:
 *   P * (1 - referralRate - margin) = cost + prep + fbaFee
 *   P = (cost + prep + fbaFee) / (1 - referralRate - margin)
 *
 * ※ FBM（出品者出荷）で使う場合は fbaFee=0、prep に自社発送コストを入れれば同式で計算可能。
 */
export interface PriceInput {
  assumedWinningBid: number; // 想定落札価格（円）
  procurementShipping: number; // 仕入れ送料（円）
  prepCost?: number; // 検品・ラベル貼替（外注）＋ FBA 入庫送料（円）
  fbaFee?: number; // FBA 配送代行手数料（円/個）。FBM 時は 0。
  targetMargin: number; // 目標利益率（0.20 = 20%）
  referralRate?: number; // Amazon 販売手数料率（既定 0.15）
  roundTo?: number; // 端数丸め単位（既定 10 円）
}

export interface PriceResult {
  sellPrice: number;
  cost: number; // 仕入原価（落札＋仕入送料）
  prepCost: number;
  referralFee: number;
  fbaFee: number;
  estimatedProfit: number;
  estimatedMargin: number;
}

export function calcSellPrice(input: PriceInput): PriceResult {
  const referralRate = input.referralRate ?? 0.15;
  const prepCost = input.prepCost ?? 0;
  const fbaFee = input.fbaFee ?? 0;
  const roundTo = input.roundTo ?? 10;
  const cost = input.assumedWinningBid + input.procurementShipping;

  const denom = 1 - referralRate - input.targetMargin;
  if (denom <= 0) {
    throw new Error(
      `利益率が高すぎて価格計算が発散します（referralRate + margin >= 1）。margin=${input.targetMargin}`,
    );
  }

  const raw = (cost + prepCost + fbaFee) / denom;
  const sellPrice = Math.ceil(raw / roundTo) * roundTo;

  const referralFee = Math.round(sellPrice * referralRate);
  const estimatedProfit = sellPrice - cost - prepCost - referralFee - fbaFee;
  const estimatedMargin = estimatedProfit / sellPrice;

  return { sellPrice, cost, prepCost, referralFee, fbaFee, estimatedProfit, estimatedMargin };
}
