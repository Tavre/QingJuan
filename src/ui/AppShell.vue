<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
// QingJuan
// Author: Tavre
// License: GPL-3.0-only
import { defaultSettings } from '../lib/mock';
import {
  deleteBook,
  downloadChapters,
  exportBook,
  fetchBookDetail,
  fetchBooks,
  fetchTaskLogs,
  fetchBookTasks,
  fetchTasks,
  fetchChapterContent,
  fetchSettings,
  importBook,
  importLocalBook,
  previewBook,
  retryTask,
  saveReadingProgress,
  saveSettings,
  translateChapters,
  uploadBookCover,
} from '../services/api';
import { chooseExportPath, openExternalLink, startDesktopBackend } from '../services/desktop';
import brandIcon from '../../qj_icon2.png';
import type {
  AddBookPayload,
  BookDetailResponse,
  BookExportFormat,
  BookRecord,
  ChapterContentResponse,
  ChapterRecord,
  PreviewResponse,
  ReaderProgressAnchorType,
  ReadingProgressRecord,
  TaskRecord,
  TranslationProvider,
  TranslationSettings,
} from '../types';

type ViewMode = 'library' | 'logs' | 'settings' | 'detail' | 'reader';
type ReaderTheme = 'default' | 'care' | 'night';
type ReaderFontSize = '小' | '中' | '大' | '特大';

interface NavItem {
  key: 'library' | 'logs' | 'settings';
  label: string;
  icon: string;
}

interface ProviderOption {
  key: TranslationProvider;
  label: string;
  description: string;
}

interface BookPresentation {
  author: string;
  coverClass: string;
  accentClass: string;
  progressCurrent: number;
  progressTotal: number;
  addedAt: string;
  words: string;
  serialState: string;
}

interface ReaderThemeOption {
  key: ReaderTheme;
  label: string;
  description: string;
  preview: string;
}

interface ActivityLogEntry {
  id: string;
  category: 'system' | 'action' | 'task' | 'error';
  title: string;
  detail: string;
  at: string;
}

interface TaskLogSyncState {
  sequence: number;
  signature: string;
}

interface ReaderProgressSnapshot {
  chapterIndex: number;
  scrollRatio: number;
  anchorType: ReaderProgressAnchorType;
  anchorIndex: number;
  anchorOffsetRatio: number;
}

interface LoadReaderChapterOptions {
  autoTranslate?: boolean;
  restoreProgress?: ReaderProgressSnapshot | null;
  scrollToTop?: boolean;
  scrollBehavior?: ScrollBehavior;
}

interface OpenReaderOptions extends LoadReaderChapterOptions {
  mode?: 'original' | 'translated';
  restoreSavedProgress?: boolean;
}

const navItems: NavItem[] = [
  { key: 'library', label: '我的书架', icon: '▥' },
  { key: 'logs', label: '运行日志', icon: '◫' },
  { key: 'settings', label: '设置', icon: '⚙' },
];

const providerOptions: ProviderOption[] = [
  { key: 'openai', label: 'OpenAI', description: '支持 GPT 系列与兼容接口' },
  { key: 'anthropic', label: 'Anthropic', description: '适合长文本与自然表达' },
  { key: 'grok2api', label: 'Grok2API', description: '兼容自建 grok2api / Grok OpenAI 接口代理' },
  { key: 'newapi', label: 'New API', description: '兼容聚合网关与中转服务' },
  { key: 'custom', label: '自定义', description: '连接本地或私有翻译端点' },
];

const themeOptions: ReaderThemeOption[] = [
  { key: 'default', label: '默认', description: '整个界面保持清亮留白，适合白天使用。', preview: '亮色书架 · 清爽详情 · 轻量阅读' },
  { key: 'care', label: '护眼', description: '整个界面改为暖色低刺激，适合长时间停留。', preview: '暖色面板 · 柔和背景 · 降低疲劳' },
  { key: 'night', label: '夜间', description: '整个界面切成深色沉浸氛围，适合夜间使用。', preview: '深色导航 · 暗面板 · 更沉浸的阅读场' },
];
const autoTranslateOptions = [
  { value: 0, label: '关闭' },
  { value: 5, label: '后续 5 章' },
  { value: 10, label: '后续 10 章' },
  { value: 20, label: '后续 20 章' },
  { value: -1, label: '全部剩余章节' },
] as const;
const READER_THEME_STORAGE_KEY = 'qingjuan.readerTheme';
const READER_FONT_SIZE_STORAGE_KEY = 'qingjuan.readerFontSize';
const READER_TEXT_COLOR_STORAGE_KEY = 'qingjuan.readerTextColor';
const READER_BACKGROUND_COLOR_STORAGE_KEY = 'qingjuan.readerBackgroundColor';
const LOG_LIMIT = 80;
const BACK_TO_TOP_VISIBLE_SCROLL = 280;

const addBookForm = reactive<AddBookPayload>({
  sourceUrl: '',
  bookKind: '长小说',
  title: '',
  language: '中文',
  needTranslation: false,
});

const books = ref<BookRecord[]>([]);
const preview = ref<PreviewResponse | null>(null);
const settings = ref<TranslationSettings>(defaultSettings);
const activeProvider = ref<TranslationProvider>('openai');
const currentView = ref<ViewMode>('library');
const selectedBookId = ref<string | null>(null);
const searchQuery = ref('');
const showImportPanel = ref(false);
const desktopState = ref('正在准备桌面后端...');
const lastMessage = ref('等待输入小说链接');
const loadingPreview = ref(false);
const importing = ref(false);
const localBookFile = ref<File | null>(null);
const localFilePickerKey = ref(0);
const coverUploadPickerKey = ref(0);
const coverFileInput = ref<HTMLInputElement | null>(null);
const savingSettings = ref(false);
const coverUploading = ref(false);
const deletingBook = ref(false);
const exportMenuOpen = ref(false);
const exportingFormat = ref<BookExportFormat | null>(null);
const detailLoading = ref(false);
const detailError = ref('');
const readerTheme = ref<ReaderTheme>(readStoredReaderTheme());
const readerFontSize = ref<ReaderFontSize>(readStoredReaderFontSize());
const readerTextColor = ref(readStoredReaderColor(READER_TEXT_COLOR_STORAGE_KEY));
const readerBackgroundColor = ref(readStoredReaderColor(READER_BACKGROUND_COLOR_STORAGE_KEY));
const showReaderPanel = ref(true);
const readerChapterPickerOpen = ref(false);
const sidebarCollapsed = ref(false);
const showBackToTopButton = ref(false);
const bookDetail = ref<BookDetailResponse | null>(null);
const selectedChapterIndexes = ref<number[]>([]);
const activeChapterIndex = ref<number | null>(null);
const readerContent = ref<ChapterContentResponse | null>(null);
const readerLoading = ref(false);
const readerError = ref('');
const readerMode = ref<'original' | 'translated'>('translated');
const readerPaperRef = ref<HTMLElement | null>(null);
const chapterActionLoading = ref<'download' | 'translate' | null>(null);
const bookTasks = ref<TaskRecord[]>([]);
const tasksLoading = ref(false);
const taskRetryingId = ref<string | null>(null);
const globalTasks = ref<TaskRecord[]>([]);
const globalTasksLoading = ref(false);
const tasksOverviewOpen = ref(false);
const activityLogs = ref<ActivityLogEntry[]>([]);
let taskPollTimer: number | null = null;
let globalTaskPollTimer: number | null = null;
let readerScrollSaveTimer: number | null = null;
let readerScrollReleaseTimer: number | null = null;
let readerPendingRestoreTimer: number | null = null;
let readerScrollSaveSuspended = false;
let readerPendingRestoreSnapshot: ReaderProgressSnapshot | null = null;
let readerLastSavedProgressKey = '';
const lastCompletedTaskStamp = ref('');
const lastGlobalTaskStamp = ref('');
const taskLogSignatures = new Map<string, string>();
const taskLogSyncState = new Map<string, TaskLogSyncState>();
const taskLogRequests = new Map<string, Promise<void>>();

const stats = computed(() => {
  const translated = books.value.filter((item) => item.translated).length;
  const totalChapters = books.value.reduce((count, item) => count + item.chapterCount, 0);

  return [
    { label: '已收藏', value: `${books.value.length}`, suffix: '本作品' },
    { label: '章节总数', value: `${totalChapters}`, suffix: '章' },
    { label: '已启用翻译', value: `${translated}`, suffix: '本' },
  ];
});

const filteredBooks = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase();
  if (!keyword) {
    return books.value;
  }

  return books.value.filter((book) => {
    const haystack = `${book.title} ${book.synopsis} ${getPresentation(book).author}`.toLowerCase();
    return haystack.includes(keyword);
  });
});

const selectedBook = computed(() => {
  const detailBook = bookDetail.value?.book;
  if (detailBook && detailBook.id === selectedBookId.value) {
    return detailBook;
  }

  const fallback = filteredBooks.value[0] ?? books.value[0] ?? null;
  if (!selectedBookId.value) {
    return fallback;
  }

  return books.value.find((item) => item.id === selectedBookId.value) ?? fallback;
});

const chapters = computed<ChapterRecord[]>(() =>
  bookDetail.value?.book.id === selectedBookId.value ? bookDetail.value.chapters : [],
);

const selectedPresentation = computed(() => {
  const book = selectedBook.value;
  if (!book) {
    return null;
  }

  const base = getPresentation(book);
  const detail = bookDetail.value?.book.id === book.id ? bookDetail.value : null;
  const progressIndex = detail?.progress.lastChapterIndex ?? book.lastReadChapterIndex ?? 0;
  return {
    ...base,
    author: detail?.author?.trim() || '作者暂未识别',
    progressCurrent: progressIndex,
    progressTotal: detail?.chapters.length ?? book.chapterCount,
    addedAt: (detail?.addedAt || book.updatedAt).slice(0, 10),
    words: `${(detail?.totalWords ?? 0).toLocaleString('en-US')}`,
    serialState: book.status === '已完成' ? '已完结' : '连载中',
  };
});

const selectedChapterCount = computed(() => selectedChapterIndexes.value.length);
const allChaptersSelected = computed(
  () => chapters.value.length > 0 && selectedChapterIndexes.value.length === chapters.value.length,
);
const isComicBook = computed(() => selectedBook.value?.bookKind === '漫画');
const persistedReadingProgress = computed(() => {
  const book = selectedBook.value;
  const detail = book && bookDetail.value?.book.id === book.id ? bookDetail.value : null;
  const chapterList = detail?.chapters ?? chapters.value;
  const maxIndex = chapterList.length ? chapterList[chapterList.length - 1].index : book?.chapterCount ?? 0;
  const rawIndex = detail?.progress.lastChapterIndex ?? book?.lastReadChapterIndex ?? 0;
  const currentIndex = maxIndex > 0 ? Math.max(0, Math.min(rawIndex, maxIndex)) : 0;
  const currentChapter = chapterList.find((chapter) => chapter.index === currentIndex) ?? null;
  const continueChapter = currentChapter ?? chapterList[0] ?? null;

  return {
    currentIndex,
    maxIndex,
    hasProgress: currentIndex > 0,
    currentChapter,
    continueChapter,
    continueIndex: continueChapter?.index ?? null,
    lastScrollRatio: clampUnit(detail?.progress.lastScrollRatio ?? 0),
    lastAnchorType: normalizeReaderAnchorType(detail?.progress.lastAnchorType),
    lastAnchorIndex: Math.max(0, detail?.progress.lastAnchorIndex ?? 0),
    lastAnchorOffsetRatio: clampUnit(detail?.progress.lastAnchorOffsetRatio ?? 0),
    lastReadAt: detail?.progress.lastReadAt ?? book?.lastReadAt ?? null,
  };
});
const continueReadingLabel = computed(() => (persistedReadingProgress.value.hasProgress ? '继续阅读' : '开始阅读'));
const continueReadingDescription = computed(() => {
  const progress = persistedReadingProgress.value;
  const chapter = progress.continueChapter;
  if (!chapter) {
    return '当前还没有可阅读的章节。';
  }

  const chapterLabel = chapter.title || formatChapterOrder(chapter.index, selectedBook.value?.bookKind);
  if (!progress.hasProgress) {
    return `尚未开始阅读，将从 ${chapterLabel} 开始。`;
  }

  const timestamp = formatReadingTimestamp(progress.lastReadAt);
  const progressPercent = Math.round(progress.lastScrollRatio * 100);
  const progressSuffix = progressPercent > 0 ? ` · 章内 ${progressPercent}%` : '';
  return timestamp
    ? `上次读到 ${chapterLabel}${progressSuffix} · ${timestamp}`
    : `上次读到 ${chapterLabel}${progressSuffix}`;
});
const readerChapterPickerSummary = computed(() => {
  const progress = persistedReadingProgress.value;
  if (!chapters.value.length) {
    return '当前还没有可切换的章节。';
  }
  if (!progress.hasProgress) {
    return '尚未有历史进度，点击任一章节即可开始阅读。';
  }
  return continueReadingDescription.value;
});

const readerChapter = computed(() =>
  chapters.value.find((item) => item.index === activeChapterIndex.value) ?? chapters.value[0] ?? null,
);

