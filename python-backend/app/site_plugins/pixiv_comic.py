from .base import SitePlugin

PLUGIN = SitePlugin(
    id="pixiv-comic",
    name="Pixiv Comic",
    description="解析 Pixiv Comic 作品、公开章节与页面下发的漫画图片。",
    category="manga",
    domains=("comic.pixiv.net",),
    book_kinds=("漫画",),
    tags=("日文", "漫画"),
    preview_handler="pixiv_comic",
    chapter_handler="pixiv_comic",
)
