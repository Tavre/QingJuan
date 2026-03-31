export type BookKind = '长小说' | '轻小说' | '漫画';
export type Language = '中文' | '英文' | '日文';
export type TranslationProvider = 'openai' | 'newapi' | 'anthropic' | 'grok2api' | 'custom';
export type BookStatus = '待处理' | '解析中' | '已下载' | '已完成';
export type TaskType = 'download' | 'translate';
export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed';
export type TaskLogLevel = 'info' | 'warning' | 'error';
export type BookExportFormat = 'txt' | 'epub';
export type ReaderProgressAnchorType = 'top' | 'paragraph' | 'image';

export interface AddBookPayload {
  sourceUrl: string;
  bookKind: BookKind;
  title?: string;
  language: Language;
  needTranslation: boolean;
}

export interface ChapterPreview {
  title: string;
  url: string;
  pageCount: number;
}

export interface BookRecord {
  id: string;
  title: string;
  sourceUrl: string;
  bookKind: BookKind;
  language: Language;
  status: BookStatus;
  chapterCount: number;
  translated: boolean;
  localPath: string;
  updatedAt: string;
  synopsis: string;
  cover?: string | null;
  lastReadChapterIndex: number;
  lastReadAt?: string | null;
}

export interface ChapterRecord {
  id: string;
  index: number;
  title: string;
  fileName: string;
  wordCount: number;
  downloaded: boolean;
  translated: boolean;
  sourceUrl?: string | null;
  illustration: boolean;
  imageCount: number;
  imageUrls: string[];
  imageFiles: string[];
  translatedImageFiles: string[];
  pageCount: number;
}

export interface ReadingProgressRecord {
  bookId: string;
  lastChapterIndex: number;
  lastScrollRatio: number;
  lastAnchorType: ReaderProgressAnchorType;
  lastAnchorIndex: number;
  lastAnchorOffsetRatio: number;
  lastReadAt?: string | null;
}

export interface ReadingProgressPayload {
  chapterIndex: number;
  scrollRatio?: number;
  anchorType?: ReaderProgressAnchorType;
  anchorIndex?: number;
  anchorOffsetRatio?: number;
}

export interface ChapterActionPayload {
  chapterIndexes: number[];
}

export interface BookExportPayload {
  format: BookExportFormat;
  targetPath?: string;
}

export interface BookExportResponse {
  bookId: string;
  format: BookExportFormat;
  fileName: string;
  filePath: string;
  downloadUrl: string;
  chapterCount: number;
}

export interface TaskRecord {
  id: string;
  bookId: string;
  taskType: TaskType;
  chapterIndexes: number[];
  status: TaskStatus;
  totalCount: number;
  completedCount: number;
  progress: number;
  message: string;
  error?: string | null;
  attempts: number;
  createdAt: string;
  updatedAt: string;
}

export interface TaskLogRecord {
  sequence: number;
  taskId: string;
  level: TaskLogLevel;
  message: string;
  createdAt: string;
}

export interface BookDetailResponse {
  book: BookRecord;
  title: string;
  author?: string | null;
  synopsis: string;
  addedAt: string;
  totalWords: number;
  downloadedChapterCount: number;
  translatedChapterCount: number;
  progress: ReadingProgressRecord;
  chapters: ChapterRecord[];
}

export interface ChapterContentResponse {
  bookId: string;
  chapter: ChapterRecord;
  content: string;
  paragraphs: string[];
  mode: 'original' | 'translated';
  translatedAvailable: boolean;
  imageSources: string[];
  pageTranslations: string[];
}

export interface PreviewResponse {
  title: string;
  author?: string;
  synopsis: string;
  cover?: string;
  chapterCount: number;
  chapters: ChapterPreview[];
  bookKind: BookKind;
}

export interface ProviderConfig {
  enabled: boolean;
  baseUrl: string;
  apiKey: string;
  model: string;
}

export interface ComicSourceConfig {
  email: string;
  password: string;
}

export interface TranslationSettings {
  defaultProvider: TranslationProvider;
  systemPrompt: string;
  autoTranslateNextChapters: number;
  downloadConcurrency: number;
  providers: Record<TranslationProvider, ProviderConfig>;
  bika: ComicSourceConfig;
}

export interface BackendInfo {
  host: string;
  port: number;
  already_running: boolean;
}