const readerParagraphs = computed(() => readerContent.value?.paragraphs ?? []);
const readerImages = computed(() => readerContent.value?.imageSources ?? []);
const readerPageTranslations = computed(() => readerContent.value?.pageTranslations ?? []);
const readerUsesTranslatedImages = computed(
  () =>
    isComicBook.value &&
    readerMode.value === 'translated' &&
    readerContent.value?.mode === 'translated' &&
    (readerContent.value?.chapter.translatedImageFiles?.length ?? 0) > 0,
);
const visibleReaderParagraphs = computed(() =>
  readerParagraphs.value.filter((paragraph) => {
    const normalized = paragraph.trim();
    if (!normalized) {
      return false;
    }
    if (normalized === '插图链接：') {
      return false;
    }
    return !/^https?:\/\//.test(normalized);
  }),
);
const readerThemeLabel = computed(
  () => themeOptions.find((item) => item.key === readerTheme.value)?.label ?? '默认',
);
const readerCustomStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {};
  if (readerTextColor.value) {
    style['--reader-custom-text'] = readerTextColor.value;
  }
  if (readerBackgroundColor.value) {
    style['--reader-custom-paper-bg'] = readerBackgroundColor.value;
  }
  return style;
});
const readerColorSummary = computed(() => {
  const text = readerTextColor.value || '跟随主题';
  const background = readerBackgroundColor.value || '跟随主题';
  return `字色 ${text} · 背景 ${background}`;
});
const readerProgressTotal = computed(() => chapters.value.length || selectedBook.value?.chapterCount || 0);
const readerProgressIndex = computed(() => readerChapter.value?.index ?? 0);
const readerWordCount = computed(
  () =>
    isComicBook.value
      ? readerContent.value?.chapter.pageCount ?? readerChapter.value?.pageCount ?? 0
      : readerContent.value?.chapter.wordCount ?? readerChapter.value?.wordCount ?? 0,
);
const hasPreviousChapter = computed(() => readerProgressIndex.value > 1);
const hasNextChapter = computed(
  () => readerProgressIndex.value > 0 && readerProgressIndex.value < readerProgressTotal.value,
);
const translatedReadable = computed(
  () => readerContent.value?.translatedAvailable ?? readerChapter.value?.translated ?? false,
);
const readerSourceUrl = computed(() => readerChapter.value?.sourceUrl?.trim() || selectedBook.value?.sourceUrl?.trim() || '');

function clampUnit(value: number | null | undefined): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0;
  }
  return Math.max(0, Math.min(value, 1));
}

function normalizeReaderAnchorType(value: string | null | undefined): ReaderProgressAnchorType {
  return value === 'paragraph' || value === 'image' ? value : 'top';
}

function buildTopProgressSnapshot(chapterIndex: number): ReaderProgressSnapshot {
  return {
    chapterIndex,
    scrollRatio: 0,
    anchorType: 'top',
    anchorIndex: 0,
    anchorOffsetRatio: 0,
  };
}

function buildPersistedProgressSnapshot(chapterIndex?: number | null): ReaderProgressSnapshot | null {
  const progress = persistedReadingProgress.value;
  const targetChapterIndex = chapterIndex ?? progress.currentIndex;
  if (!targetChapterIndex || progress.currentIndex !== targetChapterIndex) {
    return null;
  }
  return {
    chapterIndex: targetChapterIndex,
    scrollRatio: clampUnit(progress.lastScrollRatio),
    anchorType: progress.lastAnchorType,
    anchorIndex: Math.max(0, progress.lastAnchorIndex),
    anchorOffsetRatio: clampUnit(progress.lastAnchorOffsetRatio),
  };
}

function serializeProgressSnapshot(snapshot: ReaderProgressSnapshot): string {
  return [
    snapshot.chapterIndex,
    snapshot.scrollRatio.toFixed(4),
    snapshot.anchorType,
    snapshot.anchorIndex,
    snapshot.anchorOffsetRatio.toFixed(4),
  ].join(':');
}

function getReaderViewportOffset(): number {
  if (typeof window === 'undefined') {
    return 0;
  }
  const topbar = document.querySelector<HTMLElement>('.reader-topbar');
  return (topbar?.offsetHeight ?? 0) + 16;
}

function getDocumentScrollRatio(scrollTop = window.scrollY): number {
  const maxScroll = Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);
  return maxScroll > 0 ? clampUnit(scrollTop / maxScroll) : 0;
}

function captureReaderProgressSnapshot(chapterIndex = readerChapter.value?.index ?? null): ReaderProgressSnapshot | null {
  if (typeof window === 'undefined' || currentView.value !== 'reader' || !readerContent.value || chapterIndex === null) {
    return null;
  }

  const currentScroll = Math.max(window.scrollY || 0, 0);
  if (currentScroll <= 12) {
    return buildTopProgressSnapshot(chapterIndex);
  }

  const paper = readerPaperRef.value;
  const scrollRatio = getDocumentScrollRatio(currentScroll);
  if (!paper) {
    return {
      chapterIndex,
      scrollRatio,
      anchorType: 'top',
      anchorIndex: 0,
      anchorOffsetRatio: 0,
    };
  }

  const viewportTop = getReaderViewportOffset();
  const anchors = Array.from(
    paper.querySelectorAll<HTMLElement>('[data-reader-anchor-type][data-reader-anchor-index]'),
  );
  if (!anchors.length) {
    return {
      chapterIndex,
      scrollRatio,
      anchorType: 'top',
      anchorIndex: 0,
      anchorOffsetRatio: 0,
    };
  }

  let bestAnchor: HTMLElement | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const anchor of anchors) {
    const rect = anchor.getBoundingClientRect();
    const distance = rect.top - viewportTop;
    const score = distance <= 0 ? Math.abs(distance) : distance + 24;
    if (score < bestScore) {
      bestScore = score;
      bestAnchor = anchor;
    }
  }

  if (!bestAnchor) {
    return {
      chapterIndex,
      scrollRatio,
      anchorType: 'top',
      anchorIndex: 0,
      anchorOffsetRatio: 0,
    };
  }

  const anchorRect = bestAnchor.getBoundingClientRect();
  const anchorHeight = Math.max(bestAnchor.offsetHeight, 1);
  const rawAnchorIndex = Number.parseInt(bestAnchor.dataset.readerAnchorIndex ?? '0', 10);

  return {
    chapterIndex,
    scrollRatio,
    anchorType: normalizeReaderAnchorType(bestAnchor.dataset.readerAnchorType),
    anchorIndex: Number.isNaN(rawAnchorIndex) ? 0 : Math.max(0, rawAnchorIndex),
    anchorOffsetRatio: clampUnit((viewportTop - anchorRect.top) / anchorHeight),
  };
}

function resolveReaderAnchorElement(snapshot: ReaderProgressSnapshot): HTMLElement | null {
  if (!readerPaperRef.value || snapshot.anchorType === 'top') {
    return null;
  }
  return readerPaperRef.value.querySelector<HTMLElement>(
    `[data-reader-anchor-type="${snapshot.anchorType}"][data-reader-anchor-index="${snapshot.anchorIndex}"]`,
  );
}

function resolveReaderScrollTop(snapshot: ReaderProgressSnapshot): number {
  if (typeof window === 'undefined') {
    return 0;
  }

  const anchorElement = resolveReaderAnchorElement(snapshot);
  if (anchorElement) {
    const viewportOffset = getReaderViewportOffset();
    const anchorRect = anchorElement.getBoundingClientRect();
    const anchorHeight = Math.max(anchorElement.offsetHeight, 1);
    return Math.max(
      0,
      Math.round(window.scrollY + anchorRect.top - viewportOffset + anchorHeight * clampUnit(snapshot.anchorOffsetRatio)),
    );
  }

  const maxScroll = Math.max(document.documentElement.scrollHeight - window.innerHeight, 0);
  return maxScroll > 0 ? Math.round(maxScroll * clampUnit(snapshot.scrollRatio)) : 0;
}

function clearReaderScrollSaveTimer() {
  if (readerScrollSaveTimer !== null) {
    window.clearTimeout(readerScrollSaveTimer);
    readerScrollSaveTimer = null;
  }
}

function clearReaderScrollReleaseTimer() {
  if (readerScrollReleaseTimer !== null) {
    window.clearTimeout(readerScrollReleaseTimer);
    readerScrollReleaseTimer = null;
  }
}

function clearPendingReaderRestore() {
  if (readerPendingRestoreTimer !== null) {
    window.clearTimeout(readerPendingRestoreTimer);
    readerPendingRestoreTimer = null;
  }
  readerPendingRestoreSnapshot = null;
}

function rememberPendingReaderRestore(snapshot: ReaderProgressSnapshot, durationMs: number) {
  clearPendingReaderRestore();
  if (durationMs <= 0) {
    return;
  }
  readerPendingRestoreSnapshot = snapshot;
  readerPendingRestoreTimer = window.setTimeout(() => {
    clearPendingReaderRestore();
  }, durationMs);
}

function releaseReaderScrollSaveAfter(delayMs: number) {
  clearReaderScrollReleaseTimer();
  readerScrollReleaseTimer = window.setTimeout(() => {
    readerScrollSaveSuspended = false;
    readerScrollReleaseTimer = null;
  }, delayMs);
}

function waitForAnimationFrame(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => resolve());
  });
}

async function waitForAnimationFrames(count = 2): Promise<void> {
  for (let index = 0; index < count; index += 1) {
    await waitForAnimationFrame();
  }
}

async function waitForReaderAssets(timeoutMs = 1200): Promise<void> {
  if (!readerPaperRef.value) {
    return;
  }

  const pendingImages = Array.from(readerPaperRef.value.querySelectorAll<HTMLImageElement>('img')).filter(
    (image) => !image.complete,
  );
  if (!pendingImages.length) {
    return;
  }

  await Promise.race([
    Promise.all(
      pendingImages.map(
        (image) =>
          new Promise<void>((resolve) => {
            const done = () => resolve();
            image.addEventListener('load', done, { once: true });
            image.addEventListener('error', done, { once: true });
          }),
      ),
    ).then(() => undefined),
    new Promise<void>((resolve) => {
      window.setTimeout(resolve, timeoutMs);
    }),
  ]);
}

async function applyReaderViewportProgress(
  snapshot: ReaderProgressSnapshot,
  behavior: ScrollBehavior = 'auto',
): Promise<void> {
  if (typeof window === 'undefined') {
    return;
  }

  readerScrollSaveSuspended = true;
  clearReaderScrollReleaseTimer();
  rememberPendingReaderRestore(snapshot, snapshot.anchorType === 'image' ? 1800 : 0);

  await nextTick();
  if (snapshot.anchorType === 'image' || readerImages.value.length > 0) {
    await waitForReaderAssets(snapshot.anchorType === 'image' ? 1400 : 600);
  }
  await waitForAnimationFrames(2);

  window.scrollTo({
    top: resolveReaderScrollTop(snapshot),
    behavior,
  });

  if (snapshot.anchorType !== 'top' || snapshot.scrollRatio > 0) {
    await waitForAnimationFrames(1);
    const correctedTop = resolveReaderScrollTop(snapshot);
    if (Math.abs(window.scrollY - correctedTop) > 6) {
      window.scrollTo({
        top: correctedTop,
        behavior: 'auto',
      });
    }
  }

  releaseReaderScrollSaveAfter(behavior === 'smooth' ? 420 : 80);
}

async function reapplyPendingReaderRestore() {
  if (!readerPendingRestoreSnapshot || currentView.value !== 'reader') {
    return;
  }
  await waitForAnimationFrames(1);
  window.scrollTo({
    top: resolveReaderScrollTop(readerPendingRestoreSnapshot),
    behavior: 'auto',
  });
}

function applyReadingProgressState(bookId: string, progress: ReadingProgressRecord) {
  if (bookDetail.value?.book.id === bookId) {
    bookDetail.value = {
      ...bookDetail.value,
      progress,
    };
  }
  updateBookProgressCache(bookId, progress);
  readerLastSavedProgressKey = serializeProgressSnapshot({
    chapterIndex: progress.lastChapterIndex,
    scrollRatio: clampUnit(progress.lastScrollRatio),
    anchorType: normalizeReaderAnchorType(progress.lastAnchorType),
    anchorIndex: Math.max(0, progress.lastAnchorIndex),
    anchorOffsetRatio: clampUnit(progress.lastAnchorOffsetRatio),
  });
}

async function persistReaderProgressSnapshot(
  bookId: string | null,
  snapshot: ReaderProgressSnapshot | null,
  options: { force?: boolean; silent?: boolean } = {},
): Promise<ReadingProgressRecord | null> {
  if (!bookId || !snapshot) {
    return null;
  }

  const normalizedSnapshot: ReaderProgressSnapshot = {
    chapterIndex: snapshot.chapterIndex,
    scrollRatio: clampUnit(snapshot.scrollRatio),
    anchorType: normalizeReaderAnchorType(snapshot.anchorType),
    anchorIndex: Math.max(0, snapshot.anchorIndex),
    anchorOffsetRatio: clampUnit(snapshot.anchorOffsetRatio),
  };
  const snapshotKey = serializeProgressSnapshot(normalizedSnapshot);
  if (!options.force && snapshotKey === readerLastSavedProgressKey) {
    return null;
  }

  try {
    const progress = await saveReadingProgress(bookId, normalizedSnapshot);
    applyReadingProgressState(bookId, progress);
    return progress;
  } catch (error) {
    if (!options.silent) {
      lastMessage.value = `阅读进度保存失败：${toErrorMessage(error)}`;
    } else {
      console.error('阅读进度保存失败', error);
    }
    return null;
  }
}

