/**
 * SP-API 認証スモークテスト（単独実行）。
 *
 * 目的: 全体を動かす前に「LWA トークン取得 → SP-API 疎通」だけを最小構成で検証する。
 * 実行:  npm run auth:test
 *
 * 確認する 2 段階:
 *   1) LWA: refresh_token → access_token の取得に成功するか
 *   2) SP-API: /sellers/v1/marketplaceParticipations が 200 を返すか（認証＋権限の実証）
 *
 * ※ 補足: 現行 SP-API は 2023 以降 AWS SigV4 署名・STS/IAM ロールが不要になっており、
 *   認証は LWA アクセストークンのみ（x-amz-access-token ヘッダ）。旧来の STS トークン取得は不要です。
 */
import axios from 'axios';
import { config } from '../config.js';

async function main(): Promise<void> {
  console.log('▶ Step 1: LWA アクセストークンを取得中...');
  let accessToken: string;
  try {
    const res = await axios.post(
      config.SPAPI_LWA_ENDPOINT,
      new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: config.SPAPI_LWA_REFRESH_TOKEN,
        client_id: config.SPAPI_LWA_CLIENT_ID,
        client_secret: config.SPAPI_LWA_CLIENT_SECRET,
      }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, timeout: 20_000 },
    );
    accessToken = res.data.access_token;
    console.log(`  ✅ access_token 取得成功（expires_in=${res.data.expires_in}s）`);
    console.log(`     token 先頭: ${String(accessToken).slice(0, 12)}...`);
  } catch (err: any) {
    console.error('  ❌ LWA トークン取得に失敗:', err.response?.data ?? err.message);
    console.error('     → client_id / client_secret / refresh_token を .env で再確認してください。');
    process.exit(1);
  }

  console.log('\n▶ Step 2: SP-API 疎通確認（marketplaceParticipations）...');
  try {
    const res = await axios.get(
      `${config.SPAPI_ENDPOINT}/sellers/v1/marketplaceParticipations`,
      { headers: { 'x-amz-access-token': accessToken }, timeout: 20_000 },
    );
    const marketplaces = (res.data?.payload ?? [])
      .map((p: any) => p.marketplace?.id)
      .filter(Boolean);
    console.log('  ✅ SP-API 疎通成功。参加マーケットプレイス:', marketplaces.join(', ') || '(なし)');
    const jpOk = marketplaces.includes(config.SPAPI_MARKETPLACE_ID);
    console.log(
      jpOk
        ? `  ✅ 設定中の SPAPI_MARKETPLACE_ID(${config.SPAPI_MARKETPLACE_ID}) に出品権限あり。`
        : `  ⚠️ 設定中の SPAPI_MARKETPLACE_ID(${config.SPAPI_MARKETPLACE_ID}) が参加一覧に見当たりません。要確認。`,
    );
  } catch (err: any) {
    console.error('  ❌ SP-API 疎通に失敗:', err.response?.status, err.response?.data ?? err.message);
    console.error('     → アプリのロール（出品/在庫の権限）、endpoint リージョン、seller_id を確認してください。');
    process.exit(1);
  }

  console.log('\n🎉 認証・疎通ともに OK。全体の起動（npm run dev / worker）に進めます。');
}

main();
