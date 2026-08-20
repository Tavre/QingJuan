from .base import SitePlugin

PLUGIN = SitePlugin(
    id="sfacg",
    name="SF 轻小说",
    description="解析菠萝包/SF 轻小说作品、完整分卷目录、可取得的章节正文和搜索。",
    category="novel",
    domains=("sfacg.com",),
    book_kinds=("轻小说",),
    tags=("中文", "轻小说", "菠萝包"),
    preview_handler="sfacg",
    chapter_handler="sfacg",
    search_handler="sfacg",
)