async function persistCurrentReadingProgress(
  options: { force?: boolean; silent?: boolean } = {},
): Promise<ReadingProgressRecord | null> {
  return await persistReaderProgressSnapshot(selectedBookId.value, captureReaderProgressSnapshot(), options);
}

function scheduleReaderProgressSave() {
  if (
    typeof window === 'undefined' ||
    readerScrollSaveSuspended ||
    currentView.value !== 'reader' ||
    readerLoading.value ||
    !readerContent.value
  ) {
    return;
  }

  clearReaderScrollSaveTimer();
  readerScrollSaveTimer = window.setTimeout(() => {
    readerScrollSaveTimer = null;
    void persistCurrentReadingProgress({ silent: true });
  }, 420);
}

async function flushReaderProgressSave(options: { silent?: boolean } = {}): Promise<ReadingProgressRecord | null> {
  clearReaderScrollSaveTimer();
  return await persistCurrentReadingProgress({
    force: true,
    silent: options.silent ?? true,
  });
}

function handleReaderWindowScroll() {
  scheduleReaderProgressSave();
}

function updateScrollAffordances() {
  if (typeof window === 'undefined') {
    showBackToTopButton.value = false;
    return;
  }
  showBackToTopButton.value = currentView.value !== 'reader' && window.scrollY > BACK_TO_TOP_VISIBLE_SCROLL;
}

function handleWindowScroll() {
  handleReaderWindowScroll();
  updateScrollAffordances();
}

function scrollPageToTop() {
  if (typeof window === 'undefined') {
    return;
  }
  window.scrollTo({
    top: 0,
    behavior: 'smooth',
  });
}

function handleReaderAssetLoad() {
  if (readerPendingRestoreSnapshot) {
    void reapplyPendingReaderRestore();
  }
}

const activeTasks = computed(() => bookTasks.value.filter((task) => task.status === 'queued' || task.status === 'running'));
const failedTasks = computed(() => bookTasks.value.filter((task) => task.status === 'failed'));
const globalActiveTasks = computed(() =>
  globalTasks.value.filter((task) => task.status === 'queued' || task.status === 'running'),
);
const globalFailedTasks = computed(() => globalTasks.value.filter((task) => task.status === 'failed'));
const tasksOverviewItems = computed(() => globalTasks.value.slice(0, 8));
const logSummary = computed(() => {
  const total = activityLogs.value.length;
  const system = activityLogs.value.filter((entry) => entry.category === 'system').length;
  const action = activityLogs.value.filter((entry) => entry.category === 'action').length;
  const task = activityLogs.value.filter((entry) => entry.category === 'task').length;
  const error = activityLogs.value.filter((entry) => entry.category === 'error').length;
  return { total, system, action, task, error };
});

const providerModelOptions = computed(() => {
  const options: Record<TranslationProvider, string[]> = {
    openai: ['gpt-5.4', 'gpt-4.1', 'gpt-4o-mini'],
    anthropic: ['claude-3-7-sonnet-latest', 'claude-3-5-sonnet-latest', 'claude-3-5-haiku-latest'],
    grok2api: ['grok-4', 'grok-3', 'grok-3-reasoning', 'grok-3-deepsearch'],
    newapi: ['gpt-5.4', 'deepseek-chat', 'gemini-2.0-flash'],
    custom: ['custom-model', 'local-llm', 'translator-proxy'],
  };

  return options[activeProvider.value];
});

const detailSynopsis = computed(
  () =>
    bookDetail.value?.synopsis ||
    selectedBook.value?.synopsis ||
    '这本书尚未写入简介，你可以在后续版本中为站点适配专属摘要提取器。',
);

function readStoredReaderTheme(): ReaderTheme {
  if (typeof window === 'undefined') {
    return 'default';
  }
  const stored = window.localStorage.getItem(READER_THEME_STORAGE_KEY);
  return stored === 'default' || stored === 'care' || stored === 'night' ? stored : 'default';
}

function readStoredReaderFontSize(): ReaderFontSize {
  if (typeof window === 'undefined') {
    return '中';
  }
  const stored = window.localStorage.getItem(READER_FONT_SIZE_STORAGE_KEY);
  return stored === '小' || stored === '中' || stored === '大' || stored === '特大' ? stored : '中';
}

function normalizeReaderColor(value: string | null | undefined): string {
  const normalized = (value ?? '').trim();
  if (/^#[0-9a-fA-F]{6}$/.test(normalized)) {
    return normalized.toLowerCase();
  }
  if (/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return `#${normalized.toLowerCase()}`;
  }
  return '';
}

function readStoredReaderColor(storageKey: string): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return normalizeReaderColor(window.localStorage.getItem(storageKey));
}

function persistReaderPreferences() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(READER_THEME_STORAGE_KEY, readerTheme.value);
  window.localStorage.setItem(READER_FONT_SIZE_STORAGE_KEY, readerFontSize.value);
  if (readerTextColor.value) {
    window.localStorage.setItem(READER_TEXT_COLOR_STORAGE_KEY, readerTextColor.value);
  } else {
    window.localStorage.removeItem(READER_TEXT_COLOR_STORAGE_KEY);
  }
  if (readerBackgroundColor.value) {
    window.localStorage.setItem(READER_BACKGROUND_COLOR_STORAGE_KEY, readerBackgroundColor.value);
  } else {
    window.localStorage.removeItem(READER_BACKGROUND_COLOR_STORAGE_KEY);
  }
}

function logCategoryLabel(category: ActivityLogEntry['category']) {
  const labels: Record<ActivityLogEntry['category'], string> = {
    system: '系统',
    action: '操作',
    task: '任务',
    error: '异常',
  };
  return labels[category];
}

function buildLogId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildLogTime() {
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date());
}

function formatChapterOrder(index: number, bookKind: BookRecord['bookKind'] | PreviewResponse['bookKind'] | null | undefined): string {
  const normalizedIndex = Math.max(0, Math.trunc(index || 0));
  if (normalizedIndex <= 0) {
    return bookKind === '漫画' ? '未开始阅读' : '未开始阅读';
  }
  return `第 ${normalizedIndex} ${bookKind === '漫画' ? '话' : '章'}`;
}

function formatReadingTimestamp(value: string | null | undefined): string {
  const normalized = (value ?? '').trim();
  if (!normalized) {
    return '';
  }

  const parsed = new Date(normalized.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) {
    return normalized;
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
    .format(parsed)
    .replace(',', '');
}

function appendActivityLog(category: ActivityLogEntry['category'], title: string, detail: string) {
  const normalizedDetail = detail.trim();
  if (!normalizedDetail) {
    return;
  }
  const previous = activityLogs.value[0];
  if (previous && previous.category === category && previous.title === title && previous.detail === normalizedDetail) {
    return;
  }
  activityLogs.value = [
    {
      id: buildLogId(),
      category,
      title,
      detail: normalizedDetail,
      at: buildLogTime(),
    },
    ...activityLogs.value,
  ].slice(0, LOG_LIMIT);
}

function clearActivityLogs() {
  activityLogs.value = [];
  appendActivityLog('system', '日志已清空', '新的操作、下载和翻译记录会继续追加到这里。');
}

function logCardDescription(type: keyof typeof logSummary.value) {
  const labels = {
    total: '累计写入的全部日志',
    system: '桌面后端与运行状态',
    action: '导入、阅读与外链操作',
    task: '下载和翻译任务进度',
    error: '需要关注的失败与异常',
  };
  return labels[type];
}

async function bootstrap() {
  let backendReady = false;

  try {
    const backend = await startDesktopBackend();
    desktopState.value = backend
      ? `桌面后端已连接 ${backend.host}:${backend.port}`
      : '浏览器预览模式，未启动 Tauri sidecar';
    backendReady = true;
  } catch (error) {
    desktopState.value = `桌面后端启动失败：${toErrorMessage(error)}`;
  }

  const isTauriWindow = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
  if (isTauriWindow && !backendReady) {
    lastMessage.value = '桌面后端未就绪，已跳过书架初始化';
    return;
  }

  try {
    await refreshBooks();
  } catch (error) {
    books.value = [];
    lastMessage.value = `书架加载失败：${toErrorMessage(error)}`;
  }

  try {
    settings.value = await fetchSettings();
    activeProvider.value = settings.value.defaultProvider;
  } catch (error) {
    activeProvider.value = settings.value.defaultProvider;
    lastMessage.value = `设置加载失败：${toErrorMessage(error)}`;
  }

  try {
    await refreshGlobalTasks();
  } catch (error) {
    globalTasks.value = [];
    lastMessage.value = `任务总览加载失败：${toErrorMessage(error)}`;
  }
}

async function refreshBooks() {
  books.value = await fetchBooks();
  if (selectedBookId.value && books.value.some((item) => item.id === selectedBookId.value)) {
    return;
  }
  selectedBookId.value = books.value[0]?.id ?? null;
}

async function handlePreview() {
  if (!addBookForm.sourceUrl.trim()) {
    lastMessage.value = '请先输入作品链接';
    return;
  }

  loadingPreview.value = true;
  lastMessage.value = '正在解析站点并提取章节...';

  try {
    preview.value = await previewBook(addBookForm);
    addBookForm.bookKind = preview.value.bookKind;
    lastMessage.value =
      preview.value.bookKind === '漫画'
        ? `已自动识别为漫画，获取 ${preview.value.chapterCount} 话候选`
        : `已获取 ${preview.value.chapterCount} 个章节候选`;
  } catch (error) {
    preview.value = null;
    lastMessage.value = `预览失败：${toErrorMessage(error)}`;
  } finally {
    loadingPreview.value = false;
  }
}

async function handleImport() {
  if (!addBookForm.sourceUrl.trim()) {
    lastMessage.value = '导入前必须填写作品链接';
    return;
  }

  importing.value = true;
  lastMessage.value = '正在导入并写入本地文库...';

  try {
    const book = await importBook(addBookForm);
    updateBookCache(book);
    selectedBookId.value = book.id;
    await loadBookDetail(book.id);
    currentView.value = 'detail';
    lastMessage.value = `《${book.title}》已进入文库`;
    showImportPanel.value = false;
    preview.value = null;
    localBookFile.value = null;
    resetAddBookForm();
  } catch (error) {
    lastMessage.value = `导入失败：${toErrorMessage(error)}`;
  } finally {
    importing.value = false;
  }
}

function handleLocalFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null;
  localBookFile.value = input?.files?.[0] ?? null;
  if (localBookFile.value) {
    preview.value = null;
    lastMessage.value = `已选择本地文件：${localBookFile.value.name}`;
  }
}

async function handleImportLocal() {
  if (!localBookFile.value) {
    lastMessage.value = '请先选择本地 TXT 文件';
    return;
  }

  importing.value = true;
  lastMessage.value = `正在导入本地文件：${localBookFile.value.name}`;

  try {
    const book = await importLocalBook(localBookFile.value, {
      bookKind: addBookForm.bookKind,
      title: addBookForm.title,
      language: addBookForm.language,
      needTranslation: addBookForm.needTranslation,
    });
    updateBookCache(book);
    selectedBookId.value = book.id;
    await loadBookDetail(book.id);
    currentView.value = 'detail';
    lastMessage.value = `《${book.title}》已从本地文件导入`;
    showImportPanel.value = false;
    preview.value = null;
    localBookFile.value = null;
    resetAddBookForm();
  } catch (error) {
    lastMessage.value = `本地导入失败：${toErrorMessage(error)}`;
  } finally {
    importing.value = false;
  }
}

async function handleCoverFileChange(event: Event) {
  const book = selectedBook.value;
  const input = event.target as HTMLInputElement | null;
  const file = input?.files?.[0] ?? null;
  coverUploadPickerKey.value += 1;

  if (!book || !file) {
    return;
  }

  coverUploading.value = true;
  lastMessage.value = `正在上传《${book.title}》封面...`;

  try {
    const updatedBook = await uploadBookCover(book.id, file);
    updateBookCache(updatedBook);
    if (bookDetail.value?.book.id === updatedBook.id) {
      bookDetail.value = {
        ...bookDetail.value,
        book: updatedBook,
        title: updatedBook.title,
      };
    }
    lastMessage.value = `《${updatedBook.title}》封面已更新`;
  } catch (error) {
    lastMessage.value = `封面上传失败：${toErrorMessage(error)}`;
  } finally {
    coverUploading.value = false;
  }
}

async function handleDeleteSelectedBook() {
  const book = bookDetail.value?.book ?? selectedBook.value;
  if (!book) {
    return;
  }

  const confirmed = window.confirm(`确定删除《${book.title}》吗？这会同时移除本地章节、封面、任务记录和阅读进度。`);
  if (!confirmed) {
    return;
  }

  deletingBook.value = true;
  lastMessage.value = `正在删除《${book.title}》...`;

  try {
    await deleteBook(book.id);
    await refreshBooks().catch(() => {
      books.value = books.value.filter((item) => item.id !== book.id);
    });
    globalTasks.value = globalTasks.value.filter((task) => task.bookId !== book.id);
    bookTasks.value = bookTasks.value.filter((task) => task.bookId !== book.id);
    selectedChapterIndexes.value = [];
    activeChapterIndex.value = null;
    readerContent.value = null;
    readerError.value = '';
    bookDetail.value = null;
    selectedBookId.value = null;
    currentView.value = 'library';
    stopTaskPolling();
    await refreshGlobalTasks().catch(() => undefined);
    lastMessage.value = `《${book.title}》已删除`;
  } catch (error) {
    lastMessage.value = `删除书籍失败：${toErrorMessage(error)}`;
  } finally {
    deletingBook.value = false;
  }
}

