from .base import SitePlugin, is_http_url

PLUGIN = SitePlugin(
    id="generic-web",
    name="通用网页",
    description="为没有专用模块的 HTTP/HTTPS 作品链接提供通用目录与正文解析。",
    category="general",
    domains=(),
    book_kinds=("长小说", "轻小说", "漫画"),
    tags=("回退", "通用解析"),
    preview_handler="generic",
    chapter_handler="generic",
    matcher=is_http_url,
)
