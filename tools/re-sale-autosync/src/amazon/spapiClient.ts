import axios, { AxiosInstance, AxiosError } from 'axios';
import { config } from '../config.js';
import { logger } from '../logger.js';

/**
 * SP-API 認証（LWA）とベース HTTP クライアント。
 *
 * 重要な前提:
 *  - 2023 以降、SP-API は AWS SigV4 署名・IAM ロール不要になった。
 *    LWA の access_token を x-amz-access-token ヘッダに載せるだけで呼べる。
 *  - access_token は約 1 時間で失効するため、内部でキャッシュ＋自動更新する。
 */
class SpApiClient {
  private accessToken: string | null = null;
  private tokenExpiresAt = 0; // epoch ms
  private http: AxiosInstance;

  constructor() {
    this.http = axios.create({
      baseURL: config.SPAPI_ENDPOINT,
      timeout: 30_000,
    });
  }

  /** LWA refresh_token → access_token（60 秒のマージンを持ってキャッシュ再利用）。 */
  private async getAccessToken(): Promise<string> {
    const now = Date.now();
    if (this.accessToken && now < this.tokenExpiresAt - 60_000) {
      return this.accessToken;
    }

    const res = await axios.post(
      config.SPAPI_LWA_ENDPOINT,
      new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: config.SPAPI_LWA_REFRESH_TOKEN,
        client_id: config.SPAPI_LWA_CLIENT_ID,
        client_secret: config.SPAPI_LWA_CLIENT_SECRET,
      }),
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
    );

    this.accessToken = res.data.access_token as string;
    this.tokenExpiresAt = now + (res.data.expires_in as number) * 1000;
    logger.debug('LWA access token refreshed');
    return this.accessToken;
  }

  /**
   * 認証ヘッダ付きの汎用リクエスト。
   * 429（レート制限）は指数バックオフ + Retry-After 尊重で最大 3 回リトライ。
   */
  async request<T = unknown>(opts: {
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    path: string;
    params?: Record<string, string | number | undefined>;
    data?: unknown;
    attempt?: number;
  }): Promise<T> {
    const attempt = opts.attempt ?? 0;
    const token = await this.getAccessToken();

    try {
      const res = await this.http.request<T>({
        method: opts.method,
        url: opts.path,
        params: opts.params,
        data: opts.data,
        headers: {
          'x-amz-access-token': token,
          'content-type': 'application/json',
        },
      });
      return res.data;
    } catch (err) {
      const ae = err as AxiosError;
      const status = ae.response?.status;

      // レート制限 or 一時的サーバエラーはバックオフ再試行
      if ((status === 429 || (status && status >= 500)) && attempt < 3) {
        const retryAfter = Number(ae.response?.headers?.['retry-after']);
        const backoff = Number.isFinite(retryAfter)
          ? retryAfter * 1000
          : 2 ** attempt * 1000;
        logger.warn(
          { status, backoff, path: opts.path },
          'SP-API throttled/5xx; backing off',
        );
        await new Promise((r) => setTimeout(r, backoff));
        return this.request<T>({ ...opts, attempt: attempt + 1 });
      }

      logger.error(
        { status, data: ae.response?.data, path: opts.path },
        'SP-API request failed',
      );
      throw err;
    }
  }
}

export const spapi = new SpApiClient();
