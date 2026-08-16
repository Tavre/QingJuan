from .base import SitePlugin

PLUGIN = SitePlugin(
    id="18comic",
    name="18Comic",
    description="解析 18Comic 专辑、章节和漫画图片，并提供内置作品搜索。",
    category="manga",
    domains=("18comic.vip",),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "R18"),
    preview_handler="18comic",
    chapter_handler="18comic",
    search_handler="18comic",
)
