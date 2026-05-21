<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import bookGlobeIcon from '@fluentui/svg-icons/icons/book_globe_20_regular.svg?raw';
import bookAddIcon from '@fluentui/svg-icons/icons/book_add_20_regular.svg?raw';
import bookOpenIcon from '@fluentui/svg-icons/icons/book_open_20_regular.svg?raw';
import clipboardClockIcon from '@fluentui/svg-icons/icons/clipboard_clock_20_regular.svg?raw';
import arrowUpIcon from '@fluentui/svg-icons/icons/arrow_up_20_regular.svg?raw';
import searchIcon from '@fluentui/svg-icons/icons/search_20_regular.svg?raw';
import settingsIcon from '@fluentui/svg-icons/icons/settings_20_regular.svg?raw';
// QingJuan
// Author: Tavre
// License: GPL-3.0-only
import { defaultSettings } from '../lib/mock';
import {
  fetchBookSources,
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
  importBookSourcesFromText,
  importBookSourcesFromUrl,
  importLocalBook,
  previewBook,
  retryTask,
  saveReadingProgress,
  saveSettings,
  searchBookSources,
  translateChapters,
  uploadBookCover,
} from '../services/api';
import { openExternalLink, startDesktopBackend } from '../services/desktop';
import brandIcon from '../../qj_icon2.png';
import type {
  AddBookPayload,
  BookDetailResponse,
  BookExportFormat,
  BookSourceImportResult,
  BookSourceRecord,
  BookSourceSearchResult,
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

type ViewMode = 'library' | 'search' | 'sources' | 'logs' | 'settings' | 'detail' | 'reader';
type ReaderTheme = 'default' | 'care' | 'night';
type ReaderFontSize = '小' | '中' | '大' | '特大';
type LibraryDisplayMode = 'grid' | 'list';

interface NavItem {
  key: 'library' | 'search' | 'sources' | 'logs' | 'settings';
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
  contentCountText: string;
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
  { key: 'library', label: '我的书架', icon: bookOpenIcon },
  { key: 'search', label: '搜索', icon: searchIcon },
  { key: 'sources', label: '书源管理', icon: bookGlobeIcon },
  { key: 'logs', label: '运行日志', icon: clipboardClockIcon },
  { key: 'settings', label: '设置', icon: settingsIcon },
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
const bookSources = ref<BookSourceRecord[]>([]);
const preview = ref<PreviewResponse | null>(null);
const sourceImportForm = reactive({
  url: '',
  content: '',
});
const sourceImportSummary = ref<BookSourceImportResult | null>(null);
const sourceImporting = ref(false);
const sourceSearchKeyword = ref('');
const sourceSearchResults = ref<BookSourceSearchResult[]>([]);
const sourceSearchLoading = ref(false);
const sourceSearchError = ref('');
const sourceSearchTouched = ref(false);
const sourceSearchImporting = ref<string | null>(null);
const settings = ref<TranslationSettings>(defaultSettings);
const activeProvider = ref<TranslationProvider>('openai');
const currentView = ref<ViewMode>('library');
const selectedBookId = ref<string | null>(null);
const searchQuery = ref('');
const sourceSearchQuery = ref('');
const showImportPanel = ref(false);
const desktopState = ref('正在连接后端服务...');
const lastMessage = ref('等待输入小说链接');
const loadingPreview = ref(false);
const importing = ref(false);
const sourceLoading = ref(false);
const localBookFiles = ref<File[]>([]);
const localFilePickerKey = ref(0);
const localFileInput = ref<HTMLInputElement | null>(null);
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
type GlobalTheme = 'system' | 'light' | 'care' | 'dark';

const globalTheme = ref<GlobalTheme>(readStoredGlobalTheme());
const accentBaseColor = computed(() => {
  const resolvedTheme = globalTheme.value === 'system' ? resolveSystemGlobalTheme() : globalTheme.value;
  if (resolvedTheme === 'dark') {
    return '#9fb8d8';
  }
  if (resolvedTheme === 'care') {
    return '#dccdb1';
  }
  return '#c4d8ef';
});

function resolveSystemGlobalTheme(): Exclude<GlobalTheme, 'system'> {
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }

  return 'light';
}

function mapReaderThemeToGlobalTheme(theme: ReaderTheme): Exclude<GlobalTheme, 'system'> {
  if (theme === 'care') {
    return 'care';
  }

  if (theme === 'night') {
    return 'dark';
  }

  return 'light';
}

function mapGlobalThemeToReaderTheme(theme: GlobalTheme): ReaderTheme {
  const resolvedTheme = theme === 'system' ? resolveSystemGlobalTheme() : theme;

  if (resolvedTheme === 'care') {
    return 'care';
  }

  if (resolvedTheme === 'dark') {
    return 'night';
  }

  return 'default';
}

function syncGlobalTheme() {
  if (typeof window === 'undefined') return;
  const val = globalTheme.value;
  window.localStorage.setItem('qingjuan.globalTheme', val);

  if (val === 'care') {
    document.documentElement.dataset.theme = 'care';
    return;
  }

  if (val === 'dark' || (val === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.dataset.theme = 'dark';
  } else {
    delete document.documentElement.dataset.theme;
  }
}
watch(globalTheme, syncGlobalTheme, { immediate: true });

let dragScrollCleanup: (() => void) | null = null;
function setupDragScroll() {
  if (typeof window === 'undefined') return;
  let isDragging = false;
  let startY = 0;
  let scrollTop = 0;

  const handleMouseDown = (e: MouseEvent) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('button, input, select, textarea, a, fluent-button, fluent-search, fluent-select, fluent-text-field, fluent-text-area, .no-drag')) return;
    
    isDragging = true;
    startY = e.pageY - document.documentElement.offsetTop;
    scrollTop = window.scrollY;
    document.body.style.cursor = 'grab';
    document.body.style.userSelect = 'none';
  };

  const handleMouseLeaveOrUp = () => {
    if (!isDragging) return;
    isDragging = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging) return;
    e.preventDefault();
    const y = e.pageY - document.documentElement.offsetTop;
    const walk = y - startY;
    window.scrollTo(0, scrollTop - walk);
  };

  window.addEventListener('mousedown', handleMouseDown);
  window.addEventListener('mouseleave', handleMouseLeaveOrUp);
  window.addEventListener('mouseup', handleMouseLeaveOrUp);
  window.addEventListener('mousemove', handleMouseMove);

  dragScrollCleanup = () => {
    window.removeEventListener('mousedown', handleMouseDown);
    window.removeEventListener('mouseleave', handleMouseLeaveOrUp);
    window.removeEventListener('mouseup', handleMouseLeaveOrUp);
    window.removeEventListener('mousemove', handleMouseMove);
  };
}
const readerFontSize = ref<ReaderFontSize>(readStoredReaderFontSize());
const readerTextColor = ref(readStoredReaderColor(READER_TEXT_COLOR_STORAGE_KEY));
const readerBackgroundColor = ref(readStoredReaderColor(READER_BACKGROUND_COLOR_STORAGE_KEY));
const readerTextColorInput = ref<HTMLInputElement | null>(null);
const readerBackgroundColorInput = ref<HTMLInputElement | null>(null);
const showReaderPanel = ref(true);
const readerChapterPickerOpen = ref(false);
const libraryDisplayMode = ref<LibraryDisplayMode>(
  typeof window !== 'undefined'
    ? (window.localStorage.getItem('qingjuan.libraryDisplayMode') as LibraryDisplayMode) || 'grid'
    : 'grid',
);
watch(libraryDisplayMode, (val) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('qingjuan.libraryDisplayMode', val);
  }
});
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

function normalizeFuzzyText(value: string): string {
  return value
    .toLowerCase()
    .normalize('NFKC')
    .replace(/[\s\p{P}\p{S}_]+/gu, '');
}

function fuzzyMatchText(haystack: string, keyword: string): boolean {
  const normalizedHaystack = normalizeFuzzyText(haystack);
  const normalizedKeyword = normalizeFuzzyText(keyword);
  if (!normalizedKeyword) {
    return true;
  }
  if (normalizedHaystack.includes(normalizedKeyword)) {
    return true;
  }

  let cursor = 0;
  for (const char of normalizedKeyword) {
    cursor = normalizedHaystack.indexOf(char, cursor);
    if (cursor < 0) {
      return false;
    }
    cursor += char.length;
  }
  return true;
}

