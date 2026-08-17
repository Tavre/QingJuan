from .base import SitePlugin

PLUGIN = SitePlugin(
    id="kakuyomu",
    name="Kakuyomu",
    description="解析 Kakuyomu 作品、目录与章节，并提供内置作品搜索。",
    category="novel",
    domains=("kakuyomu.jp",),
    book_kinds=("轻小说", "长小说"),
    tags=("日文", "连载"),
    preview_handler="kakuyomu",
    chapter_handler="kakuyomu",
    search_handler="kakuyomu",
)
