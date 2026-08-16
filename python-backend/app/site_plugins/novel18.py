from .base import SitePlugin

PLUGIN = SitePlugin(
    id="novel18",
    name="Novel18",
    description="解析 Novel18 公开作品目录与章节，仅供符合站点年龄要求的用户启用。",
    category="novel",
    domains=("novel18.syosetu.com",),
    book_kinds=("长小说",),
    tags=("日文", "R18"),
    preview_handler="syosetu",
    chapter_handler="syosetu",
)
