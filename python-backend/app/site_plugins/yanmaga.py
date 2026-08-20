from .base import SitePlugin

PLUGIN = SitePlugin(
    id="yanmaga",
    name="Yanmaga",
    description="解析 Yanmaga 作品与匿名公开章节，并复原官方 Viewer 下发的漫画页面。",
    category="manga",
    domains=("yanmaga.jp",),
    book_kinds=("漫画",),
    tags=("日文", "漫画", "公开章节"),
    preview_handler="yanmaga",
    chapter_handler="yanmaga",
)
