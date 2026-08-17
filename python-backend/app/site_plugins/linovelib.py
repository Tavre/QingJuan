from .base import SitePlugin

PLUGIN = SitePlugin(
    id="linovelib",
    name="Linovelib",
    description="解析 Linovelib 与 Bilinovel 作品目录、分卷和插图章节。",
    category="novel",
    domains=("linovelib.com", "bilinovel.com"),
    book_kinds=("轻小说",),
    tags=("轻小说", "插图"),
    preview_handler="generic",
    chapter_handler="linovelib",
)
