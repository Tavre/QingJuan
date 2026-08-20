from .base import SitePlugin

PLUGIN = SitePlugin(
    id="comicores",
    name="COMICORES 漫核",
    description="解析 COMICORES 作品元数据和搜索；当前解析器尚未实现章节资源解析。",
    category="manga",
    domains=("comicores.cc",),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "公开元数据"),
    preview_handler="comicores",
    chapter_handler=None,
    search_handler="comicores",
)
