from .base import SitePlugin

PLUGIN = SitePlugin(
    id="alphapolis",
    name="Alphapolis",
    description="解析 Alphapolis 小说作品目录与章节正文。",
    category="novel",
    domains=("alphapolis.co.jp",),
    book_kinds=("长小说",),
    tags=("日文", "小说"),
    preview_handler="alphapolis",
    chapter_handler="alphapolis",
)
