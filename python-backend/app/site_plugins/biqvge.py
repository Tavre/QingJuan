from .base import SitePlugin

PLUGIN = SitePlugin(
    id="biqvge",
    name="笔趣阁",
    description="聚合八零小说网、笔趣阁 5200 与笔趣看，支持搜索、上游可取得的作品目录和公开章节正文。",
    category="novel",
    domains=("txt80.net", "b520.cc", "blqukan.cc"),
    book_kinds=("长小说",),
    tags=("中文", "聚合搜索", "章节解析"),
    preview_handler="biqvge",
    chapter_handler="biqvge",
    search_handler="biqvge",
    supports_on_demand=True,
)
