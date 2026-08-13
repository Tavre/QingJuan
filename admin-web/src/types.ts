export type SessionInfo = {
  authenticated: true;
  expiresAt: string;
  csrfToken: string;
  csrfHeader: string;
};

export type ServiceMeta = {
  service: "qingjuan-backend";
  appVersion: string;
  apiVersion: string;
  instanceId: string;
  capabilities: Record<string, boolean>;
};

export type DevicePlatform = "android" | "windows" | "linux" | "macos" | "ios" | "other";

export type Device = {
  id: string;
  name: string;
  platform: DevicePlatform;
  ipAddress: string;
  firstSeenAt: string;
  lastSeenAt: string;
  banned: boolean;
  bannedAt: string | null;
  online: boolean;
};

export type ConnectionTokenStatus = {
  configured: boolean;
  revealAvailable: boolean;
  maskedToken: string | null;
  fingerprint: string | null;
};

export type RuntimeLogLevel = "debug" | "info" | "warning" | "error" | "critical";

export type RuntimeLog = {
  timestamp: string;
  level: RuntimeLogLevel;
  source: string;
  message: string;
};

export type RuntimeLogBatch = {
  items: RuntimeLog[];
  sources: string[];
  total: number;
};

export type DiagnosticStatus = "healthy" | "warning" | "error";

export type TranslationModelCheck = {
  enabled: boolean;
  configured: boolean;
  available: boolean;
  status: "ready" | "disabled" | "unconfigured" | "failed";
  model: string | null;
  supportsVision: boolean;
  checkedAt: string;
  latencyMs: number | null;
  message: string;
  cached: boolean;
};

export type ServiceDiagnostics = {
  schemaVersion: number;
  status: DiagnosticStatus;
  generatedAt: string;
  startedAt: string;
  uptimeSeconds: number;
  runtime: {
    pythonVersion: string;
    operatingSystem: string;
    architecture: string;
  };
  requests: {
    total: number;
    successful: number;
    clientErrors: number;
    serverErrors: number;
    averageDurationMs: number;
    p95DurationMs: number;
    sampleSize: number;
  };
  storage: {
    totalBytes: number;
    usedBytes: number;
    freeBytes: number;
    databaseBytes: number;
    runtimeLogsBytes: number;
  };
  workload: {
    books: number;
    tasks: number;
    queuedTasks: number;
    runningTasks: number;
    failedTasks: number;
    pendingQueueItems: number;
    devices: number;
    onlineDevices: number;
  };
  checks: Array<{
    key: string;
    label: string;
    status: DiagnosticStatus;
    detail: string;
  }>;
  recentIssues: Array<{
    timestamp: string;
    level: "warning" | "error" | "critical";
    source: string;
    message: string;
  }>;
};

export type Book = {
  id: string;
  title: string;
  sourceUrl: string;
  bookKind: "长小说" | "轻小说" | "漫画";
  language: "中文" | "英文" | "日文";
  status: "待处理" | "解析中" | "已下载" | "已完成";
  chapterCount: number;
  translated: boolean;
  updatedAt: string;
  synopsis: string;
  cover: string | null;
  lastReadChapterIndex: number;
  lastReadAt: string | null;
};

export type TaskStatus = "queued" | "running" | "completed" | "failed";

export type Task = {
  id: string;
  bookId: string;
  taskType: "download" | "translate";
  chapterIndexes: number[];
  status: TaskStatus;
  totalCount: number;
  completedCount: number;
  progress: number;
  message: string;
  error: string | null;
  attempts: number;
  createdAt: string;
  updatedAt: string;
};

export type TaskLog = {
  sequence: number;
  taskId: string;
  level: "info" | "warning" | "error";
  message: string;
  createdAt: string;
};

export type BookSource = {
  id: string;
  name: string;
  baseUrl: string;
  description: string;
  bookKind: Book["bookKind"] | null;
  language: Book["language"] | null;
  enabled: boolean;
  supported: boolean;
  sampleUrl: string | null;
  tags: string[];
  origin: "builtin" | "manual" | "imported";
  status: "unknown" | "online" | "slow" | "offline" | "unsupported";
  statusMessage: string;
  lastCheckedAt: string | null;
  createdAt: string;
};

export type Settings = {
  systemPrompt: string;
  autoTranslateNextChapters: number;
  downloadConcurrency: number;
  translationModel: {
    enabled: boolean;
    baseUrl: string;
    model: string;
    supportsVision: boolean;
    apiKeyConfigured: boolean;
  };
  mangaOcr: {
    enabled: boolean;
    baseUrl: string;
    apiKeyConfigured: boolean;
  };
  bika: {
    emailConfigured: boolean;
    passwordConfigured: boolean;
  };
};

export type SettingsUpdate = {
  systemPrompt: string;
  autoTranslateNextChapters: number;
  downloadConcurrency: number;
  translationModel: {
    enabled: boolean;
    baseUrl: string;
    apiKey: string;
    model: string;
    supportsVision: boolean;
    apiKeyAction: "keep" | "replace" | "clear";
  };
  mangaOcr: {
    enabled: boolean;
    baseUrl: string;
    apiKey: string;
    apiKeyAction: "keep" | "replace" | "clear";
  };
  bika: {
    email: string;
    password: string;
    passwordAction: "keep";
  };
};

export type DashboardData = {
  meta: ServiceMeta;
  connectionToken: ConnectionTokenStatus;
  devices: Device[];
  books: Book[];
  tasks: Task[];
  sources: BookSource[];
  settings: Settings;
};