function triggerCoverUpload() {
  coverFileInput.value?.click();
}

function resetAddBookForm() {
  addBookForm.title = '';
  addBookForm.sourceUrl = '';
  addBookForm.bookKind = '长小说';
  addBookForm.language = '中文';
  addBookForm.needTranslation = false;
  localBookFile.value = null;
  localFilePickerKey.value += 1;
}

async function handleSaveSettings() {
  savingSettings.value = true;
  try {
    settings.value.downloadConcurrency = Math.max(1, Math.min(8, Math.trunc(settings.value.downloadConcurrency || 1)));
    settings.value = await saveSettings(settings.value);
    activeProvider.value = settings.value.defaultProvider;
    lastMessage.value = `已保存 ${settings.value.defaultProvider} 翻译配置`;
  } catch (error) {
    lastMessage.value = `设置保存失败：${toErrorMessage(error)}`;
  } finally {
    savingSettings.value = false;
  }
}

async function loadBookDetail(bookId: string) {
  detailLoading.value = true;
  detailError.value = '';
  readerError.value = '';

  try {
    applyBookDetail(await fetchBookDetail(bookId));
    try {
      await refreshBookTasks(bookId);
    } catch (taskError) {
      bookTasks.value = [];
      lastMessage.value = `任务队列同步失败：${toErrorMessage(taskError)}`;
    }
    lastMessage.value = `已读取《${bookDetail.value?.title || ''}》的 ${bookDetail.value?.chapters.length || 0} 章本地内容`;
  } catch (error) {
    bookDetail.value = null;
    readerContent.value = null;
    bookTasks.value = [];
    detailError.value = toErrorMessage(error);
    lastMessage.value = `章节加载失败：${detailError.value}`;
  } finally {
    detailLoading.value = false;
  }
}

async function loadReaderChapter(
  bookId: string,
  chapterIndex: number,
  mode: 'original' | 'translated' = readerMode.value,
  options: LoadReaderChapterOptions = {},
) {
  const autoTranslate = options.autoTranslate ?? true;
  const restoreProgress =
    options.restoreProgress && options.restoreProgress.chapterIndex === chapterIndex ? options.restoreProgress : null;
  const initialProgressSnapshot =
    restoreProgress ?? (options.scrollToTop === false ? null : buildTopProgressSnapshot(chapterIndex));
  const shouldPersistInitialProgress = Boolean(initialProgressSnapshot) && !restoreProgress;

  activeChapterIndex.value = chapterIndex;
  if (!selectedChapterIndexes.value.includes(chapterIndex)) {
    selectedChapterIndexes.value = [...selectedChapterIndexes.value, chapterIndex];
  }

  readerLoading.value = true;
  readerError.value = '';

  try {
    readerContent.value = await fetchChapterContent(bookId, chapterIndex, mode);
    readerMode.value = readerContent.value.mode;
    readerLoading.value = false;

    if (initialProgressSnapshot) {
      await applyReaderViewportProgress(initialProgressSnapshot, options.scrollBehavior ?? 'auto');
    } else {
      clearPendingReaderRestore();
    }

    if (shouldPersistInitialProgress) {
      await persistReaderProgressSnapshot(bookId, initialProgressSnapshot, {
        force: true,
        silent: false,
      });
    }

    lastMessage.value = `正在阅读：${readerContent.value.chapter.title}`;
    if (!autoTranslate) {
      return;
    }
    await triggerAutoTranslateOnRead(bookId, chapterIndex);
  } catch (error) {
    readerContent.value = null;
    readerError.value = toErrorMessage(error);
    lastMessage.value = `正文加载失败：${readerError.value}`;
  } finally {
    readerLoading.value = false;
  }
}

async function navigate(view: ViewMode) {
  if (currentView.value === 'reader' && view !== 'reader') {
    await flushReaderProgressSave({ silent: true });
  }
  currentView.value = view;
  if (view === 'settings') {
    showImportPanel.value = false;
  }
  if (view === 'library' || view === 'logs') {
    stopTaskPolling();
    void refreshGlobalTasks();
    return;
  }
  if (view === 'settings') {
    tasksOverviewOpen.value = false;
  }
  if (view === 'settings' || view === 'detail' || view === 'reader') {
    stopGlobalTaskPolling();
    stopTaskPolling();
  }
}

async function openBook(bookId: string) {
  stopGlobalTaskPolling();
  tasksOverviewOpen.value = false;
  readerChapterPickerOpen.value = false;
  selectedBookId.value = bookId;
  currentView.value = 'detail';
  await loadBookDetail(bookId);
}

async function openReader(chapterIndex?: number | null, options: OpenReaderOptions = {}) {
  const book = selectedBook.value;
  if (!book) {
    return;
  }

  const previousView = currentView.value;
  const previousBookId = selectedBookId.value;
  const previousChapterIndex = readerChapter.value?.index ?? null;
  const previousMode = readerMode.value;

  if (!bookDetail.value || bookDetail.value.book.id !== book.id) {
    selectedBookId.value = book.id;
    await loadBookDetail(book.id);
  }

  const targetIndex = chapterIndex ?? persistedReadingProgress.value.continueIndex ?? activeChapterIndex.value ?? chapters.value[0]?.index ?? null;
  if (
    previousView === 'reader' &&
    previousBookId === book.id &&
    readerContent.value &&
    (previousChapterIndex !== targetIndex || (options.mode && options.mode !== previousMode))
  ) {
    await flushReaderProgressSave({ silent: true });
  }

  selectedBookId.value = book.id;
  currentView.value = 'reader';
  showReaderPanel.value = false;
  readerChapterPickerOpen.value = false;

  if (targetIndex === null) {
    readerContent.value = null;
    return;
  }

  const restoreProgress =
    options.restoreProgress ??
    (options.restoreSavedProgress ? buildPersistedProgressSnapshot(targetIndex) : null);

  await loadReaderChapter(book.id, targetIndex, options.mode ?? readerMode.value, {
    autoTranslate: options.autoTranslate,
    restoreProgress,
    scrollToTop: options.scrollToTop ?? !restoreProgress,
    scrollBehavior: options.scrollBehavior ?? (restoreProgress ? 'auto' : 'auto'),
  });
}

async function handleDownloadSelected() {
  if (!selectedBookId.value || selectedChapterIndexes.value.length === 0) {
    lastMessage.value = '请先选择要下载的章节';
    return;
  }

  chapterActionLoading.value = 'download';
  try {
    const task = await downloadChapters(selectedBookId.value, {
      chapterIndexes: selectedChapterIndexes.value,
    });
    upsertTaskCollections(task);
    startTaskPolling(selectedBookId.value);
    lastMessage.value = `已加入下载队列，共 ${task.totalCount} 章`;
  } catch (error) {
    lastMessage.value = `章节下载失败：${toErrorMessage(error)}`;
  } finally {
    chapterActionLoading.value = null;
  }
}

async function handleTranslateSelected() {
  if (!selectedBookId.value || selectedChapterIndexes.value.length === 0) {
    lastMessage.value = '请先选择要翻译的章节';
    return;
  }

  chapterActionLoading.value = 'translate';
  try {
    const task = await translateChapters(selectedBookId.value, {
      chapterIndexes: selectedChapterIndexes.value,
    });
    upsertTaskCollections(task);
    startTaskPolling(selectedBookId.value);
    lastMessage.value = `已加入翻译队列，共 ${task.totalCount} 章`;
  } catch (error) {
    lastMessage.value = `章节翻译失败：${toErrorMessage(error)}`;
  } finally {
    chapterActionLoading.value = null;
  }
}

async function toggleReaderMode() {
  if (!selectedBookId.value || !readerChapter.value) {
    return;
  }

  const nextMode = readerMode.value === 'translated' ? 'original' : 'translated';
  await openReader(readerChapter.value.index, {
    mode: nextMode,
    autoTranslate: false,
    restoreProgress: captureReaderProgressSnapshot(readerChapter.value.index),
    scrollToTop: false,
  });
}

async function backToLibrary() {
  readerChapterPickerOpen.value = false;
  await navigate('library');
}

async function backToDetail() {
  readerChapterPickerOpen.value = false;
  await flushReaderProgressSave({ silent: true });
  currentView.value = 'detail';
}

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value;
}

async function handleOpenExternal(url: string | null | undefined, label = '链接') {
  const target = url?.trim() ?? '';
  if (!target) {
    lastMessage.value = `${label}不存在或暂未写入`;
    return;
  }

  try {
    await openExternalLink(target);
    lastMessage.value = `已打开${label}`;
  } catch (error) {
    lastMessage.value = `打开${label}失败：${toErrorMessage(error)}`;
  }
}