const filteredBooks = computed(() => {
  const keyword = searchQuery.value.trim();
  if (!keyword) {
    return books.value;
  }

  return books.value.filter((book) => {
    const haystack = `${book.title} ${book.synopsis} ${getPresentation(book).author}`;
    return fuzzyMatchText(haystack, keyword);
  });
});

const filteredSources = computed(() => {
  const keyword = sourceSearchQuery.value.trim();
  if (!keyword) {
    return bookSources.value;
  }

  return bookSources.value.filter((source) => {
    const haystack = [
      source.name,
      source.baseUrl,
      source.description,
      source.bookKind ?? '',
      source.language ?? '',
      source.tags.join(' '),
      source.statusMessage,
    ]
      .join(' ');
    return fuzzyMatchText(haystack, keyword);
  });
});

const searchableImportedSources = computed(() =>
  bookSources.value.filter(
    (source) =>
      source.origin !== 'builtin' &&
      source.enabled &&
      source.tags.includes('可搜索'),
  ),
);

const librarySourceUrlSet = computed(() => new Set(books.value.map((book) => book.sourceUrl.trim())));

const sourceStats = computed(() => {
  const total = bookSources.value.length;
  const enabled = bookSources.value.filter((source) => source.enabled).length;
  const searchable = searchableImportedSources.value.length;
  return { total, enabled, searchable };
});

