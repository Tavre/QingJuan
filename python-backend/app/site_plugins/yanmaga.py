from .base import SitePlugin

PLUGIN = SitePlugin(
    id="yanmaga",
    name="Yanmaga",
    description="解析 Yanmaga 作品与完整目录，并在官方 Viewer 返回内容时复原漫画页面。",
    category="manga",
    domains=("yanmaga.jp",),
    book_kinds=("漫画",),
    tags=("日文", "漫画", "章节解析"),
    preview_handler="yanmaga",
    chapter_handler="yanmaga",
)
