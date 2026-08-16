from .base import SitePlugin

PLUGIN = SitePlugin(
    id="qidian",
    name="起点中文网",
    description="解析起点作品与公开章节，支持扫码登录并一键导入当前账号书架。",
    category="novel",
    domains=("qidian.com",),
    book_kinds=("长小说", "轻小说"),
    tags=("中文", "账号书架"),
    preview_handler="qidian",
    chapter_handler="qidian",
    supports_on_demand=True,
    supports_account_login=True,
    supports_bookshelf_import=True,
)