function isTauriRuntime() {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

function triggerBrowserDownload(url: string, fileName: string) {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.rel = 'noopener noreferrer';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

function buildDefaultExportFileName(title: string, format: BookExportFormat) {
  const normalized = title.replace(/[\\/:*?"<>|]+/g, '_').trim() || '未命名小说';
  return `${normalized}.${format}`;
}

function toggleExportMenu() {
  if (!chapters.value.length || exportingFormat.value !== null) {
    return;
  }
  exportMenuOpen.value = !exportMenuOpen.value;
}

async function handleExportBook(format: BookExportFormat) {
  if (!selectedBookId.value || !selectedBook.value) {
    lastMessage.value = '请先选择要导出的书籍';
    return;
  }

  const tauriRuntime = isTauriRuntime();

  try {
    let targetPath: string | undefined;
    if (tauriRuntime) {
      const selectedPath = await chooseExportPath(buildDefaultExportFileName(selectedBook.value.title, format), format);
      if (!selectedPath) {
        lastMessage.value = '已取消导出';
        return;
      }
      targetPath = selectedPath;
    }

    exportingFormat.value = format;
    const result = await exportBook(selectedBookId.value, format, targetPath);
    if (tauriRuntime) {
      lastMessage.value = `已导出 ${format.toUpperCase()}：${result.filePath}`;
      return;
    }

    triggerBrowserDownload(result.downloadUrl, result.fileName);
    lastMessage.value = `已生成 ${format.toUpperCase()} 导出文件：${result.fileName}`;
  } catch (error) {
    lastMessage.value = `导出 ${format.toUpperCase()} 失败：${toErrorMessage(error)}`;
  } finally {
    exportingFormat.value = null;
    exportMenuOpen.value = false;
  }
}

function setDefaultProvider(provider: TranslationProvider) {
  settings.value.defaultProvider = provider;
  settings.value.providers[provider].enabled = true;
  activeProvider.value = provider;
}

function applyReaderTheme(theme: ReaderTheme) {
  readerTheme.value = theme;
  persistReaderPreferences();
}

function applyReaderFontSize(size: ReaderFontSize) {
  readerFontSize.value = size;
  persistReaderPreferences();
}

function applyReaderTextColor(value: string) {
  readerTextColor.value = normalizeReaderColor(value);
  persistReaderPreferences();
}

function applyReaderBackgroundColor(value: string) {
  readerBackgroundColor.value = normalizeReaderColor(value);
  persistReaderPreferences();
}

function resetReaderColors() {
  readerTextColor.value = '';
  readerBackgroundColor.value = '';
  persistReaderPreferences();
}

function autoTranslateLabel(value: number): string {
  return autoTranslateOptions.find((item) => item.value === value)?.label ?? '关闭';
}

function canAutoTranslateOnRead(book: BookRecord | null): boolean {
  if (!book) {
    return false;
  }
  if (settings.value.autoTranslateNextChapters === 0) {
    return false;
  }
  if (book.language === '中文') {
    return false;
  }
  const provider = settings.value.defaultProvider;
  const config = settings.value.providers[provider];
  return Boolean(
    config.enabled &&
      config.apiKey.trim() &&
      config.baseUrl.trim() &&
      config.model.trim(),
  );
}

function getAutoTranslateChapterIndexes(currentIndex: number): number[] {
  const pendingTranslationIndexes = new Set(
    bookTasks.value
      .filter((task) => task.taskType === 'translate' && (task.status === 'queued' || task.status === 'running'))
      .flatMap((task) => task.chapterIndexes),
  );
  const remainingChapters = chapters.value.filter(
    (chapter) =>
      chapter.index >= currentIndex &&
      chapter.downloaded &&
      !chapter.translated &&
      !pendingTranslationIndexes.has(chapter.index),
  );
  if (!remainingChapters.length) {
    return [];
  }

  if (settings.value.autoTranslateNextChapters === -1) {
    return remainingChapters.map((chapter) => chapter.index);
  }

  return remainingChapters
    .slice(0, settings.value.autoTranslateNextChapters + 1)
    .map((chapter) => chapter.index);
}

async function triggerAutoTranslateOnRead(bookId: string, chapterIndex: number) {
  const book = selectedBook.value;
  if (!book || book.id !== bookId || !canAutoTranslateOnRead(book)) {
    return;
  }

  const chapterIndexes = getAutoTranslateChapterIndexes(chapterIndex);
  if (!chapterIndexes.length) {
    return;
  }

  try {
    const task = await translateChapters(bookId, { chapterIndexes });
    upsertTaskCollections(task);
    startTaskPolling(bookId);
    lastMessage.value = `已按阅读偏好加入预翻译队列：当前章 + ${autoTranslateLabel(settings.value.autoTranslateNextChapters)}`;
  } catch (error) {
    lastMessage.value = `自动预翻译失败：${toErrorMessage(error)}`;
  }
}

function formatChapterCount(
  count: number,
  bookKind: BookRecord['bookKind'] | PreviewResponse['bookKind'] = '轻小说',
): string {
  return `${count} ${bookKind === '漫画' ? '话' : '章'}`;
}

function formatWordCount(count: number): string {
  return `${count.toLocaleString('en-US')} 字`;
}

function formatPageCount(count: number): string {
  return `${count.toLocaleString('en-US')} 页`;
}

function formatContentCount(count: number, bookKind: BookRecord['bookKind'] | PreviewResponse['bookKind'] = '轻小说'): string {
  return bookKind === '漫画' ? formatPageCount(count) : formatWordCount(count);
}

function formatChapterMeta(chapter: ChapterRecord, bookKind: BookRecord['bookKind'] | null | undefined): string {
  if (bookKind === '漫画') {
    return formatPageCount(chapter.pageCount || chapter.imageCount || 0);
  }
  return formatWordCount(chapter.wordCount);
}

function setActiveChapter(chapterIndex: number) {
  activeChapterIndex.value = chapterIndex;
  if (!selectedChapterIndexes.value.includes(chapterIndex)) {
    selectedChapterIndexes.value = [...selectedChapterIndexes.value, chapterIndex];
  }
}

async function handleContinueReading() {
  await openReader(persistedReadingProgress.value.continueIndex, {
    restoreSavedProgress: true,
  });
}

async function handleReadSelectedChapter() {
  await openReader(activeChapterIndex.value, {
    scrollToTop: true,
  });
}

async function selectReaderChapter(chapterIndex: number) {
  if (!selectedBookId.value) {
    return;
  }
  readerChapterPickerOpen.value = false;
  await openReader(chapterIndex, {
    scrollToTop: true,
    scrollBehavior: 'smooth',
  });
}

function toggleAllChapters() {
  if (allChaptersSelected.value) {
    selectedChapterIndexes.value = [];
    return;
  }

  selectedChapterIndexes.value = chapters.value.map((chapter) => chapter.index);
  if (!activeChapterIndex.value && chapters.value[0]) {
    activeChapterIndex.value = chapters.value[0].index;
  }
}

async function goToAdjacentChapter(offset: -1 | 1) {
  const currentIndex = chapters.value.findIndex((chapter) => chapter.index === activeChapterIndex.value);
  if (currentIndex < 0) {
    return;
  }

  const nextChapter = chapters.value[currentIndex + offset];
  if (!nextChapter) {
    return;
  }

  await openReader(nextChapter.index, {
    scrollToTop: true,
    scrollBehavior: 'smooth',
  });
}

function coverSeed(value: string): number {
  return value.split('').reduce((seed, char) => seed + char.charCodeAt(0), 0);
}

function getPresentation(book: BookRecord): BookPresentation {
  const seed = coverSeed(book.id);
  const authors = ['蝴蝶蓝', '长月达平', 'J.R.R. Tolkien', '爱潜水的乌贼', 'Priest', 'A. Sterling'];
  const addedDays = (seed % 7) + 11;

  return {
    author: authors[seed % authors.length],
    coverClass: `cover-${seed % 6}`,
    accentClass: `accent-${seed % 4}`,
    progressCurrent: Math.max(0, Math.min(book.chapterCount, book.lastReadChapterIndex || 0)),
    progressTotal: Math.max(book.chapterCount, 1),
    addedAt: `2026-03-${String(addedDays).padStart(2, '0')}`,
    words: '0',
    serialState: book.status === '已完成' ? '已完结' : '连载中',
  };
}

function getCoverClass(book: BookRecord): string {
  return book.cover ? 'cover-has-image' : getPresentation(book).coverClass;
}

function providerCardClass(provider: TranslationProvider) {
  return {
    'provider-option': true,
    active: activeProvider.value === provider,
  };
}

function syncChapterSelection(nextChapters: ChapterRecord[], progressIndex = 0) {
  const availableIndexes = new Set(nextChapters.map((chapter) => chapter.index));
  const retained = selectedChapterIndexes.value.filter((chapterIndex) => availableIndexes.has(chapterIndex));
  const fallbackIndex =
    (progressIndex && availableIndexes.has(progressIndex) ? progressIndex : null) ?? nextChapters[0]?.index ?? null;
  selectedChapterIndexes.value = retained.length > 0 ? retained : fallbackIndex ? [fallbackIndex] : [];

  if (activeChapterIndex.value && availableIndexes.has(activeChapterIndex.value)) {
    return;
  }

  activeChapterIndex.value = fallbackIndex;
}

function updateBookCache(book: BookRecord) {
  const currentIndex = books.value.findIndex((item) => item.id === book.id);
  if (currentIndex === -1) {
    books.value = [book, ...books.value];
    return;
  }

  books.value = books.value.map((item) => (item.id === book.id ? book : item));
}

function updateBookProgressCache(bookId: string, progress: Pick<ReadingProgressRecord, 'lastChapterIndex' | 'lastReadAt'>) {
  books.value = books.value.map((item) =>
    item.id === bookId
      ? {
          ...item,
          lastReadChapterIndex: progress.lastChapterIndex,
          lastReadAt: progress.lastReadAt ?? null,
        }
      : item,
  );
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return String(error);
}

function applyBookDetail(detail: BookDetailResponse) {
  bookDetail.value = detail;
  updateBookCache(detail.book);
  syncChapterSelection(detail.chapters, detail.progress.lastChapterIndex);
}

async function refreshGlobalTasks() {
  globalTasksLoading.value = true;
  try {
    const tasks = await fetchTasks();
    const previousStamp = lastGlobalTaskStamp.value;
    globalTasks.value = tasks;
    syncTaskLogState(tasks);
    await syncTaskRuntimeLogs(tasks);
    const currentStamp = tasks
      .filter((task) => task.status === 'completed' || task.status === 'failed')
      .map((task) => `${task.id}:${task.status}:${task.updatedAt}`)
      .join('|');
    lastGlobalTaskStamp.value = currentStamp;

    if (globalActiveTasks.value.length) {
      if ((currentView.value === 'library' || currentView.value === 'logs') && globalTaskPollTimer === null) {
        globalTaskPollTimer = window.setInterval(() => {
          if (currentView.value !== 'library' && currentView.value !== 'logs') {
            stopGlobalTaskPolling();
            return;
          }
          void refreshGlobalTasks();
        }, 1500);
      }
    } else {
      stopGlobalTaskPolling();
      if (currentStamp && currentStamp !== previousStamp && currentView.value === 'detail' && selectedBookId.value) {
        void refreshBookTasks(selectedBookId.value);
      }
    }
  } finally {
    globalTasksLoading.value = false;
  }
}

async function refreshBookTasks(bookId: string) {
  tasksLoading.value = true;
  try {
    const tasks = await fetchBookTasks(bookId);
    const previousStamp = lastCompletedTaskStamp.value;
    bookTasks.value = tasks;
    syncTaskLogState(tasks);
    await syncTaskRuntimeLogs(tasks);
    const currentStamp = tasks
      .filter((task) => task.status === 'completed' || task.status === 'failed')
      .map((task) => `${task.id}:${task.status}:${task.updatedAt}`)
      .join('|');
    lastCompletedTaskStamp.value = currentStamp;

    if (activeTasks.value.length) {
      if (taskPollTimer === null) {
        taskPollTimer = window.setInterval(() => {
          if (!selectedBookId.value || selectedBookId.value !== bookId) {
            stopTaskPolling();
            return;
          }
          void refreshBookTasks(bookId);
        }, 1500);
      }
    } else {
      stopTaskPolling();
      if (currentStamp && currentStamp !== previousStamp) {
        await loadBookDetailWithoutTasks(bookId);
      }
    }
  } finally {
    tasksLoading.value = false;
  }
}

async function loadBookDetailWithoutTasks(bookId: string) {
  try {
    applyBookDetail(await fetchBookDetail(bookId));
    if (currentView.value === 'reader' && activeChapterIndex.value && selectedBookId.value === bookId) {
      await loadReaderChapter(bookId, activeChapterIndex.value, readerMode.value, false);
    }
  } catch {
    // ignore background refresh failures, explicit loads surface errors elsewhere
  }
}

function startTaskPolling(bookId: string) {
  stopTaskPolling();
  void refreshGlobalTasks();
  void refreshBookTasks(bookId);
}

function stopTaskPolling() {
  if (taskPollTimer !== null) {
    window.clearInterval(taskPollTimer);
    taskPollTimer = null;
  }
}

function startGlobalTaskPolling() {
  stopGlobalTaskPolling();
  void refreshGlobalTasks();
}

function stopGlobalTaskPolling() {
  if (globalTaskPollTimer !== null) {
    window.clearInterval(globalTaskPollTimer);
    globalTaskPollTimer = null;
  }
}

function upsertTask(task: TaskRecord) {
  const index = bookTasks.value.findIndex((item) => item.id === task.id);
  if (index === -1) {
    bookTasks.value = [task, ...bookTasks.value];
    return;
  }
  bookTasks.value = bookTasks.value.map((item) => (item.id === task.id ? task : item));
}

function upsertGlobalTask(task: TaskRecord) {
  const index = globalTasks.value.findIndex((item) => item.id === task.id);
  if (index === -1) {
    globalTasks.value = [task, ...globalTasks.value];
    return;
  }
  globalTasks.value = globalTasks.value.map((item) => (item.id === task.id ? task : item));
}

function upsertTaskCollections(task: TaskRecord) {
  if (!taskLogSyncState.has(task.id)) {
    taskLogSyncState.set(task.id, {
      sequence: 0,
      signature: taskRuntimeSignature(task),
    });
  }
  upsertTask(task);
  upsertGlobalTask(task);
  syncTaskLogState([task]);
}

async function handleRetryTask(taskId: string) {
  taskRetryingId.value = taskId;
  try {
    const task = await retryTask(taskId);
    upsertTaskCollections(task);
    if (currentView.value !== 'library' && selectedBookId.value) {
      startTaskPolling(selectedBookId.value);
    }
    if (currentView.value === 'library') {
      startGlobalTaskPolling();
    }
    lastMessage.value = '失败任务已重新加入队列';
  } catch (error) {
    lastMessage.value = `任务重试失败：${toErrorMessage(error)}`;
  } finally {
    taskRetryingId.value = null;
  }
}

function taskTypeLabel(task: TaskRecord) {
  return task.taskType === 'download' ? '下载任务' : '翻译任务';
}

function taskStatusLabel(status: TaskRecord['status']) {
  const labels: Record<TaskRecord['status'], string> = {
    queued: '排队中',
    running: '进行中',
    completed: '已完成',
    failed: '失败',
  };
  return labels[status];
}

function taskLogTitle(task: TaskRecord) {
  return `${taskBookTitle(task)} · ${taskTypeLabel(task)} ${taskStatusLabel(task.status)}`;
}

function syncTaskLogState(tasks: TaskRecord[]) {
  tasks.forEach((task) => {
    const signature = [
      task.status,
      task.completedCount,
      task.totalCount,
      task.error ?? '',
    ].join('|');
    const previous = taskLogSignatures.get(task.id);
    if (previous === signature) {
      return;
    }
    taskLogSignatures.set(task.id, signature);
    if (previous === undefined && task.status !== 'queued' && task.status !== 'running') {
      return;
    }
    appendActivityLog(
      task.status === 'failed' ? 'error' : 'task',
      taskLogTitle(task),
      task.error?.trim() || task.message || `章节 ${task.completedCount} / ${task.totalCount}`,
    );
  });
}

function taskRuntimeSignature(task: TaskRecord) {
  return [
    task.status,
    task.completedCount,
    task.totalCount,
    task.updatedAt,
    task.message,
    task.error ?? '',
  ].join('|');
}

async function fetchAndAppendTaskLogs(task: TaskRecord): Promise<void> {
  const state = taskLogSyncState.get(task.id) ?? { sequence: 0, signature: '' };
  const requestKey = `${task.id}:${state.sequence}`;
  const pending = taskLogRequests.get(requestKey);
  if (pending) {
    await pending;
    return;
  }

  const request = (async () => {
    try {
      const logs = await fetchTaskLogs(task.id, state.sequence);
      if (logs.length) {
        taskLogSyncState.set(task.id, {
          sequence: logs[logs.length - 1]?.sequence ?? state.sequence,
          signature: taskRuntimeSignature(task),
        });
        logs.forEach((entry) => {
          appendActivityLog(entry.level === 'error' ? 'error' : 'task', taskLogTitle(task), entry.message);
        });
      } else {
        taskLogSyncState.set(task.id, {
          sequence: state.sequence,
          signature: taskRuntimeSignature(task),
        });
      }
    } catch {
      taskLogSyncState.set(task.id, {
        sequence: state.sequence,
        signature: '',
      });
    } finally {
      taskLogRequests.delete(requestKey);
    }
  })();

  taskLogRequests.set(requestKey, request);
  await request;
}

async function syncTaskRuntimeLogs(tasks: TaskRecord[]) {
  const targets = tasks.filter((task) => {
    const currentSignature = taskRuntimeSignature(task);
    const previous = taskLogSyncState.get(task.id);
    if (!previous) {
      taskLogSyncState.set(task.id, { sequence: 0, signature: currentSignature });
      return task.status === 'queued' || task.status === 'running';
    }
    return previous.signature !== currentSignature;
  });

  if (!targets.length) {
    return;
  }

  await Promise.all(targets.map((task) => fetchAndAppendTaskLogs(task)));
}

function toggleTasksOverview() {
  tasksOverviewOpen.value = !tasksOverviewOpen.value;
  if (tasksOverviewOpen.value) {
    startGlobalTaskPolling();
  }
}

function taskBookTitle(task: TaskRecord) {
  return books.value.find((item) => item.id === task.bookId)?.title ?? `书籍 ${task.bookId.slice(0, 8)}`;
}

async function openTaskBook(task: TaskRecord) {
  await openBook(task.bookId);
}

watch(desktopState, (value, previous) => {
  if (!value || value === previous) {
    return;
  }
  appendActivityLog(value.includes('失败') ? 'error' : 'system', '桌面状态', value);
}, { immediate: true });

watch(lastMessage, (value, previous) => {
  if (!value || value === previous || value === '等待输入小说链接') {
    return;
  }
  appendActivityLog(value.includes('失败') ? 'error' : 'action', '操作日志', value);
});

watch(readerTheme, (value, previous) => {
  persistReaderPreferences();
  if (!previous || value === previous) {
    return;
  }
  appendActivityLog('action', '应用主题已切换', `当前主题：${themeOptions.find((item) => item.key === value)?.label ?? value}`);
});

watch(readerFontSize, (value, previous) => {
  persistReaderPreferences();
  if (!previous || value === previous) {
    return;
  }
  appendActivityLog('action', '阅读字号已切换', `当前字号：${value}`);
});

watch(readerTextColor, (value, previous) => {
  persistReaderPreferences();
  if (value === previous) {
    return;
  }
  appendActivityLog('action', '阅读字色已更新', value ? `当前字色：${value}` : '已恢复跟随主题');
});

watch(readerBackgroundColor, (value, previous) => {
  persistReaderPreferences();
  if (value === previous) {
    return;
  }
  appendActivityLog('action', '阅读背景已更新', value ? `当前背景：${value}` : '已恢复跟随主题');
});

watch(currentView, (value, previous) => {
  if (previous === 'reader' && value !== 'reader') {
    clearPendingReaderRestore();
  }
  updateScrollAffordances();
});

onMounted(() => {
  window.addEventListener('scroll', handleWindowScroll, { passive: true });
  updateScrollAffordances();
  void bootstrap();
});

onBeforeUnmount(() => {
  window.removeEventListener('scroll', handleWindowScroll);
  void flushReaderProgressSave({ silent: true });
  clearReaderScrollSaveTimer();
  clearReaderScrollReleaseTimer();
  clearPendingReaderRestore();
  stopTaskPolling();
  stopGlobalTaskPolling();
});
</script>

<template>
  <div
    class="shell"
    :class="{
      'shell--sidebar-collapsed': sidebarCollapsed,
      'shell--reader-mode': currentView === 'reader',
    }"
    :data-reader-theme="readerTheme"
    :data-font-size="readerFontSize"
    :style="readerCustomStyle"
  >
    <aside class="sidebar">
      <div class="brand-row">
        <div class="brand">
          <img
            :src="brandIcon"
            alt="青卷图标"
            class="brand-mark"
          />
          <div class="brand-copy">
            <h1>青卷</h1>
            <p>小说集成管理</p>
          </div>
        </div>
        <button
          class="icon-btn sidebar-toggle"
          :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
          @click="toggleSidebar"
        >
          {{ sidebarCollapsed ? '›' : '‹' }}
        </button>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="{ active: currentView === item.key }"
          :title="item.label"
          @click="navigate(item.key)"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <p>{{ desktopState }}</p>
        <span>v0.2.1</span>
      </div>
    </aside>

    <section class="main-area">
      <template v-if="currentView === 'library'">
        <header class="page-head">
          <div>
            <p class="page-kicker">我的书架</p>
            <h2>我的书架</h2>
            <p class="page-subtitle">已收藏 {{ books.length }} 本作品</p>
          </div>
          <button
            class="primary-btn"
            @click="showImportPanel = true"
          >
            <span>＋</span>
            添加书籍
          </button>
        </header>

        <section class="toolbar">
          <label class="search-field">
            <span>⌕</span>
            <input
              v-model="searchQuery"
              placeholder="搜索书名或作者..."
              type="text"
            />
          </label>
        </section>

        <section class="summary-row">
          <article
            v-for="item in stats"
            :key="item.label"
            class="summary-card"
          >
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.suffix }}</small>
          </article>

          <button
            class="summary-card task-overview-entry"
            :class="{ active: tasksOverviewOpen, busy: globalActiveTasks.length > 0 }"
            type="button"
            @click="toggleTasksOverview"
          >
            <span>进行中任务</span>
            <strong>{{ globalActiveTasks.length }}</strong>
            <small>
              {{
                globalFailedTasks.length > 0
                  ? `失败 ${globalFailedTasks.length} 个，点击查看详情`
                  : globalActiveTasks.length > 0
                    ? '下载与翻译任务正在后台执行'
                    : '当前没有进行中的任务'
              }}
            </small>
          </button>
        </section>

        <section class="library-theme-panel">
          <div class="chapter-head library-theme-head">
            <div>
              <h3>应用主题</h3>
              <p>在主页切换整个软件的主题，书架、设置、详情和阅读页会同时生效。</p>
            </div>
            <span class="book-state-pill">当前 {{ readerThemeLabel }} · {{ readerFontSize }}</span>
          </div>

          <div class="theme-preview-grid">
            <button
              v-for="theme in themeOptions"
              :key="theme.key"
              class="theme-preview-card"
              :class="{ active: readerTheme === theme.key }"
              :data-theme-key="theme.key"
              type="button"
              @click="applyReaderTheme(theme.key)"
            >
              <strong>{{ theme.label }}</strong>
              <p>{{ theme.description }}</p>
              <span>{{ theme.preview }}</span>
            </button>
          </div>

          <div class="theme-live-preview">
            <div class="theme-live-toolbar">
              <span>整页预览</span>
              <div class="theme-live-actions">
                <button class="ghost-btn compact">原文</button>
                <button class="ghost-btn compact active-preview-btn">译文</button>
              </div>
            </div>
            <article class="theme-live-paper">
              <h4>第一章 初识异世界</h4>
              <p>晨雾像未翻完的书页一样铺在窗边，主角在安静的房间里重新整理思绪，准备继续读下去。</p>
              <p>这里会实时预览当前应用主题的正文底色、文字颜色、按钮和面板层次，不再只显示按钮选中态变化。</p>
            </article>
          </div>
        </section>

        <transition name="panel-fade">
          <section
            v-if="tasksOverviewOpen"
            class="task-overview-panel"
          >
            <div class="chapter-head task-overview-head">
              <div>
                <h3>任务总览</h3>
                <p v-if="globalTasksLoading">正在同步所有书籍的任务状态...</p>
                <p v-else>运行中 {{ globalActiveTasks.length }} 个，失败 {{ globalFailedTasks.length }} 个</p>
              </div>
              <button
                class="ghost-btn compact"
                type="button"
                @click="tasksOverviewOpen = false"
              >
                收起
              </button>
            </div>

            <div
              v-if="!tasksOverviewItems.length"
              class="status-note flush"
            >
              <strong>暂无任务</strong>
              <p>下载和翻译任务开始后，这里会汇总显示所有进行中与历史结果。</p>
            </div>

            <div
              v-else
              class="task-list task-list-compact"
            >
              <article
                v-for="task in tasksOverviewItems"
                :key="task.id"
                class="task-row"
              >
                <div class="task-copy">
                  <div class="task-meta">
                    <strong>{{ taskTypeLabel(task) }}</strong>
                    <span :data-task-status="task.status">{{ taskStatusLabel(task.status) }}</span>
                  </div>
                  <p>{{ taskBookTitle(task) }}</p>
                  <small>{{ task.message || '等待任务状态更新' }}</small>
                  <small>章节 {{ task.completedCount }} / {{ task.totalCount }}</small>
                  <small v-if="task.error">{{ task.error }}</small>
                </div>

                <div class="task-side">
                  <div class="task-progress">
                    <div
                      class="task-progress-fill"
                      :style="{ width: `${task.progress}%` }"
                    ></div>
                  </div>

                  <div class="task-actions">
                    <button
                      class="ghost-btn compact"
                      type="button"
                      @click="openTaskBook(task)"
                    >
                      查看书籍
                    </button>
                    <button
                      v-if="task.status === 'failed'"
                      class="ghost-btn compact"
                      :disabled="taskRetryingId === task.id"
                      type="button"
                      @click="handleRetryTask(task.id)"
                    >
                      {{ taskRetryingId === task.id ? '重试中...' : '失败重试' }}
                    </button>
                  </div>
                </div>
              </article>
            </div>
          </section>
        </transition>

        <section class="books-grid">
          <article
            v-for="book in filteredBooks"
            :key="book.id"
            class="shelf-card"
            @click="openBook(book.id)"
          >
            <div
              class="cover-art"
              :class="getCoverClass(book)"
            >
              <img
                v-if="book.cover"
                :src="book.cover"
                :alt="`${book.title} 封面`"
                class="cover-image"
                loading="lazy"
              />
              <div
                v-if="book.cover"
                class="cover-filter"
              ></div>
              <div
                v-else
                class="cover-glow"
              ></div>
              <div class="cover-caption">
                <span>{{ book.language }}</span>
                <strong>{{ book.title }}</strong>
              </div>
            </div>

            <div class="card-body">
              <h3>{{ book.title }}</h3>
              <p class="author-line">{{ getPresentation(book).author }}</p>

              <div class="book-tags">
                <span>{{ book.bookKind }}</span>
                <span>{{ book.language }}</span>
                <span v-if="book.translated">翻译中</span>
              </div>

              <p
                v-if="book.lastReadChapterIndex > 0"
                class="card-reading"
              >
                上次读到第 {{ book.lastReadChapterIndex }} 章
              </p>

              <div class="progress-meta">
                <span>{{ book.lastReadChapterIndex > 0 ? '阅读进度' : '章节数量' }}</span>
                <strong>
                  {{
                    book.lastReadChapterIndex > 0
                      ? `${book.lastReadChapterIndex} / ${book.chapterCount}`
                      : `${book.chapterCount} / ${book.chapterCount}`
                  }}
                </strong>
              </div>
              <div class="progress-track">
                <div
                  class="progress-bar"
                  :style="{ width: `${book.chapterCount ? ((book.lastReadChapterIndex || book.chapterCount) / book.chapterCount) * 100 : 0}%` }"
                ></div>
              </div>
            </div>
          </article>
        </section>

        <transition name="panel-fade">
          <section
            v-if="showImportPanel"
            class="drawer-mask"
            @click.self="showImportPanel = false"
          >
            <div class="import-drawer">
              <div class="drawer-head">
                <div>
                  <p class="page-kicker">添加书籍</p>
                  <h3>导入新内容</h3>
                </div>
                <button
                  class="icon-btn"
                  @click="showImportPanel = false"
                >
                  ×
                </button>
              </div>

              <label class="form-field">
                <span>内容链接</span>
                <input
                  v-model="addBookForm.sourceUrl"
                  placeholder="https://example.com/novel/123 或漫画详情页链接"
                  type="url"
                />
                <small class="field-hint">
                  已支持自动识别小说 / 漫画；漫画目前支持 18comic.vip 与 bikawebapp.com。
                </small>
              </label>

              <label class="form-field">
                <span>本地小说文件</span>
                <input
                  :key="localFilePickerKey"
                  accept=".txt,.text,.md"
                  type="file"
                  @change="handleLocalFileChange"
                />
                <small class="field-hint">
                  支持导入本地 TXT / TEXT / Markdown 文本，系统会自动尝试拆分章节。
                </small>
                <strong
                  v-if="localBookFile"
                  class="file-picked"
                >
                  已选择：{{ localBookFile.name }}
                </strong>
              </label>

              <div class="field-grid">
                <label class="form-field">
                  <span>内容类型</span>
                  <select v-model="addBookForm.bookKind">
                    <option value="长小说">长小说</option>
                    <option value="轻小说">轻小说</option>
                    <option value="漫画">漫画</option>
                  </select>
                  <small class="field-hint">远程链接会自动识别，手动选择主要用于本地导入。</small>
                </label>

                <label class="form-field">
                  <span>语言</span>
                  <select v-model="addBookForm.language">
                    <option value="中文">中文</option>
                    <option value="英文">英文</option>
                    <option value="日文">日文</option>
                  </select>
                </label>
              </div>

              <label class="form-field">
                <span>书名（可选）</span>
                <input
                  v-model="addBookForm.title"
                  placeholder="允许留空，抓取后自动识别"
                  type="text"
                />
              </label>

              <label class="check-line">
                <input
                  v-model="addBookForm.needTranslation"
                  type="checkbox"
                />
                <span>抓取完成后自动进入 AI 翻译流程</span>
              </label>

              <div class="drawer-actions">
                <button
                  class="ghost-btn"
                  :disabled="loadingPreview"
                  @click="handlePreview"
                >
                  {{ loadingPreview ? '解析中...' : '预览章节' }}
                </button>
                <button
                  class="primary-btn"
                  :disabled="importing"
                  @click="handleImport"
                >
                  {{ importing ? '导入中...' : '加入书架' }}
                </button>
              </div>

              <div class="drawer-actions drawer-actions--local">
                <button
                  class="secondary-btn"
                  :disabled="importing || !localBookFile"
                  @click="handleImportLocal"
                >
                  {{ importing ? '导入中...' : '导入本地文件' }}
                </button>
              </div>

              <div class="status-note">
                <strong>状态</strong>
                <p>{{ lastMessage }}</p>
              </div>

              <div
                v-if="preview"
                class="preview-panel"
              >
                <div class="preview-top">
                  <div>
                    <span class="page-kicker">抓取预览</span>
                    <h4>{{ preview.title }}</h4>
                  </div>
                  <strong>{{ preview.bookKind }} · {{ formatChapterCount(preview.chapterCount, preview.bookKind) }}</strong>
                </div>
                <p>{{ preview.synopsis }}</p>
                <ul>
                  <li
                    v-for="chapter in preview.chapters.slice(0, 6)"
                    :key="chapter.url"
                  >
                    {{ chapter.title }}
                    <small v-if="preview.bookKind === '漫画' && chapter.pageCount > 0">（{{ formatPageCount(chapter.pageCount) }}）</small>
                  </li>
                </ul>
              </div>
            </div>
          </section>
        </transition>
      </template>

      <template v-else-if="currentView === 'logs'">
        <header class="page-head">
          <div>
            <p class="page-kicker">运行面板</p>
            <h2>运行日志</h2>
            <p class="page-subtitle">查看导入、下载、翻译和系统状态的完整记录</p>
          </div>
          <button
            class="ghost-btn"
            type="button"
            @click="clearActivityLogs"
          >
            清空日志
          </button>
        </header>

        <section class="summary-row">
          <article class="summary-card">
            <span>全部日志</span>
            <strong>{{ logSummary.total }}</strong>
            <small>{{ logCardDescription('total') }}</small>
          </article>
          <article class="summary-card">
            <span>系统状态</span>
            <strong>{{ logSummary.system }}</strong>
            <small>{{ logCardDescription('system') }}</small>
          </article>
          <article class="summary-card">
            <span>操作记录</span>
            <strong>{{ logSummary.action }}</strong>
            <small>{{ logCardDescription('action') }}</small>
          </article>
          <article class="summary-card">
            <span>任务 / 异常</span>
            <strong>{{ logSummary.task + logSummary.error }}</strong>
            <small>下载、翻译进度与失败回报</small>
          </article>
        </section>

        <section class="logs-page-panel">
          <div class="chapter-head logs-page-head">
            <div>
              <h3>日志流</h3>
              <p>当前记录 {{ logSummary.total }} 条，下载与翻译任务执行时会自动追加。</p>
            </div>
          </div>

          <div
            v-if="!activityLogs.length"
            class="status-note flush"
          >
            <strong>暂无日志</strong>
            <p>导入小说、下载章节、翻译任务或系统状态变化后，这里会显示完整记录。</p>
          </div>

          <div
            v-else
            class="logs-page-list"
          >
            <article
              v-for="entry in activityLogs"
              :key="entry.id"
              class="logs-page-item"
              :data-log-category="entry.category"
            >
              <div class="logs-page-meta">
                <span>{{ logCategoryLabel(entry.category) }}</span>
                <time>{{ entry.at }}</time>
              </div>
              <strong>{{ entry.title }}</strong>
              <p>{{ entry.detail }}</p>
            </article>
          </div>
        </section>
      </template>

      <template v-else-if="currentView === 'settings'">
        <header class="page-head narrow">
          <div>
            <p class="page-kicker">配置中心</p>
            <h2>设置</h2>
            <p class="page-subtitle">配置 AI 翻译服务、漫画站点凭证和应用偏好</p>
          </div>
        </header>

        <section class="settings-layout">
          <article class="settings-card large">
            <div class="settings-card-head">
              <div class="settings-badge">⚡</div>
              <div>
                <h3>AI 翻译配置</h3>
                <p>设置用于章节翻译的 AI 服务</p>
              </div>
            </div>

            <div class="provider-grid">
              <button
                v-for="provider in providerOptions"
                :key="provider.key"
                :class="providerCardClass(provider.key)"
                @click="setDefaultProvider(provider.key)"
              >
                <strong>{{ provider.label }}</strong>
                <span>{{ provider.description }}</span>
              </button>
            </div>

            <label class="form-field">
              <span>API 密钥</span>
              <input
                v-model="settings.providers[activeProvider].apiKey"
                placeholder="sk-..."
                type="password"
              />
              <small>您的 API 密钥将加密保存在本地，不会上传到服务器</small>
            </label>

            <label class="form-field">
              <span>API 地址</span>
              <input
                v-model="settings.providers[activeProvider].baseUrl"
                placeholder="https://api.openai.com/v1"
                type="text"
              />
            </label>

            <label class="form-field">
              <span>翻译模型</span>
              <input
                v-model="settings.providers[activeProvider].model"
                :list="`${activeProvider}-model-options`"
                placeholder="输入模型名，例如 gpt-5.4"
                type="text"
              />
              <datalist :id="`${activeProvider}-model-options`">
                <option
                  v-for="option in providerModelOptions"
                  :key="option"
                  :value="option"
                />
              </datalist>
              <small>可直接输入任意模型名，下面的建议项仅用于快速填写。</small>
            </label>

            <label class="check-line">
              <input
                v-model="settings.providers[activeProvider].enabled"
                type="checkbox"
              />
              <span>启用当前提供商</span>
            </label>
          </article>

          <article class="settings-card">
            <h3>应用设置</h3>
            <label class="form-field">
              <span>默认翻译服务</span>
              <select v-model="settings.defaultProvider">
                <option
                  v-for="provider in providerOptions"
                  :key="provider.key"
                  :value="provider.key"
                >
                  {{ provider.label }}
                </option>
              </select>
            </label>

            <label class="form-field">
              <span>阅读时预翻译后续章节</span>
              <select v-model.number="settings.autoTranslateNextChapters">
                <option
                  v-for="option in autoTranslateOptions"
                  :key="option.value"
                  :value="option.value"
                >
                  {{ option.label }}
                </option>
              </select>
              <small>打开章节阅读时，会自动把当前章和后续设定章数加入翻译队列；选择“全部剩余章节”会翻译从当前章开始的全部未翻译章节。</small>
            </label>

            <label class="form-field">
              <span>下载线程数</span>
              <input
                v-model.number="settings.downloadConcurrency"
                min="1"
                max="8"
                step="1"
                type="number"
              />
              <small>用于控制章节与漫画图片下载并发数。建议设置 2-5；18comic / Bika 会自动放大图片并发，过高可能触发目标站点限流。</small>
            </label>

            <div class="status-note flush">
              <strong>Bika 漫画凭证</strong>
              <p>用于抓取 bikawebapp.com 对应的漫画目录和章节图片；留空时会在首次抓取时自动创建并登录本地账户，也支持手动填写已有账户。</p>
            </div>

            <label class="form-field">
              <span>Bika 账号</span>
              <input
                v-model="settings.bika.email"
                placeholder="留空则自动创建，或输入已有邮箱/用户名"
                type="text"
              />
            </label>

            <label class="form-field">
              <span>Bika 密码</span>
              <input
                v-model="settings.bika.password"
                placeholder="留空则自动创建，或输入已有账户密码"
                type="password"
              />
            </label>

            <label class="form-field">
              <span>系统提示词</span>
              <textarea
                v-model="settings.systemPrompt"
                rows="6"
              ></textarea>
            </label>

            <div class="status-note flush">
              <strong>桌面状态</strong>
              <p>{{ desktopState }}</p>
            </div>

            <button
              class="primary-btn full"
              :disabled="savingSettings"
              @click="handleSaveSettings"
            >
              {{ savingSettings ? '保存中...' : '保存设置' }}
            </button>
          </article>
        </section>
      </template>

      <template v-else-if="currentView === 'detail' && selectedBook && selectedPresentation">
        <header class="detail-back">
          <button
            class="text-btn"
            @click="backToLibrary"
          >
            ‹ 返回书架
          </button>
        </header>

        <section class="detail-hero">
          <div
            class="detail-cover"
            :class="getCoverClass(selectedBook)"
          >
            <img
              v-if="selectedBook.cover"
              :src="selectedBook.cover"
              :alt="`${selectedBook.title} 封面`"
              class="cover-image"
            />
            <div
              v-if="selectedBook.cover"
              class="cover-filter"
            ></div>
            <div
              v-else
              class="cover-glow"
            ></div>
            <div class="cover-caption">
              <span>{{ selectedBook.language }}</span>
              <strong>{{ selectedBook.title }}</strong>
            </div>
            <input
              :key="coverUploadPickerKey"
              ref="coverFileInput"
              class="cover-upload-input"
              accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"
              type="file"
              @change="handleCoverFileChange"
            />
            <button
              class="cover-upload-trigger"
              type="button"
              :disabled="coverUploading"
              @click="triggerCoverUpload"
            >
              {{ coverUploading ? '上传中...' : '更换封面' }}
            </button>
          </div>

          <div class="detail-copy">
            <h2>{{ selectedBook.title }}</h2>
            <p class="detail-author">作者：{{ selectedPresentation.author }}</p>

            <div class="book-tags">
              <span>{{ selectedBook.bookKind }}</span>
              <span>{{ selectedBook.language }}</span>
              <span :class="selectedPresentation.accentClass">{{ selectedPresentation.serialState }}</span>
            </div>

            <div class="detail-stats">
              <article>
                <span>{{ selectedBook.bookKind === '漫画' ? '总话数' : '总章节' }}</span>
                <strong>{{ selectedPresentation.progressTotal }}</strong>
              </article>
              <article>
                <span>阅读进度</span>
                <strong>
                  {{
                    persistedReadingProgress.hasProgress
                      ? `${persistedReadingProgress.currentIndex} / ${selectedPresentation.progressTotal}`
                      : '未开始'
                  }}
                </strong>
                <small v-if="persistedReadingProgress.lastReadAt">{{ formatReadingTimestamp(persistedReadingProgress.lastReadAt) }}</small>
              </article>
              <article>
                <span>{{ selectedBook.bookKind === '漫画' ? '总页数' : '总字数' }}</span>
                <strong>{{ formatContentCount(Number(selectedPresentation.words), selectedBook.bookKind) }}</strong>
              </article>
              <article>
                <span>添加日期</span>
                <strong>{{ selectedPresentation.addedAt }}</strong>
              </article>
            </div>

            <p class="detail-summary">
              {{ detailSynopsis }}
            </p>

            <div class="detail-actions">
              <div class="detail-continue">
                <button
                  class="primary-btn"
                  :disabled="!chapters.length"
                  @click="handleContinueReading"
                >
                  ▶ {{ continueReadingLabel }}
                </button>
                <small>{{ continueReadingDescription }}</small>
              </div>
              <button
                class="ghost-btn anchor-btn"
                :disabled="!selectedBook.sourceUrl"
                @click="handleOpenExternal(selectedBook.sourceUrl, '原帖')"
              >
                ↗ 访问原帖
              </button>
              <div class="export-menu">
                <button
                  class="ghost-btn"
                  :disabled="!chapters.length || exportingFormat !== null"
                  @click="toggleExportMenu"
                >
                  {{ exportingFormat ? `${exportingFormat.toUpperCase()} 导出中...` : exportMenuOpen ? '收起导出' : '导出' }}
                </button>
                <div
                  v-if="exportMenuOpen"
                  class="export-submenu"
                >
                  <button
                    class="ghost-btn compact"
                    :disabled="exportingFormat !== null"
                    @click="handleExportBook('txt')"
                  >
                    TXT 文本
                  </button>
                  <button
                    class="ghost-btn compact"
                    :disabled="exportingFormat !== null"
                    @click="handleExportBook('epub')"
                  >
                    EPUB 电子书
                  </button>
                  <span class="export-hint">导出时可自由选择保存位置</span>
                </div>
              </div>
              <button
                class="ghost-btn"
                :disabled="coverUploading || exportingFormat !== null"
                @click="triggerCoverUpload"
              >
                {{ coverUploading ? '封面上传中...' : '自定义封面' }}
              </button>
              <button
                class="danger-btn"
                :disabled="deletingBook || exportingFormat !== null"
                @click="handleDeleteSelectedBook"
              >
                {{ deletingBook ? '删除中...' : '删除书籍' }}
              </button>
            </div>
          </div>
        </section>

        <section class="chapter-card">
          <div class="chapter-head">
            <div>
              <h3>章节列表</h3>
              <p v-if="detailLoading">正在读取本地章节...</p>
              <p v-else>
                已选择 {{ selectedChapterCount }} {{ selectedBook.bookKind === '漫画' ? '话' : '章' }}，共
                {{ chapters.length }} {{ selectedBook.bookKind === '漫画' ? '话' : '章' }}
              </p>
            </div>
            <div
              v-if="chapters.length"
              class="chapter-tools"
            >
              <button
                class="text-btn"
                @click="toggleAllChapters"
              >
                {{ allChaptersSelected ? '取消全选' : '全选' }}
              </button>
              <button
                class="primary-btn soft"
                :disabled="!chapters.length"
                @click="handleReadSelectedChapter"
              >
                阅读当前章
              </button>
              <button
                class="ghost-btn compact"
                :disabled="chapterActionLoading === 'translate' || selectedChapterCount === 0"
                @click="handleDownloadSelected"
              >
                {{ chapterActionLoading === 'download' ? '下载中...' : `下载选中 (${selectedChapterCount})` }}
              </button>
              <button
                class="ghost-btn compact"
                :disabled="chapterActionLoading === 'download' || selectedChapterCount === 0"
                @click="handleTranslateSelected"
              >
                {{ chapterActionLoading === 'translate' ? '翻译中...' : `翻译选中 (${selectedChapterCount})` }}
              </button>
              <span class="chapter-inline-note">当前下载线程：{{ settings.downloadConcurrency }}</span>
            </div>
          </div>

          <div
            v-if="detailLoading"
            class="status-note flush"
          >
            <strong>同步中</strong>
            <p>正在读取本地章节文件和书籍目录清单...</p>
          </div>

          <div
            v-else-if="detailError"
            class="status-note flush"
          >
            <strong>加载失败</strong>
            <p>{{ detailError }}</p>
            <button
              class="ghost-btn"
              @click="selectedBookId && openBook(selectedBookId)"
            >
              重新读取
            </button>
          </div>

          <div
            v-else-if="!chapters.length"
            class="status-note flush"
          >
            <strong>暂无章节</strong>
            <p>当前书籍目录里还没有可读取的章节文件。</p>
          </div>

          <div
            v-else
            class="chapter-list"
          >
            <label
              v-for="chapter in chapters"
              :key="chapter.id"
              class="chapter-row"
              :class="{ active: chapter.index === activeChapterIndex }"
              @click="setActiveChapter(chapter.index)"
            >
              <input
                v-model="selectedChapterIndexes"
                :value="chapter.index"
                type="checkbox"
                @click.stop
              />
              <div class="chapter-copy">
                <strong>{{ chapter.title }}</strong>
                <span>{{ formatChapterMeta(chapter, selectedBook.bookKind) }}</span>
              </div>
              <div class="chapter-flags">
                <em v-if="selectedBook.bookKind === '漫画' && chapter.pageCount > 0">{{ formatPageCount(chapter.pageCount) }}</em>
                <em v-if="chapter.illustration">插图</em>
                <em v-if="chapter.downloaded">已下载</em>
                <em v-if="chapter.translated">已翻译</em>
              </div>
            </label>
          </div>
        </section>

        <section class="chapter-card task-card">
          <div class="chapter-head">
            <div>
              <h3>任务队列</h3>
              <p v-if="tasksLoading">正在同步任务状态...</p>
              <p v-else>运行中 {{ activeTasks.length }} 个，失败 {{ failedTasks.length }} 个</p>
            </div>
          </div>

          <div
            v-if="!bookTasks.length"
            class="status-note flush"
          >
            <strong>暂无任务</strong>
            <p>下载和翻译任务会显示在这里，并持续更新进度。</p>
          </div>

          <div
            v-else
            class="task-list"
          >
            <article
              v-for="task in bookTasks"
              :key="task.id"
              class="task-row"
            >
              <div class="task-copy">
                <div class="task-meta">
                  <strong>{{ taskTypeLabel(task) }}</strong>
                  <span :data-task-status="task.status">{{ taskStatusLabel(task.status) }}</span>
                </div>
                <p>{{ task.message || '等待任务状态更新' }}</p>
                <small>章节 {{ task.completedCount }} / {{ task.totalCount }}</small>
                <small v-if="task.error">{{ task.error }}</small>
              </div>

              <div class="task-side">
                <div class="task-progress">
                  <div
                    class="task-progress-fill"
                    :style="{ width: `${task.progress}%` }"
                  ></div>
                </div>
                <button
                  v-if="task.status === 'failed'"
                  class="ghost-btn compact"
                  :disabled="taskRetryingId === task.id"
                  @click="handleRetryTask(task.id)"
                >
                  {{ taskRetryingId === task.id ? '重试中...' : '失败重试' }}
                </button>
              </div>
            </article>
          </div>
        </section>
      </template>

      <template v-else-if="currentView === 'reader' && selectedBook && selectedPresentation">
        <header class="reader-topbar">
          <button
            class="text-btn"
            @click="backToDetail"
          >
            ‹ 返回
          </button>

          <div class="reader-title">
            <strong>{{ selectedBook.title }}</strong>
            <span>{{ readerChapter?.title || '未选择章节' }}</span>
          </div>

          <div class="reader-tools">
            <button
              class="ghost-btn compact"
              :disabled="!readerSourceUrl"
              @click="handleOpenExternal(readerSourceUrl, '章节原帖')"
            >
              原帖
            </button>
            <button
              class="ghost-btn compact"
              :disabled="!chapters.length"
              @click="readerChapterPickerOpen = !readerChapterPickerOpen"
            >
              {{ readerChapterPickerOpen ? '收起章节' : '章节选择' }}
            </button>
            <button
              class="ghost-btn compact"
              :disabled="!translatedReadable"
              @click="toggleReaderMode"
            >
              {{ readerMode === 'translated' ? (isComicBook ? '原图' : '原文') : '译文' }}
            </button>
            <button
              class="ghost-btn compact"
              :disabled="!hasPreviousChapter"
              @click="goToAdjacentChapter(-1)"
            >
              {{ isComicBook ? '上一话' : '上一章' }}
            </button>
            <button
              class="ghost-btn compact"
              :disabled="!hasNextChapter"
              @click="goToAdjacentChapter(1)"
            >
              {{ isComicBook ? '下一话' : '下一章' }}
            </button>
            <button
              class="icon-btn"
              @click="showReaderPanel = !showReaderPanel"
            >
              ⚙
            </button>
          </div>
        </header>

        <div class="reader-progress">
          <span>{{ isComicBook ? '话数' : '章节' }} {{ readerProgressIndex }} / {{ readerProgressTotal }}</span>
          <span>{{ formatContentCount(readerWordCount, selectedBook.bookKind) }}</span>
          <div class="reader-line">
            <div
              class="reader-line-fill"
              :style="{ width: `${readerProgressTotal ? (readerProgressIndex / readerProgressTotal) * 100 : 0}%` }"
            ></div>
          </div>
        </div>

        <transition name="panel-fade">
          <section
            v-if="readerChapterPickerOpen"
            class="reader-chapter-picker"
          >
            <div class="reader-chapter-picker-head">
              <div>
                <strong>章节选择</strong>
                <p>{{ readerChapterPickerSummary }}</p>
              </div>
              <button
                class="ghost-btn compact"
                @click="readerChapterPickerOpen = false"
              >
                收起
              </button>
            </div>
            <div class="reader-chapter-picker-list">
              <button
                v-for="chapter in chapters"
                :key="chapter.id"
                class="reader-chapter-chip"
                :class="{
                  active: chapter.index === activeChapterIndex,
                  progress: persistedReadingProgress.currentIndex > 0 && chapter.index === persistedReadingProgress.currentIndex,
                }"
                @click="selectReaderChapter(chapter.index)"
              >
                <span>{{ chapter.title || formatChapterOrder(chapter.index, selectedBook.bookKind) }}</span>
                <small>{{ formatChapterMeta(chapter, selectedBook.bookKind) }}</small>
              </button>
            </div>
          </section>
        </transition>

        <section
          class="reader-layout"
          :class="{ 'reader-layout--focus': !showReaderPanel }"
        >
          <article
            ref="readerPaperRef"
            class="reader-paper"
          >
            <template v-if="readerLoading">
              <h2>{{ readerChapter?.title || '正在加载章节' }}</h2>
              <p>正在从本地章节文件读取正文...</p>
            </template>

            <template v-else-if="readerError">
              <h2>{{ readerChapter?.title || '章节加载失败' }}</h2>
              <p>{{ readerError }}</p>
            </template>

            <template v-else-if="readerContent">
              <h2>{{ readerContent.chapter.title }}</h2>
              <div
                v-if="readerImages.length"
                class="reader-illustrations"
              >
                <figure
                  v-for="(imageSource, index) in readerImages"
                  :key="`${readerContent.chapter.id}-image-${index}`"
                  class="reader-figure"
                  data-reader-anchor-type="image"
                  :data-reader-anchor-index="index"
                >
                  <img
                    :src="imageSource"
                    :alt="`${readerContent.chapter.title} 插图 ${index + 1}`"
                    @load="handleReaderAssetLoad"
                    @error="handleReaderAssetLoad"
                  />
                  <figcaption>{{ isComicBook ? `第 ${index + 1} 页` : `插图 ${index + 1}` }}</figcaption>
                  <div
                    v-if="isComicBook && readerMode === 'translated' && !readerUsesTranslatedImages && readerPageTranslations[index]"
                    class="reader-page-translation"
                  >
                    <strong>本页译文</strong>
                    <p class="reader-page-translation-text">{{ readerPageTranslations[index] }}</p>
                  </div>
                </figure>
              </div>
              <template v-if="!isComicBook">
                <p
                  v-for="(paragraph, index) in visibleReaderParagraphs"
                  :key="`${readerContent.chapter.id}-${index}`"
                  data-reader-anchor-type="paragraph"
                  :data-reader-anchor-index="index"
                >
                  {{ paragraph }}
                </p>
              </template>
              <div
                v-else-if="readerMode === 'translated' && !readerUsesTranslatedImages && !readerPageTranslations.length && visibleReaderParagraphs.length"
                class="reader-comic-fallback"
              >
                <strong>整话译文</strong>
                <p
                  v-for="(paragraph, index) in visibleReaderParagraphs"
                  :key="`${readerContent.chapter.id}-fallback-${index}`"
                  data-reader-anchor-type="paragraph"
                  :data-reader-anchor-index="index"
                >
                  {{ paragraph }}
                </p>
              </div>
            </template>

            <template v-else>
              <h2>{{ readerChapter?.title || '暂无章节' }}</h2>
              <p>当前没有可读取的章节内容。</p>
            </template>
          </article>

          <aside
            v-if="showReaderPanel"
            class="reader-panel"
          >
            <div class="reader-panel-head">
              <h3>阅读设置</h3>
              <button
                class="icon-btn"
                @click="showReaderPanel = false"
              >
                ×
              </button>
            </div>

            <div class="reader-block">
              <span>字体大小</span>
              <div class="segmented">
                <button
                  v-for="size in ['小', '中', '大', '特大']"
                  :key="size"
                  :class="{ active: readerFontSize === size }"
                  @click="applyReaderFontSize(size as ReaderFontSize)"
                >
                  {{ size }}
                </button>
              </div>
            </div>

            <div class="reader-block">
              <span>应用主题</span>
              <div class="theme-stack">
                <button
                  v-for="theme in themeOptions"
                  :key="theme.key"
                  :class="{ active: readerTheme === theme.key }"
                  @click="applyReaderTheme(theme.key)"
                >
                  {{ theme.label }}
                  <small v-if="readerTheme === theme.key">当前</small>
                </button>
              </div>
            </div>

            <div class="reader-block">
              <div class="reader-color-head">
                <span>自定义颜色</span>
                <button
                  class="text-btn"
                  type="button"
                  @click="resetReaderColors"
                >
                  恢复主题
                </button>
              </div>
              <div class="reader-color-grid">
                <label class="reader-color-field">
                  <small>字体颜色</small>
                  <div class="reader-color-input">
                    <input
                      :value="readerTextColor || '#111827'"
                      type="color"
                      @input="applyReaderTextColor(($event.target as HTMLInputElement).value)"
                    />
                    <input
                      :value="readerTextColor"
                      placeholder="跟随主题"
                      type="text"
                      @input="applyReaderTextColor(($event.target as HTMLInputElement).value)"
                    />
                  </div>
                </label>
                <label class="reader-color-field">
                  <small>背景颜色</small>
                  <div class="reader-color-input">
                    <input
                      :value="readerBackgroundColor || '#ffffff'"
                      type="color"
                      @input="applyReaderBackgroundColor(($event.target as HTMLInputElement).value)"
                    />
                    <input
                      :value="readerBackgroundColor"
                      placeholder="跟随主题"
                      type="text"
                      @input="applyReaderBackgroundColor(($event.target as HTMLInputElement).value)"
                    />
                  </div>
                </label>
              </div>
            </div>

            <div class="preview-sample">
              <strong>示例文本</strong>
              <p>这是当前字体大小和主题的预览效果，适合长时间沉浸阅读。</p>
              <span>{{ readerThemeLabel }} · {{ readerFontSize }}</span>
              <span>{{ readerColorSummary }}</span>
            </div>
          </aside>
        </section>
      </template>
    </section>

    <button
      v-if="showBackToTopButton"
      class="scroll-top-btn"
      type="button"
      title="返回顶部"
      @click="scrollPageToTop"
    >
      ↑ 返回顶部
    </button>
  </div>
</template>
