import type { BackendInfo } from '../types';

const BACKEND_READY_TIMEOUT_MS = 45000;
const BACKEND_READY_RETRY_MS = 500;
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:19453';

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function waitForBackendHealth(baseUrl: string): Promise<void> {
  const startedAt = Date.now();
  let lastError: unknown = null;

  while (Date.now() - startedAt < BACKEND_READY_TIMEOUT_MS) {
    try {
      const response = await fetch(`${baseUrl}/health`, {
        method: 'GET',
        cache: 'no-store',
      });
      if (response.ok) {
        return;
      }
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }

    await sleep(BACKEND_READY_RETRY_MS);
  }

  if (lastError instanceof Error && lastError.message.trim()) {
    throw new Error(`后端服务连接超时（等待 ${Math.round(BACKEND_READY_TIMEOUT_MS / 1000)} 秒）：${lastError.message}`);
  }
  throw new Error(`后端服务连接超时（等待 ${Math.round(BACKEND_READY_TIMEOUT_MS / 1000)} 秒）`);
}

export async function startDesktopBackend(): Promise<BackendInfo | null> {
  const configuredUrl = import.meta.env.VITE_QINGJUAN_BACKEND_URL;
  const baseUrl = (typeof configuredUrl === 'string' && configuredUrl.trim() ? configuredUrl : DEFAULT_BACKEND_URL).replace(/\/+$/, '');
  (window as Window & { __QINGJUAN_BACKEND__?: string }).__QINGJUAN_BACKEND__ = baseUrl;
  await waitForBackendHealth(baseUrl);
  const parsedUrl = new URL(baseUrl);
  return {
    host: parsedUrl.hostname,
    port: Number(parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80)),
    already_running: true,
  };
}

export async function openExternalLink(url: string): Promise<void> {
  const target = url.trim();
  if (!target) {
    return;
  }

  window.open(target, '_blank', 'noopener,noreferrer');
}
