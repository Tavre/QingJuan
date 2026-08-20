from .base import SitePlugin

PLUGIN = SitePlugin(
    id="comicores",
    name="COMICORES 漫核",
    description="解析 COMICORES 公开作品元数据和搜索；登录或付费下载资源不接入。",
    category="manga",
    domains=("comicores.cc",),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "公开元数据"),
    preview_handler="comicores",
    chapter_handler=None,
    search_handler="comicores",
)
