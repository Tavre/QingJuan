from .base import SitePlugin

PLUGIN = SitePlugin(
    id="dmzj",
    name="动漫之家",
    description="使用通用漫画阅读页适配器解析动漫之家公开章节图片。",
    category="manga",
    domains=("dmzj.com",),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "通用适配"),
    preview_handler="generic",
    chapter_handler="generic_manga",
)
