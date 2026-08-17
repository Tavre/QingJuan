from .base import SitePlugin

PLUGIN = SitePlugin(
    id="fanqie",
    name="番茄小说",
    description="解析番茄小说作品、搜索与章节正文，支持账号登录和一键导入当前书架。",
    category="novel",
    domains=("fanqienovel.com",),
    book_kinds=("长小说",),
    tags=("中文", "连载", "账号书架"),
    preview_handler="fanqie",
    chapter_handler="fanqie",
    search_handler="fanqie",
    supports_on_demand=True,
    supports_account_login=True,
    supports_cookie_login=True,
    supports_bookshelf_import=True,
    version="1.1.0",
)
