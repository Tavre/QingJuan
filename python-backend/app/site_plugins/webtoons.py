from .base import SitePlugin

PLUGIN = SitePlugin(
    id="webtoons",
    name="Webtoons",
    description="使用通用漫画阅读页适配器解析 Webtoons 公开章节图片。",
    category="manga",
    domains=("webtoons.com",),
    book_kinds=("漫画",),
    tags=("漫画", "通用适配"),
    preview_handler="generic",
    chapter_handler="generic_manga",
)
