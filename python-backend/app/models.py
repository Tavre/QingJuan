from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

BookKind = Literal["长小说", "轻小说", "漫画"]
Language = Literal["中文", "英文", "日文"]
TranslationProvider = Literal["openai", "newapi", "anthropic", "grok2api", "custom"]
TaskType = Literal["download", "translate"]
TaskStatus = Literal["queued", "running", "completed", "failed"]
TaskLogLevel = Literal["info", "warning", "error"]


class AddBookPayload(BaseModel):
    sourceUrl: HttpUrl
    bookKind: BookKind
    title: str | None = None
    language: Language
    needTranslation: bool = False


class ChapterPreview(BaseModel):
    title: str
    url: str
    pageCount: int = 0


class PreviewResponse(BaseModel):
    title: str
    author: str | None = None
    synopsis: str = ""
    cover: str | None = None
    chapterCount: int
    chapters: list[ChapterPreview]
    bookKind: BookKind = "轻小说"


class BookRecord(BaseModel):
    id: str
    title: str
    sourceUrl: str
    bookKind: BookKind
    language: Language
    status: Literal["待处理", "解析中", "已下载", "已完成"]
    chapterCount: int
    translated: bool
    localPath: str
    updatedAt: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    synopsis: str = ""
    cover: str | None = None
    lastReadChapterIndex: int = 0
    lastReadAt: str | None = None


class ChapterRecord(BaseModel):
    id: str
    index: int
    title: str
    fileName: str
    wordCount: int
    downloaded: bool = True
    translated: bool = False
    sourceUrl: str | None = None
    illustration: bool = False
    imageCount: int = 0
    imageUrls: list[str] = []
    imageFiles: list[str] = []
    translatedImageFiles: list[str] = []
    pageCount: int = 0


class ReadingProgressRecord(BaseModel):
    bookId: str
    lastChapterIndex: int = 0
    lastScrollRatio: float = 0
    lastAnchorType: Literal["top", "paragraph", "image"] = "top"
    lastAnchorIndex: int = 0
    lastAnchorOffsetRatio: float = 0
    lastReadAt: str | None = None


class ReadingProgressPayload(BaseModel):
    chapterIndex: int
    scrollRatio: float = 0
    anchorType: Literal["top", "paragraph", "image"] = "top"
    anchorIndex: int = 0
    anchorOffsetRatio: float = 0


class ChapterActionPayload(BaseModel):
    chapterIndexes: list[int] = Field(min_length=1)


class BookExportPayload(BaseModel):
    format: Literal["txt", "epub"]
    targetPath: str | None = None


class BookExportResponse(BaseModel):
    bookId: str
    format: Literal["txt", "epub"]
    fileName: str
    filePath: str
    downloadUrl: str
    chapterCount: int


class TaskRecord(BaseModel):
    id: str
    bookId: str
    taskType: TaskType
    chapterIndexes: list[int]
    status: TaskStatus
    totalCount: int
    completedCount: int = 0
    progress: float = 0
    message: str = ""
    error: str | None = None
    attempts: int = 0
    createdAt: str
    updatedAt: str


class TaskLogRecord(BaseModel):
    sequence: int
    taskId: str
    level: TaskLogLevel = "info"
    message: str
    createdAt: str


class BookDetailResponse(BaseModel):
    book: BookRecord
    title: str
    author: str | None = None
    synopsis: str = ""
    addedAt: str
    totalWords: int
    downloadedChapterCount: int
    translatedChapterCount: int
    progress: ReadingProgressRecord
    chapters: list[ChapterRecord]


class ChapterContentResponse(BaseModel):
    bookId: str
    chapter: ChapterRecord
    content: str
    paragraphs: list[str]
    mode: Literal["original", "translated"] = "original"
    translatedAvailable: bool = False
    imageSources: list[str] = []
    pageTranslations: list[str] = []


class ProviderConfig(BaseModel):
    enabled: bool = False
    baseUrl: str = ""
    apiKey: str = ""
    model: str = ""


class ComicSourceConfig(BaseModel):
    email: str = ""
    password: str = ""


class TranslationSettings(BaseModel):
    defaultProvider: TranslationProvider = "openai"
    systemPrompt: str = """你是一位专业的文学翻译家，精通中英文互译，擅长小说、散文等文学作品的翻译。
## 翻译原则
1. **忠实原文**：准确传达原文的意思，不随意增删内容
2. **流畅自然**：译文符合目标语言的表达习惯，读起来流畅，不生硬
3. **保留风格**：保持原著的文学风格、叙事节奏和作者语气（幽默、严肃、诗意等）
4. **文化转化**：对文化特有词汇、俚语、典故进行适当的本地化处理，必要时加注说明
## 翻译要求
- 人名、地名首次出现时保留原文并附译名
- 对话翻译要符合人物性格，体现说话人的身份和语气
- 保留原文段落结构，不随意合并或拆分段落
- 专有名词（魔法、功夫、宗教等体系术语）保持统一，不前后矛盾
## 输出格式
直接输出译文，无需解释翻译过程。
如遇歧义或难以处理的表达，在译文后用【译注】标注说明。
## 翻译方向
    [中译英 / 英译中]"""
    autoTranslateNextChapters: int = 0
    downloadConcurrency: int = Field(default=3, ge=1, le=8)
    providers: dict[TranslationProvider, ProviderConfig]
    bika: ComicSourceConfig = Field(default_factory=ComicSourceConfig)
