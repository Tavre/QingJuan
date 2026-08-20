from .base import SitePlugin

PLUGIN = SitePlugin(
    id="copymanga",
    name="拷贝漫画 (CopyManga)",
    description="解析拷贝漫画作品、完整分组目录、可取得的章节图片和搜索。",
    category="manga",
    domains=("mangacopy.com", "copymanga.com", "copymanga.site"),
    book_kinds=("漫画",),
    tags=("中文", "漫画", "章节解析"),
    preview_handler="copymanga",
    chapter_handler="copymanga",
    search_handler="copymanga",
    supports_on_demand=True,
)
