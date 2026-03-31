import { invoke } from '@tauri-apps/api/core';
import { openUrl } from '@tauri-apps/plugin-opener';
import type { BackendInfo, BookExportFormat } from '../types';

const BACKEND_READY_TIMEOUT_MS = 45000;
const BACKEND_READY_RETRY_MS = 500;

function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

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
    throw new Error(`桌面后端启动超时（等待 ${Math.round(BACKEND_READY_TIMEOUT_MS / 1000)} 秒）：${lastError.message}`);
  }
  throw new Error(`桌面后端启动超时（等待 ${Math.round(BACKEND_READY_TIMEOUT_MS / 1000)} 秒）`);
}

export async function startDesktopBackend(): Promise<BackendInfo | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  const backend = await invoke<BackendInfo>('start_python_backend');
  const baseUrl = `http://${backend.host}:${backend.port}`;
  (window as Window & { __QINGJUAN_BACKEND__?: string }).__QINGJUAN_BACKEND__ = baseUrl;
  await waitForBackendHealth(baseUrl);
  return backend;
}

export async function chooseExportPath(defaultFileName: string, format: BookExportFormat): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }

  return await invoke<string | null>('choose_export_path', {
    suggestedName: defaultFileName,
    format,
  });
}

export async function openExternalLink(url: string): Promise<void> {
  const target = url.trim();
  if (!target) {
    return;
  }

  if (isTauriRuntime()) {
    await openUrl(target);
    return;
  }

  window.open(target, '_blank', 'noopener,noreferrer');
}
