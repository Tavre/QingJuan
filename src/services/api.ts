import type {
  AddBookPayload,
  BookDetailResponse,
  BookRecord,
  ChapterActionPayload,
  ChapterContentResponse,
  PreviewResponse,
  ReadingProgressRecord,
  TaskRecord,
  TranslationSettings,
} from '../types';
import { defaultSettings } from '../lib/mock';

const DEFAULT_BASE_URL = 'http://127.0.0.1:19453';

function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

function getBaseUrl(): string {
  return (window as Window & { __QINGJUAN_BACKEND__?: string }).__QINGJUAN_BACKEND__ ?? DEFAULT_BASE_URL;
}

function toAbsoluteBackendUrl(pathOrUrl: string): string {
  const normalized = pathOrUrl.trim();
  if (!normalized) {
    return normalized;
  }
  if (/^https?:\/\//i.test(normalized)) {
    return normalized;
  }
  return `${getBaseUrl()}${normalized.startsWith('/') ? normalized : `/${normalized}`}`;
}

function normalizeBook<T extends BookRecord>(book: T): T {
  return {
    ...book,
    cover: book.cover ? toAbsoluteBackendUrl(book.cover) : book.cover,
  };
}

function normalizePreview(preview: PreviewResponse): PreviewResponse {
  return {
    ...preview,
    cover: preview.cover ? toAbsoluteBackendUrl(preview.cover) : preview.cover,
  };
}

export function buildBookAssetUrl(bookId: string, assetPath: string): string {
  const normalized = assetPath
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  return `${getBaseUrl()}/books/${bookId}/assets/${normalized}`;
}

async function safeJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}`;

    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === 'string' && payload.detail.trim()) {
        message = payload.detail;
      }
    } catch {
      try {
        const text = await response.text();
        if (text.trim()) {
          message = text.trim();
        }
      } catch {
        // ignore parsing errors for fallback message
      }
    }

    throw new Error(message);
  }

  return (await response.json()) as T;
}

export async function fetchBooks(): Promise<BookRecord[]> {
  const response = await fetch(`${getBaseUrl()}/books`);
  const payload = await safeJson<BookRecord[]>(response);
  return payload.map((book) => normalizeBook(book));
}

export async function fetchBookDetail(bookId: string): Promise<BookDetailResponse> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}`);
  const payload = await safeJson<BookDetailResponse>(response);
  return {
    ...payload,
    book: normalizeBook(payload.book),
  };
}

export async function fetchChapterContent(
  bookId: string,
  chapterIndex: number,
  mode: 'original' | 'translated' = 'translated',
): Promise<ChapterContentResponse> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/chapters/${chapterIndex}?mode=${mode}`);
  const payload = await safeJson<ChapterContentResponse>(response);
  const imageSources = payload.imageSources.length
    ? payload.imageSources
    : payload.chapter.imageFiles.map((assetPath) => buildBookAssetUrl(bookId, assetPath));

  return {
    ...payload,
    imageSources: imageSources.map(toAbsoluteBackendUrl),
  };
}

export async function saveReadingProgress(
  bookId: string,
  chapterIndex: number,
): Promise<ReadingProgressRecord> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/progress`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ chapterIndex }),
  });
  return await safeJson<ReadingProgressRecord>(response);
}

export async function downloadChapters(
  bookId: string,
  payload: ChapterActionPayload,
): Promise<TaskRecord> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/chapters/download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return await safeJson<TaskRecord>(response);
}

export async function translateChapters(
  bookId: string,
  payload: ChapterActionPayload,
): Promise<TaskRecord> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/chapters/translate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return await safeJson<TaskRecord>(response);
}

export async function fetchBookTasks(bookId: string): Promise<TaskRecord[]> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/tasks`);
  return await safeJson<TaskRecord[]>(response);
}

export async function fetchTasks(): Promise<TaskRecord[]> {
  const response = await fetch(`${getBaseUrl()}/tasks`);
  return await safeJson<TaskRecord[]>(response);
}

export async function retryTask(taskId: string): Promise<TaskRecord> {
  const response = await fetch(`${getBaseUrl()}/tasks/${taskId}/retry`, {
    method: 'POST',
  });
  return await safeJson<TaskRecord>(response);
}

export async function previewBook(payload: AddBookPayload): Promise<PreviewResponse> {
  const response = await fetch(`${getBaseUrl()}/books/preview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return normalizePreview(await safeJson<PreviewResponse>(response));
}

export async function importBook(payload: AddBookPayload): Promise<BookRecord> {
  const response = await fetch(`${getBaseUrl()}/books/import`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return normalizeBook(await safeJson<BookRecord>(response));
}

export async function importLocalBook(
  file: File,
  payload: Omit<AddBookPayload, 'sourceUrl'>,
): Promise<BookRecord> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('bookKind', payload.bookKind);
  formData.append('language', payload.language);
  formData.append('needTranslation', String(payload.needTranslation));
  if (payload.title?.trim()) {
    formData.append('title', payload.title.trim());
  }

  const response = await fetch(`${getBaseUrl()}/books/import-local`, {
    method: 'POST',
    body: formData,
  });
  return normalizeBook(await safeJson<BookRecord>(response));
}

export async function uploadBookCover(bookId: string, file: File): Promise<BookRecord> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${getBaseUrl()}/books/${bookId}/cover`, {
    method: 'POST',
    body: formData,
  });
  return normalizeBook(await safeJson<BookRecord>(response));
}

export async function deleteBook(bookId: string): Promise<void> {
  const response = await fetch(`${getBaseUrl()}/books/${bookId}`, {
    method: 'DELETE',
  });
  await safeJson<{ status: string; bookId: string }>(response);
}

export async function fetchSettings(): Promise<TranslationSettings> {
  try {
    const response = await fetch(`${getBaseUrl()}/settings`);
    return await safeJson<TranslationSettings>(response);
  } catch (error) {
    if (isTauriRuntime()) {
      throw error;
    }
    return defaultSettings;
  }
}

export async function saveSettings(payload: TranslationSettings): Promise<TranslationSettings> {
  try {
    const response = await fetch(`${getBaseUrl()}/settings`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    return await safeJson<TranslationSettings>(response);
  } catch (error) {
    if (isTauriRuntime()) {
      throw error;
    }
    return payload;
  }
}
