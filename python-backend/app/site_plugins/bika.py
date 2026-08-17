from .base import SitePlugin

PLUGIN = SitePlugin(
    id="bika",
    name="Bika Web App",
    description="解析 Bika Web App 漫画、章节和图片；需要在后端配置站点凭据。",
    category="manga",
    domains=("bikawebapp.com",),
    book_kinds=("漫画",),
    tags=("中文", "漫画"),
    preview_handler="bika",
    chapter_handler="bika",
    search_handler="bika",
)
