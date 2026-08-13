import 'dotenv/config';
import { z } from 'zod';

/**
 * 環境変数を Zod で検証して型安全に露出する。
 * 起動時に不正値があれば即座に落とす（本番投入時の設定ミスを早期検知）。
 */
const envSchema = z.object({
  PORT: z.coerce.number().default(3000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  LOG_LEVEL: z.string().default('info'),

  DATABASE_URL: z.string(),

  // Amazon SP-API / LWA
  SPAPI_LWA_CLIENT_ID: z.string(),
  SPAPI_LWA_CLIENT_SECRET: z.string(),
  SPAPI_LWA_REFRESH_TOKEN: z.string(),
  SPAPI_MARKETPLACE_ID: z.string().default('A1VC38T7YXB528'), // 日本
  SPAPI_SELLER_ID: z.string(),
  SPAPI_ENDPOINT: z.string().default('https://sellingpartnerapi-fe.amazon.com'),
  SPAPI_LWA_ENDPOINT: z.string().default('https://api.amazon.com/auth/o2/token'),

  // ヤフオク!
  YAHOO_BASE_URL: z.string().default('https://page.auctions.yahoo.co.jp/jp/auction/'),
  YAHOO_REQUEST_INTERVAL_MS: z.coerce.number().default(3000),
  YAHOO_USER_AGENT: z.string().default('ResaleAutoSyncBot/0.1'),
  YAHOO_FETCH_MODE: z.enum(['cheerio', 'puppeteer']).default('cheerio'),

  // Cron
  MONITOR_CRON: z.string().default('*/20 * * * *'),
  MONITOR_CONCURRENCY: z.coerce.number().default(3),

  // 安全弁
  DRY_RUN: z
    .string()
    .default('true')
    .transform((v) => v.toLowerCase() === 'true'),
});

export const config = envSchema.parse(process.env);
export type Config = typeof config;
