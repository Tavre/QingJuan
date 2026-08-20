from .base import SitePlugin

PLUGIN = SitePlugin(
    id="ciweimao",
    name="刺猬猫阅读",
    description="解析刺猬猫作品、分卷目录与可取得的章节正文，并提供作品搜索。",
    category="novel",
    domains=("ciweimao.com",),
    book_kinds=("轻小说",),
    tags=("中文", "轻小说", "章节解析"),
    preview_handler="ciweimao",
    chapter_handler="ciweimao",
    search_handler="ciweimao",
)
