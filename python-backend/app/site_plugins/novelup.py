from .base import SitePlugin

PLUGIN = SitePlugin(
    id="novelup",
    name="Novelup",
    description="解析 Novelup 作品目录；站点保护变化时会返回明确诊断。",
    category="novel",
    domains=("novelup.plus",),
    book_kinds=("长小说",),
    tags=("日文", "投稿"),
    preview_handler="novelup",
    chapter_handler="novelup",
)
