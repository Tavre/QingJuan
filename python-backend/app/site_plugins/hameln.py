from .base import SitePlugin

PLUGIN = SitePlugin(
    id="hameln",
    name="Hameln",
    description="解析 Hameln 同人小说作品目录与章节。",
    category="novel",
    domains=("syosetu.org",),
    book_kinds=("长小说",),
    tags=("日文", "同人"),
    preview_handler="hameln",
    chapter_handler="hameln",
)
