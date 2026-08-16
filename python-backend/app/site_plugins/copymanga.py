from .base import SitePlugin

PLUGIN = SitePlugin(
    id="copymanga",
    name="CopyManga",
    description="使用通用漫画阅读页适配器解析 CopyManga 公开章节图片。",
    category="manga",
    domains=("copymanga.com", "copymanga.site"),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "通用适配"),
    preview_handler="generic",
    chapter_handler="generic_manga",
)
