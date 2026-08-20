from .base import SitePlugin

PLUGIN = SitePlugin(
    id="quark",
    name="夸克小说",
    description="通过书旗网页内核搜索并解析夸克小说作品、目录与匿名免费章节。",
    category="novel",
    domains=("shuqi.com", "novel.quark.cn"),
    book_kinds=("长小说",),
    tags=("中文", "夸克", "匿名公开"),
    preview_handler="quark",
    chapter_handler="quark",
    search_handler="quark",
    supports_on_demand=True,
)
