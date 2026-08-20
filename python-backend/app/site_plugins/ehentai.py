from .base import SitePlugin

PLUGIN = SitePlugin(
    id="ehentai",
    name="E-Hentai",
    description="解析 E-Hentai 画廊元数据、搜索结果和可取得的画廊原图。",
    category="manga",
    domains=("e-hentai.org", "exhentai.org"),
    book_kinds=("漫画",),
    tags=("漫画", "画廊", "R18"),
    preview_handler="ehentai",
    chapter_handler="ehentai",
    search_handler="ehentai",
)
