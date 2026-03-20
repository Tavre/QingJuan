import type { BookRecord, PreviewResponse, TranslationSettings } from '../types';

export const mockBooks: BookRecord[] = [
  {
    id: 'book-001',
    title: '全职高手',
    sourceUrl: 'https://example.com/novel/the-kings-avatar',
    bookKind: '长小说',
    language: '中文',
    status: '已下载',
    chapterCount: 1728,
    translated: false,
    localPath: '文库/中文/全职高手',
    updatedAt: '2026-03-18 00:20',
    synopsis: '网游荣耀中被誉为教科书级别的顶尖高手叶修，在离开职业舞台后重新踏上属于自己的征程。',
    lastReadChapterIndex: 245,
    lastReadAt: '2026-03-18 00:20',
  },
  {
    id: 'book-002',
    title: 'Re: 从零开始的异世界生活',
    sourceUrl: 'https://example.com/novel/re-zero',
    bookKind: '轻小说',
    language: '日文',
    status: '已完成',
    chapterCount: 156,
    translated: true,
    localPath: '文库/日文/ReZero',
    updatedAt: '2026-03-17 19:42',
    synopsis: '死亡回归与命运循环交织的异世界轻小说，适合展示抓取后翻译的工作流。',
    lastReadChapterIndex: 89,
    lastReadAt: '2026-03-17 19:42',
  },
  {
    id: 'book-003',
    title: 'The Lord of the Rings',
    sourceUrl: 'https://example.com/novel/lotr',
    bookKind: '长小说',
    language: '英文',
    status: '已下载',
    chapterCount: 62,
    translated: false,
    localPath: '文库/英文/TheLordOfTheRings',
    updatedAt: '2026-03-16 16:32',
    synopsis: '经典奇幻长篇，适合作为英文原站抓取和多章节归档的演示素材。',
    lastReadChapterIndex: 12,
    lastReadAt: '2026-03-16 16:32',
  },
  {
    id: 'book-004',
    title: '诡秘之主',
    sourceUrl: 'https://example.com/novel/lord-of-mysteries',
    bookKind: '长小说',
    language: '中文',
    status: '已完成',
    translated: true,
    chapterCount: 1394,
    localPath: '文库/中文/诡秘之主',
    updatedAt: '2026-03-15 09:30',
    synopsis: '蒸汽与神秘交织的序列之路，章节体量大，适合验证下载管理与本地阅读体验。',
    lastReadChapterIndex: 567,
    lastReadAt: '2026-03-15 09:30',
  },
];

export const mockPreview: PreviewResponse = {
  title: 'Moonlit Registry',
  author: 'A. Sterling',
  synopsis: '一本从废弃图书馆延展出的奇异调查小说，适合作为英文站点解析演示。',
  chapterCount: 12,
  chapters: Array.from({ length: 12 }, (_, index) => ({
    title: `Chapter ${index + 1}`,
    url: `https://example.com/moonlit-registry/${index + 1}`,
  })),
};

export const defaultSettings: TranslationSettings = {
  defaultProvider: 'openai',
  autoTranslateNextChapters: 0,
  downloadConcurrency: 3,
  systemPrompt: `你是一位专业的文学翻译家，精通中英文互译，擅长小说、散文等文学作品的翻译。
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
[中译英 / 英译中]`,
  providers: {
    openai: {
      enabled: true,
      baseUrl: 'https://api.openai.com/v1',
      apiKey: '',
      model: 'gpt-4.1-mini',
    },
    newapi: {
      enabled: false,
      baseUrl: 'https://your-newapi-endpoint/v1',
      apiKey: '',
      model: 'gpt-4.1-mini',
    },
    anthropic: {
      enabled: false,
      baseUrl: 'https://api.anthropic.com/v1',
      apiKey: '',
      model: 'claude-3-7-sonnet-latest',
    },
    custom: {
      enabled: false,
      baseUrl: 'https://localhost:8001/v1',
      apiKey: '',
      model: 'custom-model',
    },
  },
};
