import { PrismaClient } from '@prisma/client';

/**
 * Prisma クライアントのシングルトン。
 * dev の HMR で複数インスタンスが生成されるのを防ぐ。
 */
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: ['warn', 'error'],
  });

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = prisma;
