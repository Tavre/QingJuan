from .base import SitePlugin

PLUGIN = SitePlugin(
    id="copymanga",
    name="拷贝漫画 (CopyManga)",
    description="通过公开接口解析拷贝漫画作品、分组目录、章节图片和搜索。",
    category="manga",
    domains=("mangacopy.com", "copymanga.com", "copymanga.site"),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "公开接口"),
    preview_handler="copymanga",
    chapter_handler="copymanga",
    search_handler="copymanga",
    supports_on_demand=True,
)