const searchResultsEmptyState = computed(() => {
  if (!sourceSearchTouched.value) {
    return '输入关键词后，直接搜索全部已启用的可搜索书源。';
  }
  if (!sourceSearchLoading.value && !sourceSearchResults.value.length && !sourceSearchError.value) {
    return searchableImportedSources.value.length
      ? '暂时没有搜索结果。'
      : '还没有可搜索的导入书源，请先到书源管理导入并启用 Legado 书源。';
  }
  return sourceSearchError.value;
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
    contentCountText: formatBookContentCount(detail, book.bookKind),
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
  style['--shell-accent'] = accentBaseColor.value;
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
const activeProviderOption = computed(
  () => providerOptions.find((item) => item.key === activeProvider.value) ?? providerOptions[0],
);
const appHeaderMeta = computed(() => {
  if (currentView.value === 'library') {
    return {
      kicker: '藏书陈列',
      title: '青卷',
      subtitle: `已收藏 ${books.value.length} 本作品，当前展示 ${filteredBooks.value.length} 本。`,
    };
  }

  if (currentView.value === 'sources') {
    return {
      kicker: 'Legado 书源',
      title: '书源管理',
      subtitle: `已导入 ${sourceStats.value.total} 个 Legado/阅读书源规则，启用 ${sourceStats.value.enabled} 个。`,
    };
  }

  if (currentView.value === 'search') {
    return {
      kicker: '书源搜索',
      title: '搜索',
      subtitle: sourceStats.value.searchable
        ? `默认搜索已导入的 ${sourceStats.value.searchable} 个可搜索书源。`
        : '请先在书源管理导入并启用 Legado 书源，然后再搜索作品。',
    };
  }

  if (currentView.value === 'logs') {
    return {
      kicker: '运行台账',
      title: '运行日志',
      subtitle: `集中查看导入、下载、翻译与系统状态的完整轨迹，共 ${logSummary.value.total} 条记录。`,
    };
  }

  if (currentView.value === 'settings') {
    return {
      kicker: '配置工作台',
      title: '设置',
      subtitle: `当前正在编辑 ${activeProviderOption.value.label}，用于管理翻译服务与应用偏好。`,
    };
  }

  if (currentView.value === 'detail') {
    const author = selectedPresentation.value?.author ? `${selectedPresentation.value.author} · ` : '';
    return {
      kicker: '作品详情',
      title: selectedBook.value?.title ?? '书籍详情',
      subtitle: `${author}${continueReadingDescription.value}`,
    };
  }

  return {
    kicker: '沉浸阅读',
    title: selectedBook.value?.title ?? '阅读器',
    subtitle: readerChapter.value?.title ?? '准备进入阅读',
  };
});
const windowTitle = computed(() => {
  if (currentView.value === 'library') {
    return '青卷';
  }

  if (currentView.value === 'reader') {
    const bookTitle = selectedBook.value?.title ?? '阅读器';
    const chapterTitle = readerChapter.value?.title;
    return chapterTitle ? `${bookTitle} · ${chapterTitle} · 青卷` : `${bookTitle} · 青卷`;
  }

  return `${appHeaderMeta.value.title} · 青卷`;
});

function readStoredReaderTheme(): ReaderTheme {
  if (typeof window === 'undefined') {
    return 'default';
  }
  const stored = window.localStorage.getItem(READER_THEME_STORAGE_KEY);
  return stored === 'default' || stored === 'care' || stored === 'night' ? stored : 'default';
}

function readStoredGlobalTheme(): GlobalTheme {
  if (typeof window === 'undefined') {
    return mapReaderThemeToGlobalTheme(readStoredReaderTheme());
  }

  const stored = window.localStorage.getItem('qingjuan.globalTheme');
  if (stored === 'system' || stored === 'light' || stored === 'care' || stored === 'dark') {
    return stored;
  }

  return mapReaderThemeToGlobalTheme(readStoredReaderTheme());
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
    system: '后端服务与运行状态',
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
      ? `后端服务已连接 ${backend.host}:${backend.port}`
      : '后端服务未返回连接信息';
    backendReady = true;
  } catch (error) {
    desktopState.value = `后端服务连接失败：${toErrorMessage(error)}`;
  }

  if (!backendReady) {
    lastMessage.value = '后端服务未就绪，已跳过书架初始化';
    return;
  }

  try {
    await refreshBooks();
  } catch (error) {
    books.value = [];
    lastMessage.value = `书架加载失败：${toErrorMessage(error)}`;
  }

  try {
    await refreshBookSources();
  } catch (error) {
    bookSources.value = [];
    lastMessage.value = `书源加载失败：${toErrorMessage(error)}`;
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

async function refreshBookSources() {
  sourceLoading.value = true;
  try {
    bookSources.value = await fetchBookSources();
  } finally {
    sourceLoading.value = false;
  }
}

async function handleSourceSearch() {
  const keyword = sourceSearchKeyword.value.trim();
  sourceSearchTouched.value = true;
  sourceSearchError.value = '';

  if (!keyword) {
    sourceSearchResults.value = [];
    sourceSearchError.value = '请输入书名、作者或关键词后再搜索';
    return;
  }

  if (!searchableImportedSources.value.length) {
    sourceSearchResults.value = [];
    sourceSearchError.value = '当前没有已启用且可搜索的导入书源，请先到书源管理导入 Legado 书源';
    return;
  }

  sourceSearchLoading.value = true;
  try {
    sourceSearchResults.value = await searchBookSources({ keyword, limit: 24 });
    if (!sourceSearchResults.value.length) {
      sourceSearchError.value = `没有找到“${keyword}”相关结果`;
    }
  } catch (error) {
    sourceSearchResults.value = [];
    sourceSearchError.value = toErrorMessage(error);
  } finally {
    sourceSearchLoading.value = false;
  }
}

function clearSourceSearch() {
  sourceSearchKeyword.value = '';
  sourceSearchResults.value = [];
  sourceSearchError.value = '';
  sourceSearchTouched.value = false;
}

function resultImportKind(result: BookSourceSearchResult): AddBookPayload['bookKind'] {
  return result.bookKind ?? '长小说';
}

function resultImportLanguage(result: BookSourceSearchResult): AddBookPayload['language'] {
  return result.sourceLanguage ?? '中文';
}

async function handleImportSearchResult(result: BookSourceSearchResult) {
  sourceSearchImporting.value = result.sourceUrl;
  lastMessage.value = `正在加入《${result.title}》到书库...`;
  try {
    const book = await importBook({
      sourceUrl: result.sourceUrl,
      bookKind: resultImportKind(result),
      language: resultImportLanguage(result),
      needTranslation: false,
      title: result.title.trim() || undefined,
      sourceId: result.sourceId,
      synopsis: result.synopsis?.trim() || undefined,
      cover: result.cover || undefined,
    });
    updateBookCache(book);
    selectedBookId.value = book.id;
    await loadBookDetail(book.id);
    currentView.value = 'detail';
    lastMessage.value = `《${book.title}》已加入书库`;
  } catch (error) {
    lastMessage.value = `加入书库失败：${toErrorMessage(error)}`;
  } finally {
    sourceSearchImporting.value = null;
  }
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
    localBookFiles.value = [];
    resetAddBookForm();
  } catch (error) {
    lastMessage.value = `导入失败：${toErrorMessage(error)}`;
  } finally {
    importing.value = false;
  }
}

function handleLocalFileChange(event: Event) {
  const input = event.target as HTMLInputElement | null;
  localBookFiles.value = Array.from(input?.files ?? []).filter((file) => /\.(txt|text)$/i.test(file.name));
  if (localBookFiles.value.length) {
    preview.value = null;
    const fileLabel = localBookFiles.value.length === 1
      ? localBookFiles.value[0].name
      : `${localBookFiles.value.length} 个 TXT 文件`;
    lastMessage.value = `已选择本地文件：${fileLabel}`;
  } else if (input?.files?.length) {
    lastMessage.value = '仅支持批量导入 TXT / TEXT 文件';
  }
}

async function handleImportLocal() {
  if (!localBookFiles.value.length) {
    lastMessage.value = '请先选择至少一个本地 TXT 文件';
    return;
  }

  const files = [...localBookFiles.value];
  const importedBooks: BookRecord[] = [];
  const failedFiles: Array<{ file: File; reason: string }> = [];
  const customTitle = files.length === 1 ? addBookForm.title : '';

  importing.value = true;
  lastMessage.value = `正在批量导入本地文件（1 / ${files.length}）：${files[0].name}`;

  try {
    for (const [index, file] of files.entries()) {
      lastMessage.value = `正在批量导入本地文件（${index + 1} / ${files.length}）：${file.name}`;

      try {
        const book = await importLocalBook(file, {
          bookKind: addBookForm.bookKind,
          title: customTitle,
          language: addBookForm.language,
          needTranslation: addBookForm.needTranslation,
        });
        importedBooks.push(book);
        updateBookCache(book);
      } catch (error) {
        failedFiles.push({
          file,
          reason: toErrorMessage(error),
        });
      }
    }

    if (!importedBooks.length) {
      localBookFiles.value = failedFiles.map((item) => item.file);
      localFilePickerKey.value += 1;
      lastMessage.value = failedFiles.length === 1
        ? `《${failedFiles[0].file.name}》导入失败：${failedFiles[0].reason}`
        : `${failedFiles.length} 个本地文件导入失败，请检查编码或内容格式后重试`;
      return;
    }

    const latestBook = importedBooks[importedBooks.length - 1];
    selectedBookId.value = latestBook.id;

    if (importedBooks.length === 1 && !failedFiles.length) {
      await loadBookDetail(latestBook.id);
      currentView.value = 'detail';
      lastMessage.value = `《${latestBook.title}》已从本地文件导入`;
    } else {
      currentView.value = 'library';
      lastMessage.value = failedFiles.length
        ? `批量导入完成：成功 ${importedBooks.length} 本，失败 ${failedFiles.length} 本`
        : `批量导入完成：成功导入 ${importedBooks.length} 本小说`;
    }

    preview.value = null;

    if (failedFiles.length) {
      localBookFiles.value = failedFiles.map((item) => item.file);
      localFilePickerKey.value += 1;
      return;
    }

    showImportPanel.value = false;
    resetAddBookForm();
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

function triggerLocalFilePicker() {
  localFileInput.value?.click();
}

function triggerReaderTextColorPicker() {
  readerTextColorInput.value?.click();
}

function triggerReaderBackgroundColorPicker() {
  readerBackgroundColorInput.value?.click();
}

function resetAddBookForm() {
  addBookForm.title = '';
  addBookForm.sourceUrl = '';
  addBookForm.bookKind = '长小说';
  addBookForm.language = '中文';
  addBookForm.needTranslation = false;
  localBookFiles.value = [];
  localFilePickerKey.value += 1;
}

function buildSourceImportSummaryMessage(result: BookSourceImportResult) {
  return `新增 ${result.imported.length} 个，更新 ${result.updated.length} 个，重复 ${result.duplicates.length} 个，忽略 ${result.ignored.length} 个`;
}

function formatImportedSourceNames(sources: BookSourceRecord[]) {
  return sources.map((item) => item.name).join('、');
}

async function applyImportedBookSourceResult(result: BookSourceImportResult) {
  sourceImportSummary.value = result;
  await refreshBookSources();

  lastMessage.value = `书源导入完成：${buildSourceImportSummaryMessage(result)}`;
}

async function handleSourceImportByUrl() {
  const url = sourceImportForm.url.trim();
  if (!url) {
    lastMessage.value = '请先填写书源导入链接';
    return;
  }

  sourceImporting.value = true;
  lastMessage.value = '正在导入远程 Legado 书源规则...';
  try {
    const result = await importBookSourcesFromUrl({ url });
    await applyImportedBookSourceResult(result);
    sourceImportForm.url = '';
  } catch (error) {
    lastMessage.value = `Legado 书源链接导入失败：${toErrorMessage(error)}`;
  } finally {
    sourceImporting.value = false;
  }
}

async function handleSourceImportByText() {
  const content = sourceImportForm.content.trim();
  if (!content) {
    lastMessage.value = '请先粘贴书源内容';
    return;
  }

  sourceImporting.value = true;
  lastMessage.value = '正在导入粘贴的 Legado 书源规则...';
  try {
    const result = await importBookSourcesFromText({ content });
    await applyImportedBookSourceResult(result);
  } catch (error) {
    lastMessage.value = `Legado 书源内容导入失败：${toErrorMessage(error)}`;
  } finally {
    sourceImporting.value = false;
  }
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
  if (view === 'search') {
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

  try {
    exportingFormat.value = format;
    const result = await exportBook(selectedBookId.value, format);
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
  globalTheme.value = mapReaderThemeToGlobalTheme(theme);
  persistReaderPreferences();
}

function applyGlobalTheme(theme: GlobalTheme) {
  globalTheme.value = theme;
  readerTheme.value = mapGlobalThemeToReaderTheme(theme);
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

function formatBookContentCount(
  detail: BookDetailResponse | null,
  bookKind: BookRecord['bookKind'] | PreviewResponse['bookKind'] = '轻小说',
): string {
  if (!detail || detail.downloadedChapterCount === 0) {
    return '未缓存';
  }
  return formatContentCount(detail.totalWords, bookKind);
}

function formatChapterMeta(chapter: ChapterRecord, bookKind: BookRecord['bookKind'] | null | undefined): string {
  if (!chapter.downloaded) {
    return '未缓存';
  }
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
    contentCountText: '未缓存',
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

function eventValue(event: Event): string {
  const target = event.target as { value?: unknown } | null;
  return typeof target?.value === 'string' ? target.value : '';
}

function eventChecked(event: Event): boolean {
  const target = event.target as { checked?: unknown } | null;
  return target?.checked === true;
}

function eventNumber(event: Event, fallback = 0): number {
  const value = Number(eventValue(event));
  return Number.isFinite(value) ? value : fallback;
}

function toggleChapterSelection(chapterIndex: number, checked: boolean) {
  if (checked) {
    selectedChapterIndexes.value = [...new Set([...selectedChapterIndexes.value, chapterIndex])].sort((a, b) => a - b);
    return;
  }

  selectedChapterIndexes.value = selectedChapterIndexes.value.filter((index) => index !== chapterIndex);
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
  appendActivityLog(value.includes('失败') ? 'error' : 'system', '后端状态', value);
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
  if (value !== 'library' && value !== 'logs' && value !== 'search') {
    stopGlobalTaskPolling();
  }
  updateScrollAffordances();
});

function syncWindowTitle() {
  if (typeof document !== 'undefined') {
    document.title = windowTitle.value;
  }
}

watch(windowTitle, () => {
  syncWindowTitle();
}, { immediate: true });

onMounted(() => {
  window.addEventListener('scroll', handleWindowScroll, { passive: true });
  updateScrollAffordances();
  setupDragScroll();
  void bootstrap();
});

onBeforeUnmount(() => {
  window.removeEventListener('scroll', handleWindowScroll);
  dragScrollCleanup?.();
  void flushReaderProgressSave({ silent: true });
  clearReaderScrollSaveTimer();
  clearReaderScrollReleaseTimer();
  clearPendingReaderRestore();
  stopTaskPolling();
  stopGlobalTaskPolling();
});
</script>

<template>
  <fluent-design-system-provider
    class="shell"
    :class="{
      'shell--reader-mode': currentView === 'reader',
    }"
    :accent-base-color="accentBaseColor"
    neutral-base-color="#8f8c86"
    control-corner-radius="4"
    layer-corner-radius="8"
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
          </div>
        </div>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          type="button"
          :class="{ active: currentView === item.key }"
          :title="item.label"
          :aria-label="item.label"
          @click="navigate(item.key)"
        >
          <span class="nav-icon" aria-hidden="true" v-html="item.icon"></span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <span>v0.5.0</span>
      </div>
    </aside>

    <section class="main-area">
      <header v-if="currentView !== 'reader'" class="app-header" :data-view="currentView">
        <div class="app-header-drag">
          <fluent-button
            v-if="currentView === 'detail'"
            class="text-btn app-header-back no-drag"
            type="button"
            @click="backToLibrary"
          >
            ‹ 返回书架
          </fluent-button>
          <p v-if="appHeaderMeta.kicker" class="page-kicker">{{ appHeaderMeta.kicker }}</p>
          <div class="app-header-title-row">
            <h1 class="main-title" v-if="currentView === 'library'">青卷</h1>
            <h2 v-else>{{ appHeaderMeta.title }}</h2>
            <span
              v-if="currentView === 'library'"
              class="book-state-pill"
            >
              {{ readerThemeLabel }} · {{ readerFontSize }}
            </span>
            <span
              v-else-if="currentView === 'logs'"
              class="book-state-pill"
            >
              {{ logSummary.total }} 条记录
            </span>
            <span
              v-else-if="currentView === 'sources'"
              class="book-state-pill"
            >
              {{ sourceStats.total }} 个规则
            </span>
            <span
              v-else-if="currentView === 'settings'"
              class="book-state-pill"
            >
              {{ activeProviderOption.label }}
            </span>
            <span
              v-else-if="currentView === 'detail' && selectedBook"
              class="book-state-pill"
            >
              {{ selectedBook.bookKind }} · {{ selectedBook.language }}
            </span>
          </div>
          <p class="page-subtitle">{{ appHeaderMeta.subtitle }}</p>
        </div>

        <div class="app-header-actions no-drag">
          <template v-if="currentView === 'library'">
            <fluent-search
              class="library-search-field app-header-search"
              :value="searchQuery"
              placeholder="搜索书名或作者..."
              appearance="outline"
              @input="searchQuery = eventValue($event)"
            ></fluent-search>
            <fluent-button
              class="primary-btn"
              appearance="accent"
              type="button"
              @click="showImportPanel = true"
            >
              添加书籍
            </fluent-button>
          </template>

          <template v-else-if="currentView === 'search'">
            <fluent-search
              class="library-search-field app-header-search"
              :value="sourceSearchKeyword"
              placeholder="搜索书名、作者或关键词..."
              appearance="outline"
              @input="sourceSearchKeyword = eventValue($event)"
              @keydown.enter.prevent="handleSourceSearch"
            ></fluent-search>
            <fluent-button
              class="primary-btn"
              appearance="accent"
              type="button"
              :disabled="sourceSearchLoading"
              @click="handleSourceSearch"
            >
              {{ sourceSearchLoading ? '搜索中...' : '搜索' }}
            </fluent-button>
          </template>

          <template v-else-if="currentView === 'sources'">
            <fluent-search
              class="library-search-field app-header-search"
              :value="sourceSearchQuery"
              placeholder="搜索书源名称、域名或标签..."
              appearance="outline"
              @input="sourceSearchQuery = eventValue($event)"
            ></fluent-search>
          </template>

          <fluent-button
            v-if="currentView === 'logs'"
            class="text-btn compact"
            appearance="stealth"
            type="button"
            @click="clearActivityLogs"
          >
            清空日志
          </fluent-button>
          <fluent-button
            v-if="currentView === 'settings'"
            class="primary-btn"
            appearance="accent"
            :disabled="savingSettings"
            type="button"
            @click="handleSaveSettings"
          >
            {{ savingSettings ? '保存中...' : '保存设置' }}
          </fluent-button>
        </div>
      </header>

      <template v-if="currentView === 'library'">
        <section class="library-view">
          <section class="library-summary-strip">
            <p class="library-summary-inline">
              <span v-for="(item, index) in stats" :key="item.label">
                {{ item.label }} <strong>{{ item.value }}</strong>
                <template v-if="index < stats.length - 1"> &nbsp;&nbsp;|&nbsp;&nbsp; </template>
              </span>
              &nbsp;&nbsp;|&nbsp;&nbsp;
              进行中任务 <strong>{{ globalActiveTasks.length }}</strong>
            </p>
            <div class="library-summary-actions">
              <div class="library-display-toggle">
                <fluent-button
                  type="button"
                  appearance="stealth"
                  :class="{ active: libraryDisplayMode === 'grid' }"
                  title="网格视图"
                  @click="libraryDisplayMode = 'grid'"
                >⊞</fluent-button>
                <fluent-button
                  type="button"
                  appearance="stealth"
                  :class="{ active: libraryDisplayMode === 'list' }"
                  title="列表视图"
                  @click="libraryDisplayMode = 'list'"
                >☰</fluent-button>
              </div>
              <fluent-button
                class="text-btn task-insight-btn"
                appearance="stealth"
                type="button"
                @click="toggleTasksOverview"
              >
                视图详情 ›
              </fluent-button>
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
                <fluent-button
                  class="ghost-btn compact"
                  type="button"
                  @click="tasksOverviewOpen = false"
                >
                  收起
                </fluent-button>
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
                      <fluent-button
                        class="ghost-btn compact"
                        type="button"
                        @click="openTaskBook(task)"
                      >
                        查看书籍
                      </fluent-button>
                      <fluent-button
                        v-if="task.status === 'failed'"
                        class="ghost-btn compact"
                        :disabled="taskRetryingId === task.id"
                        type="button"
                        @click="handleRetryTask(task.id)"
                      >
                        {{ taskRetryingId === task.id ? '重试中...' : '失败重试' }}
                      </fluent-button>
                    </div>
                  </div>
                </article>
              </div>
            </section>
          </transition>

          <section :class="['books-container', `books-container--${libraryDisplayMode}`]">
            <template v-if="libraryDisplayMode === 'grid'">
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
                    <span>{{ book.lastReadChapterIndex > 0 ? '阅读进度' : '进度' }}</span>
                    <strong>
                      {{
                        book.lastReadChapterIndex > 0
                          ? `${book.lastReadChapterIndex} / ${book.chapterCount}`
                          : `${book.chapterCount} / ${book.chapterCount}`
                      }}
                    </strong>
                  </div>
                </div>
              </article>
            </template>

            <template v-else>
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
                  <div v-if="book.cover" class="cover-filter"></div>
                  <div v-else class="cover-glow"></div>
                </div>

                <div class="card-body">
                  <h3>{{ book.title }}</h3>
                  <p class="author-line">{{ getPresentation(book).author }}</p>
                  <div class="book-tags">
                    <span>{{ book.bookKind }}</span>
                    <span>{{ book.language }}</span>
                    <span v-if="book.translated">翻译中</span>
                  </div>
                </div>

                <div class="list-meta">
                  <span class="progress-text">
                    {{ book.lastReadChapterIndex > 0 ? `${book.lastReadChapterIndex}/${book.chapterCount}` : `${book.chapterCount}章` }}
                  </span>
                  <div class="progress-track">
                    <div
                      class="progress-bar"
                      :style="{ width: `${book.chapterCount ? Math.round((book.lastReadChapterIndex / book.chapterCount) * 100) : 0}%` }"
                    ></div>
                  </div>
                </div>
              </article>
            </template>
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
                  <fluent-button
                    class="icon-btn"
                    @click="showImportPanel = false"
                  >
                    ×
                  </fluent-button>
                </div>

                <label class="form-field">
                  <span>内容链接</span>
                  <fluent-text-field
                    :value="addBookForm.sourceUrl"
                    placeholder="https://example.com/novel/123 或漫画详情页链接"
                    type="url"
                    appearance="outline"
                    @input="addBookForm.sourceUrl = eventValue($event)"
                  ></fluent-text-field>
                  <small class="field-hint">
                    已支持自动识别小说 / 漫画；漫画目前支持 18comic.vip 与 bikawebapp.com。
                  </small>
                </label>

                <label class="form-field">
                  <span>本地小说文件</span>
                  <input
                    :key="localFilePickerKey"
                    ref="localFileInput"
                    class="native-file-input"
                    accept=".txt,.text"
                    multiple
                    type="file"
                    @change="handleLocalFileChange"
                  />
                  <div class="file-picker-row">
                    <fluent-button
                      class="secondary-btn"
                      type="button"
                      :disabled="importing"
                      @click="triggerLocalFilePicker"
                    >
                      选择 TXT 文件
                    </fluent-button>
                    <span
                      class="file-picked"
                      :class="{ 'file-picked--empty': !localBookFiles.length }"
                    >
                      {{ localBookFiles.length ? '已选择 ' + localBookFiles.length + ' 个文件' : '尚未选择文件' }}
                    </span>
                  </div>
                  <small class="field-hint">
                    支持多选并批量导入本地 TXT / TEXT 文本，系统会自动尝试拆分章节。
                  </small>
                  <strong
                    v-if="localBookFiles.length"
                    class="file-picked file-picked--list"
                  >
                    已选择 {{ localBookFiles.length }} 个文件：{{ localBookFiles.slice(0, 3).map((file) => file.name).join('、') }}<template v-if="localBookFiles.length > 3"> 等 {{ localBookFiles.length }} 个</template>
                  </strong>
                  <small
                    v-if="localBookFiles.length > 1 && addBookForm.title.trim()"
                    class="field-hint"
                  >
                    批量导入时将自动使用各文件名作为书名，单个书名输入不会覆盖全部文件。
                  </small>
                </label>

                <div class="field-grid">
                  <label class="form-field">
                    <span>内容类型</span>
                    <fluent-select
                      :value="addBookForm.bookKind"
                      appearance="outline"
                      @change="addBookForm.bookKind = eventValue($event) as AddBookPayload['bookKind']"
                    >
                      <fluent-option value="长小说">长小说</fluent-option>
                      <fluent-option value="轻小说">轻小说</fluent-option>
                      <fluent-option value="漫画">漫画</fluent-option>
                    </fluent-select>
                    <small class="field-hint">远程链接会自动识别，手动选择主要用于本地导入。</small>
                  </label>

                  <label class="form-field">
                    <span>语言</span>
                    <fluent-select
                      :value="addBookForm.language"
                      appearance="outline"
                      @change="addBookForm.language = eventValue($event) as AddBookPayload['language']"
                    >
                      <fluent-option value="中文">中文</fluent-option>
                      <fluent-option value="英文">英文</fluent-option>
                      <fluent-option value="日文">日文</fluent-option>
                    </fluent-select>
                  </label>
                </div>

                <label class="form-field">
                  <span>书名（可选）</span>
                  <fluent-text-field
                    :value="addBookForm.title"
                    placeholder="允许留空，抓取后自动识别"
                    type="text"
                    appearance="outline"
                    @input="addBookForm.title = eventValue($event)"
                  ></fluent-text-field>
                </label>

                <label class="check-line">
                  <fluent-switch
                    :checked="addBookForm.needTranslation"
                    @change="addBookForm.needTranslation = eventChecked($event)"
                  >抓取完成后自动进入 AI 翻译流程</fluent-switch>
                </label>

                <div class="drawer-actions">
                  <fluent-button
                    class="ghost-btn"
                    :disabled="loadingPreview"
                    @click="handlePreview"
                  >
                    {{ loadingPreview ? '解析中...' : '预览章节' }}
                  </fluent-button>
                  <fluent-button
                    class="primary-btn"
                    :disabled="importing"
                    @click="handleImport"
                  >
                    {{ importing ? '导入中...' : '加入书架' }}
                  </fluent-button>
                </div>

                <div class="drawer-actions drawer-actions--local">
                  <fluent-button
                    class="secondary-btn"
                    :disabled="importing || !localBookFiles.length"
                    @click="handleImportLocal"
                  >
                    {{ importing ? '导入中...' : `导入本地文件${localBookFiles.length > 1 ? `（${localBookFiles.length}）` : ''}` }}
                  </fluent-button>
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

        </section>
      </template>

      <template v-else-if="currentView === 'search'">
        <section class="search-view">
          <section class="search-hero">
            <div class="search-hero-copy">
              <p class="page-kicker">全量搜索</p>
              <h2>搜索已导入书源</h2>
              <p>
                默认搜索全部已启用且可搜索的 Legado 书源，找到后可直接加入书库继续阅读。
              </p>
            </div>

            <div class="search-hero-bar">
              <fluent-search
                class="search-input search-input-large"
                :value="sourceSearchKeyword"
                placeholder="输入书名、作者或关键词"
                appearance="outline"
                @input="sourceSearchKeyword = eventValue($event)"
                @keydown.enter.prevent="handleSourceSearch"
              ></fluent-search>
              <div class="search-hero-actions">
                <fluent-button
                  class="primary-btn"
                  appearance="accent"
                  type="button"
                  :disabled="sourceSearchLoading"
                  @click="handleSourceSearch"
                >
                  {{ sourceSearchLoading ? '搜索中...' : '搜索' }}
                </fluent-button>
                <fluent-button
                  class="ghost-btn"
                  type="button"
                  :disabled="!sourceSearchKeyword && !sourceSearchResults.length && !sourceSearchTouched"
                  @click="clearSourceSearch"
                >
                  清空
                </fluent-button>
                <fluent-button
                  class="text-btn"
                  type="button"
                  @click="navigate('sources')"
                >
                  去书源管理
                </fluent-button>
              </div>
              <p class="search-hero-hint">
                {{ searchableImportedSources.length ? `当前可搜索书源 ${searchableImportedSources.length} 个` : '还没有可搜索书源，请先导入并启用 Legado 书源' }}
              </p>
            </div>
          </section>

          <section class="settings-card search-result-panel">
            <div class="settings-card-head">
              <div>
                <p class="page-kicker">搜索结果</p>
                <h3>从导入书源中查找作品</h3>
                <p>找到后可以直接加入书库，继续走原有的导入、阅读和翻译流程。</p>
              </div>
              <span class="search-result-count">
                {{ sourceSearchResults.length ? `${sourceSearchResults.length} 条结果` : '等待搜索' }}
              </span>
            </div>

            <div
              v-if="sourceSearchLoading"
              class="status-note flush"
            >
              <strong>正在搜索</strong>
              <p>正在按全部可搜索书源检索作品，请稍等片刻。</p>
            </div>

            <div
              v-else-if="!sourceSearchTouched"
              class="status-note flush"
            >
              <strong>开始搜索</strong>
              <p>输入关键词并点击搜索，结果会显示在这里。</p>
            </div>

            <div
              v-else-if="searchResultsEmptyState"
              class="status-note flush"
            >
              <strong>{{ sourceSearchResults.length ? '搜索失败' : '没有结果' }}</strong>
              <p>{{ searchResultsEmptyState }}</p>
            </div>

            <div
              v-else
              class="search-result-list"
            >
              <article
                v-for="result in sourceSearchResults"
                :key="`${result.sourceId}:${result.sourceUrl}`"
                class="source-card search-result-card"
              >
                <div class="source-search-result-head">
                  <div
                    v-if="result.cover"
                    class="source-search-result-cover"
                  >
                    <img
                      :src="result.cover"
                      :alt="`${result.title} 封面`"
                      loading="lazy"
                    />
                  </div>
                  <div class="source-search-result-copy">
                    <h4>{{ result.title }}</h4>
                    <p>{{ result.author || '作者未知' }}</p>
                    <small>{{ result.sourceName }} · {{ result.sourceUrl }}</small>
                  </div>
                </div>

                <p class="source-description">{{ result.synopsis || '暂无简介' }}</p>
                <p class="source-meta-line">
                  {{ result.bookKind || '未知类型' }}
                  <template v-if="result.sourceLanguage"> · {{ result.sourceLanguage }}</template>
                </p>

                <div class="source-card-actions search-result-actions">
                  <fluent-button
                    class="ghost-btn compact"
                    type="button"
                    :disabled="librarySourceUrlSet.has(result.sourceUrl)"
                    @click="handleOpenExternal(result.sourceUrl, '作品链接')"
                  >
                    打开链接
                  </fluent-button>
                  <fluent-button
                    class="primary-btn compact"
                    type="button"
                    :disabled="librarySourceUrlSet.has(result.sourceUrl) || sourceSearchImporting === result.sourceUrl"
                    @click="handleImportSearchResult(result)"
                  >
                    {{
                      librarySourceUrlSet.has(result.sourceUrl)
                        ? '已在书库'
                        : sourceSearchImporting === result.sourceUrl
                          ? '加入中...'
                          : '加入书库'
                    }}
                  </fluent-button>
                </div>
              </article>
            </div>
          </section>
        </section>
      </template>

      <template v-else-if="currentView === 'sources'">
        <section class="source-view">
          <section class="library-summary-strip source-summary-strip">
            <p class="library-summary-inline">
              已导入 <strong>{{ sourceStats.total }}</strong> 个 Legado 书源
              &nbsp;&nbsp;|&nbsp;&nbsp;
              启用 <strong>{{ sourceStats.enabled }}</strong> 个
              &nbsp;&nbsp;|&nbsp;&nbsp;
              含搜索规则 <strong>{{ sourceStats.searchable }}</strong> 个
            </p>
          </section>

          <section class="source-workbench">
            <section class="settings-card source-panel">
              <div class="settings-card-head">
                <div>
                  <p class="page-kicker">Legado / 阅读</p>
                  <h3>导入自定义书源规则</h3>
                  <p>这里保存的是 gedoor/legado 支持的书源 JSON 规则，用于管理 `bookSourceName`、`bookSourceUrl` 与各类解析规则。</p>
                </div>
              </div>

              <label class="form-field">
                <span>书源导入链接</span>
                <fluent-text-field
                  :value="sourceImportForm.url"
                  placeholder="https://shuyuan-api.yiove.com/import/book-source/..."
                  type="url"
                  appearance="outline"
                  @input="sourceImportForm.url = eventValue($event)"
                ></fluent-text-field>
                <small class="field-hint">
                  支持 Legado/阅读 的远程书源 JSON 链接，内容可以是单个对象、数组，或包装在 `data` / `bookSources` 中的数组。
                </small>
              </label>

              <div class="drawer-actions source-actions">
                <fluent-button
                  class="ghost-btn"
                  :disabled="sourceImporting"
                  type="button"
                  @click="handleSourceImportByUrl"
                >
                  {{ sourceImporting ? '导入中...' : '导入链接' }}
                </fluent-button>
              </div>

              <label class="form-field">
                <span>书源内容</span>
                <fluent-text-area
                  :value="sourceImportForm.content"
                  placeholder='[{"bookSourceName":"示例书源","bookSourceUrl":"https://example.com","ruleSearch":{},"ruleBookInfo":{},"ruleToc":{},"ruleContent":{}}]'
                  rows="6"
                  appearance="outline"
                  @input="sourceImportForm.content = eventValue($event)"
                ></fluent-text-area>
                <small class="field-hint">
                  支持 `bookSourceName`、`bookSourceUrl`、`bookSourceGroup`、`bookSourceType`、`ruleSearch`、`ruleBookInfo`、`ruleToc`、`ruleContent` 等 Legado 字段。
                </small>
              </label>

              <div class="drawer-actions source-actions">
                <fluent-button
                  class="ghost-btn"
                  :disabled="sourceImporting"
                  type="button"
                  @click="handleSourceImportByText"
                >
                  {{ sourceImporting ? '导入中...' : '导入内容' }}
                </fluent-button>
              </div>

              <div
                v-if="sourceImportSummary"
                class="status-note flush"
              >
                <strong>本次书源导入结果</strong>
                <p>{{ buildSourceImportSummaryMessage(sourceImportSummary) }}</p>
                <p v-if="sourceImportSummary.imported.length">
                  新增：{{ formatImportedSourceNames(sourceImportSummary.imported) }}
                </p>
                <p v-if="sourceImportSummary.duplicates.length">
                  重复：{{ sourceImportSummary.duplicates.join('、') }}
                </p>
                <p v-if="sourceImportSummary.ignored.length">
                  忽略：{{ sourceImportSummary.ignored.join('；') }}
                </p>
              </div>

              <div
                v-if="!bookSources.length"
                class="status-note flush"
              >
                <strong>尚未导入 Legado 书源</strong>
                <p>粘贴阅读 App 导出的书源 JSON，或填写远程书源链接后导入。</p>
              </div>
            </section>

            <section class="settings-card source-list-panel">
              <div class="settings-card-head">
                <div>
                  <p class="page-kicker">书源列表</p>
                  <h3>已导入的 Legado 规则</h3>
                  <p>这里仅显示从阅读/Legado JSON 导入的自定义书源，不再混入内置抓取站点。</p>
                </div>
              </div>

              <div
                v-if="sourceLoading"
                class="status-note flush"
              >
                <strong>正在加载书源</strong>
                <p>稍等片刻，正在同步本地书源库...</p>
              </div>

              <div
                v-else-if="!filteredSources.length"
                class="status-note flush"
              >
                <strong>暂无可用书源</strong>
                <p>当前没有匹配的书源记录。</p>
              </div>

              <div
                v-else
                class="source-grid"
              >
                <article
                  v-for="source in filteredSources"
                  :key="source.id"
                  class="source-card"
                >
                  <div class="source-card-head">
                    <div>
                      <h4>{{ source.name }}</h4>
                      <p>{{ source.baseUrl }}</p>
                    </div>
                    <span
                      class="source-status-pill"
                      :data-status="source.status"
                    >
                      {{ source.statusMessage || source.status }}
                    </span>
                  </div>
                  <p class="source-description">{{ source.description }}</p>
                  <p class="source-meta-line">{{ source.tags.join(' · ') || '暂无标签' }}</p>
                  <div class="source-card-actions">
                    <fluent-button
                      v-if="source.importUrl"
                      class="ghost-btn compact"
                      type="button"
                      @click="handleOpenExternal(source.importUrl, '书源导入链接')"
                    >
                      打开导入链接
                    </fluent-button>
                    <span v-else class="source-meta-line">已保存为 Legado 书源规则</span>
                  </div>
                </article>
              </div>
            </section>
          </section>
        </section>
      </template>

      <template v-else-if="currentView === 'logs'">
        <section class="logs-view">
          <section class="logs-table-panel">
            <div class="logs-table-head">
              <span>时间</span>
              <span>内容</span>
              <span>记录</span>
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
              class="logs-table-body"
            >
              <article
                v-for="entry in activityLogs"
                :key="entry.id"
                class="logs-table-row"
                :data-log-category="entry.category"
              >
                <time>{{ entry.at }}</time>
                <span class="logs-table-category">{{ logCategoryLabel(entry.category) }}</span>
                <div class="logs-table-content">
                  <strong class="logs-table-title">{{ entry.title }}</strong>
                  <p
                    v-if="entry.detail && entry.detail !== entry.title"
                    class="logs-table-detail"
                  >
                    {{ entry.detail }}
                  </p>
                </div>
              </article>
            </div>
          </section>
        </section>
      </template>

      <template v-else-if="currentView === 'settings'">
        <section class="settings-view">
          <section class="settings-panel">
            <div class="settings-section-head">
              <div>
                <h3>界面主题</h3>
                <p>全局亮色或深色，或是跟随您的操作系统设置。</p>
              </div>
            </div>
            <div class="theme-stack">
              <fluent-button
                v-for="opt in [{key:'light',label:'清亮'}, {key:'care',label:'护眼模式'}, {key:'dark',label:'深邃沉浸'}, {key:'system',label:'跟随系统'}]"
                :key="opt.key"
                class="ghost-btn compact"
                :class="{ activePreviewBtn: globalTheme === opt.key }"
                type="button"
                @click="applyGlobalTheme(opt.key as GlobalTheme)"
              >
                {{ opt.label }}
              </fluent-button>
            </div>
          </section>

          <section class="settings-panel settings-panel--translation">
            <div class="settings-section-head">
              <div>
                <h3>AI 配置</h3>
                <p>左侧切换服务提供商，右侧集中编辑当前提供商的地址、模型和启用状态。</p>
              </div>
            </div>

            <div class="settings-provider-layout">
              <div class="provider-list">
                <fluent-button
                  v-for="provider in providerOptions"
                  :key="provider.key"
                  :class="[providerCardClass(provider.key), 'provider-option--row']"
                  @click="setDefaultProvider(provider.key)"
                >
                  <strong>{{ provider.label }}</strong>
                  <span>{{ provider.description }}</span>
                </fluent-button>
              </div>

              <div class="settings-provider-form">
                <label class="form-field">
                  <span>API 密钥</span>
                  <fluent-text-field
                    :value="settings.providers[activeProvider].apiKey"
                    placeholder="sk-..."
                    type="password"
                    appearance="outline"
                    @input="settings.providers[activeProvider].apiKey = eventValue($event)"
                  ></fluent-text-field>
                  <small>您的 API 密钥将加密保存在本地，不会上传到服务器。</small>
                </label>

                <label class="form-field">
                  <span>API 地址</span>
                  <fluent-text-field
                    :value="settings.providers[activeProvider].baseUrl"
                    placeholder="https://api.openai.com/v1"
                    type="text"
                    appearance="outline"
                    @input="settings.providers[activeProvider].baseUrl = eventValue($event)"
                  ></fluent-text-field>
                </label>

                <label class="form-field">
                  <span>翻译模型</span>
                  <fluent-text-field
                    :value="settings.providers[activeProvider].model"
                    :list="`${activeProvider}-model-options`"
                    placeholder="输入模型名，例如 gpt-5.4"
                    type="text"
                    appearance="outline"
                    @input="settings.providers[activeProvider].model = eventValue($event)"
                  ></fluent-text-field>
                  <datalist :id="`${activeProvider}-model-options`">
                    <option
                      v-for="option in providerModelOptions"
                      :key="option"
                      :value="option"
                    />
                  </datalist>
                  <small>可直接输入任意模型名，建议项仅用于快速填写。</small>
                </label>

                <label class="check-line">
                  <fluent-switch
                    :checked="settings.providers[activeProvider].enabled"
                    @change="settings.providers[activeProvider].enabled = eventChecked($event)"
                  >启用当前提供商</fluent-switch>
                </label>

                <div class="status-note flush">
                  <strong>漫画 OCR 定位</strong>
                  <p>启用后优先调用独立 OCR 服务识别文字内容和位置，翻译完成后按定位区域进行本地修复与重绘。该服务按文档直接调用 `/ocr`，无需再配置模型，也可以不填写鉴权。</p>
                </div>

                <label class="check-line">
                  <fluent-switch
                    :checked="settings.mangaOcr.enabled"
                    @change="settings.mangaOcr.enabled = eventChecked($event)"
                  >启用漫画 OCR 定位与修复管线</fluent-switch>
                </label>

                <label class="form-field">
                  <span>OCR API 地址</span>
                  <fluent-text-field
                    :value="settings.mangaOcr.baseUrl"
                    placeholder="http://114.66.46.74:8080"
                    type="text"
                    appearance="outline"
                    @input="settings.mangaOcr.baseUrl = eventValue($event)"
                  ></fluent-text-field>
                </label>

                <label class="form-field">
                  <span>OCR API 密钥</span>
                  <fluent-text-field
                    :value="settings.mangaOcr.apiKey"
                    placeholder="可选：仅当 OCR 服务本身需要鉴权时填写"
                    type="password"
                    appearance="outline"
                    @input="settings.mangaOcr.apiKey = eventValue($event)"
                  ></fluent-text-field>
                </label>

                <label class="form-field">
                  <span>OCR 服务说明</span>
                  <fluent-text-field
                    value="当前 OCR 服务按文档直接调用 /ocr，无需再配置模型名称"
                    readonly
                    type="text"
                    appearance="outline"
                  ></fluent-text-field>
                  <small>通常只需要填写 OCR API 地址；只有 OCR 服务本身要求鉴权时，才需要额外填写上面的 OCR API 密钥。</small>
                </label>
              </div>
            </div>
          </section>

          <section class="settings-panel settings-panel--application">
            <div class="settings-section-head">
              <div>
                <h3>界面与抓取设置</h3>
                <p>应用级偏好与漫画凭证放在同一个分组下，便于统一维护。</p>
              </div>
            </div>

            <div class="settings-application-grid">
              <label class="form-field">
                <span>默认翻译服务</span>
                <fluent-select
                  :value="settings.defaultProvider"
                  appearance="outline"
                  @change="settings.defaultProvider = eventValue($event) as TranslationProvider"
                >
                  <fluent-option
                    v-for="provider in providerOptions"
                    :key="provider.key"
                    :value="provider.key"
                  >
                    {{ provider.label }}
                  </fluent-option>
                </fluent-select>
              </label>

              <label class="form-field">
                <span>阅读时预翻译后续章节</span>
                <fluent-select
                  :value="String(settings.autoTranslateNextChapters)"
                  appearance="outline"
                  @change="settings.autoTranslateNextChapters = eventNumber($event, settings.autoTranslateNextChapters)"
                >
                  <fluent-option
                    v-for="option in autoTranslateOptions"
                    :key="option.value"
                    :value="String(option.value)"
                  >
                    {{ option.label }}
                  </fluent-option>
                </fluent-select>
                <small>会自动把当前章和后续设定章数加入翻译队列。</small>
              </label>

              <label class="form-field">
                <span>下载线程数</span>
                <fluent-number-field
                  :value="String(settings.downloadConcurrency)"
                  min="1"
                  max="8"
                  step="1"
                  appearance="outline"
                  @input="settings.downloadConcurrency = eventNumber($event, settings.downloadConcurrency)"
                ></fluent-number-field>
                <small>建议设置 2-5；过高并发可能触发目标站点限流。</small>
              </label>

              <div class="status-note flush">
                <strong>Bika 漫画凭证</strong>
                <p>用于抓取 bikawebapp.com 对应的漫画目录和章节图片；留空时会在首次抓取时自动创建并登录本地账户。</p>
              </div>

              <label class="form-field">
                <span>Bika 账号</span>
                <fluent-text-field
                  :value="settings.bika.email"
                  placeholder="留空则自动创建，或输入已有邮箱/用户名"
                  type="text"
                  appearance="outline"
                  @input="settings.bika.email = eventValue($event)"
                ></fluent-text-field>
              </label>

              <label class="form-field">
                <span>Bika 密码</span>
                <fluent-text-field
                  :value="settings.bika.password"
                  placeholder="留空则自动创建，或输入已有账户密码"
                  type="password"
                  appearance="outline"
                  @input="settings.bika.password = eventValue($event)"
                ></fluent-text-field>
              </label>

              <label class="form-field settings-system-prompt">
                <span>系统提示词</span>
                <fluent-text-area
                  :value="settings.systemPrompt"
                  rows="6"
                  appearance="outline"
                  @input="settings.systemPrompt = eventValue($event)"
                ></fluent-text-area>
              </label>
            </div>

            <div class="settings-footer">
              <div class="status-note flush">
                <strong>后端状态</strong>
                <p>{{ desktopState }}</p>
              </div>

              <fluent-button
                class="primary-btn"
                :disabled="savingSettings"
                @click="handleSaveSettings"
              >
                {{ savingSettings ? '保存中...' : '保存设置' }}
              </fluent-button>
            </div>
          </section>
        </section>
      </template>

      <template v-else-if="currentView === 'detail' && selectedBook && selectedPresentation">
        <section class="detail-view">
          <section class="detail-hero detail-hero--atelier">
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
              <fluent-button
                class="cover-upload-trigger"
                type="button"
                :disabled="coverUploading"
                @click="triggerCoverUpload"
              >
                {{ coverUploading ? '上传中...' : '更换封面' }}
              </fluent-button>
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
                  <strong>{{ selectedPresentation.contentCountText }}</strong>
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
                  <fluent-button
                    class="primary-btn"
                    :disabled="!chapters.length"
                    @click="handleContinueReading"
                  >
                    ▶ {{ continueReadingLabel }}
                  </fluent-button>
                  <small>{{ continueReadingDescription }}</small>
                </div>
                <fluent-button
                  class="ghost-btn anchor-btn"
                  :disabled="!selectedBook.sourceUrl"
                  @click="handleOpenExternal(selectedBook.sourceUrl, '原帖')"
                >
                  ↗ 访问原帖
                </fluent-button>
                <div class="export-menu">
                  <fluent-button
                    class="ghost-btn"
                    :disabled="!chapters.length || exportingFormat !== null"
                    @click="toggleExportMenu"
                  >
                    {{ exportingFormat ? `${exportingFormat.toUpperCase()} 导出中...` : exportMenuOpen ? '收起导出' : '导出' }}
                  </fluent-button>
                  <div
                    v-if="exportMenuOpen"
                    class="export-submenu"
                  >
                    <fluent-button
                      class="ghost-btn compact"
                      :disabled="exportingFormat !== null"
                      @click="handleExportBook('txt')"
                    >
                      TXT 文本
                    </fluent-button>
                    <fluent-button
                      class="ghost-btn compact"
                      :disabled="exportingFormat !== null"
                      @click="handleExportBook('epub')"
                    >
                      EPUB 电子书
                    </fluent-button>
                    <span class="export-hint">导出时可自由选择保存位置</span>
                  </div>
                </div>
                <fluent-button
                  class="ghost-btn"
                  :disabled="coverUploading || exportingFormat !== null"
                  @click="triggerCoverUpload"
                >
                  {{ coverUploading ? '封面上传中...' : '自定义封面' }}
                </fluent-button>
                <fluent-button
                  class="danger-btn"
                  :disabled="deletingBook || exportingFormat !== null"
                  @click="handleDeleteSelectedBook"
                >
                  {{ deletingBook ? '删除中...' : '删除书籍' }}
                </fluent-button>
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
                <fluent-button
                  class="text-btn"
                  @click="toggleAllChapters"
                >
                  {{ allChaptersSelected ? '取消全选' : '全选' }}
                </fluent-button>
                <fluent-button
                  class="primary-btn soft"
                  :disabled="!chapters.length"
                  @click="handleReadSelectedChapter"
                >
                  阅读当前章
                </fluent-button>
                <fluent-button
                  class="ghost-btn compact"
                  :disabled="chapterActionLoading === 'translate' || selectedChapterCount === 0"
                  @click="handleDownloadSelected"
                >
                  {{ chapterActionLoading === 'download' ? '下载中...' : `下载选中 (${selectedChapterCount})` }}
                </fluent-button>
                <fluent-button
                  class="ghost-btn compact"
                  :disabled="chapterActionLoading === 'download' || selectedChapterCount === 0"
                  @click="handleTranslateSelected"
                >
                  {{ chapterActionLoading === 'translate' ? '翻译中...' : `翻译选中 (${selectedChapterCount})` }}
                </fluent-button>
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
              <fluent-button
                class="ghost-btn"
                @click="selectedBookId && openBook(selectedBookId)"
              >
                重新读取
              </fluent-button>
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
                <fluent-checkbox
                  :checked="selectedChapterIndexes.includes(chapter.index)"
                  @click.stop
                  @change="toggleChapterSelection(chapter.index, eventChecked($event))"
                ></fluent-checkbox>
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
                  <fluent-button
                    v-if="task.status === 'failed'"
                    class="ghost-btn compact"
                    :disabled="taskRetryingId === task.id"
                    @click="handleRetryTask(task.id)"
                  >
                    {{ taskRetryingId === task.id ? '重试中...' : '失败重试' }}
                  </fluent-button>
                </div>
              </article>
            </div>
          </section>
        </section>
      </template>

      <template v-else-if="currentView === 'reader' && selectedBook && selectedPresentation">
        <section class="reader-view">
          <header class="reader-topbar">
            <div class="reader-topbar-leading no-drag">
              <fluent-button
                class="text-btn app-header-back"
                @click="backToDetail"
              >
                ‹ 返回详情
              </fluent-button>
            </div>

            <div class="reader-topbar-drag">
              <div class="reader-title">
                <strong>{{ selectedBook.title }}</strong>
                <span>{{ readerChapter?.title || '未选择章节' }}</span>
              </div>
            </div>

            <div class="reader-tools no-drag">
              <fluent-button
                class="ghost-btn compact"
                :disabled="!readerSourceUrl"
                @click="handleOpenExternal(readerSourceUrl, '章节原帖')"
              >
                原帖
              </fluent-button>
              <fluent-button
                class="ghost-btn compact"
                :disabled="!chapters.length"
                @click="readerChapterPickerOpen = !readerChapterPickerOpen"
              >
                {{ readerChapterPickerOpen ? '收起章节' : '章节选择' }}
              </fluent-button>
              <fluent-button
                class="ghost-btn compact"
                :disabled="!translatedReadable"
                @click="toggleReaderMode"
              >
                {{ readerMode === 'translated' ? (isComicBook ? '原图' : '原文') : '译文' }}
              </fluent-button>
              <fluent-button
                class="ghost-btn compact"
                :disabled="!hasPreviousChapter"
                @click="goToAdjacentChapter(-1)"
              >
                {{ isComicBook ? '上一话' : '上一章' }}
              </fluent-button>
              <fluent-button
                class="ghost-btn compact"
                :disabled="!hasNextChapter"
                @click="goToAdjacentChapter(1)"
              >
                {{ isComicBook ? '下一话' : '下一章' }}
              </fluent-button>
              <fluent-button
                class="icon-btn"
                @click="showReaderPanel = !showReaderPanel"
              >
                ⚙
              </fluent-button>
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
                <fluent-button
                  class="ghost-btn compact"
                  @click="readerChapterPickerOpen = false"
                >
                  收起
                </fluent-button>
              </div>
              <div class="reader-chapter-picker-list">
                <button
                  v-for="chapter in chapters"
                  :key="chapter.id"
                  class="reader-chapter-chip"
                  type="button"
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
                <fluent-button
                  class="icon-btn"
                  @click="showReaderPanel = false"
                >
                  ×
                </fluent-button>
              </div>

              <div class="reader-block">
                <span>字体大小</span>
                <div class="segmented">
                  <fluent-button
                    v-for="size in ['小', '中', '大', '特大']"
                    :key="size"
                    :class="{ active: readerFontSize === size }"
                    @click="applyReaderFontSize(size as ReaderFontSize)"
                  >
                    {{ size }}
                  </fluent-button>
                </div>
              </div>

              <div class="reader-block">
                <span>应用主题</span>
                <div class="theme-stack">
                  <fluent-button
                    v-for="theme in themeOptions"
                    :key="theme.key"
                    :class="{ active: readerTheme === theme.key }"
                    @click="applyReaderTheme(theme.key)"
                  >
                    {{ theme.label }}
                    <small v-if="readerTheme === theme.key">当前</small>
                  </fluent-button>
                </div>
              </div>

              <div class="reader-block">
                <div class="reader-color-head">
                  <span>自定义颜色</span>
                  <fluent-button
                    class="text-btn"
                    type="button"
                    @click="resetReaderColors"
                  >
                    恢复主题
                  </fluent-button>
                </div>
                <div class="reader-color-grid">
                  <label class="reader-color-field">
                    <small>字体颜色</small>
                    <div class="reader-color-input">
                      <input
                        ref="readerTextColorInput"
                        class="native-color-input"
                        :value="readerTextColor || '#111827'"
                        type="color"
                        @input="applyReaderTextColor(eventValue($event))"
                      />
                      <fluent-button
                        class="reader-color-swatch"
                        type="button"
                        aria-label="选择字体颜色"
                        @click="triggerReaderTextColorPicker"
                      >
                        <span
                          class="reader-color-chip"
                          :style="{ backgroundColor: readerTextColor || '#111827' }"
                        ></span>
                      </fluent-button>
                      <fluent-text-field
                        :value="readerTextColor"
                        placeholder="跟随主题"
                        type="text"
                        appearance="outline"
                        @input="applyReaderTextColor(eventValue($event))"
                      ></fluent-text-field>
                    </div>
                  </label>
                  <label class="reader-color-field">
                    <small>背景颜色</small>
                    <div class="reader-color-input">
                      <input
                        ref="readerBackgroundColorInput"
                        class="native-color-input"
                        :value="readerBackgroundColor || '#ffffff'"
                        type="color"
                        @input="applyReaderBackgroundColor(eventValue($event))"
                      />
                      <fluent-button
                        class="reader-color-swatch"
                        type="button"
                        aria-label="选择背景颜色"
                        @click="triggerReaderBackgroundColorPicker"
                      >
                        <span
                          class="reader-color-chip"
                          :style="{ backgroundColor: readerBackgroundColor || '#ffffff' }"
                        ></span>
                      </fluent-button>
                      <fluent-text-field
                        :value="readerBackgroundColor"
                        placeholder="跟随主题"
                        type="text"
                        appearance="outline"
                        @input="applyReaderBackgroundColor(eventValue($event))"
                      ></fluent-text-field>
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
        </section>
      </template>
    </section>

    <transition name="scroll-top-fade">
      <fluent-button
        v-if="showBackToTopButton"
        class="scroll-top-btn"
        appearance="stealth"
        type="button"
        title="返回顶部"
        @click="scrollPageToTop"
      >
        <span class="scroll-top-icon" aria-hidden="true" v-html="arrowUpIcon"></span>
      </fluent-button>
    </transition>
  </fluent-design-system-provider>
</template>

