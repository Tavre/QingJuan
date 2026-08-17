from urllib.parse import urlparse

from .base import SitePlugin, host_matches


def _matches(url: str) -> bool:
    return host_matches(url, ("pixiv.net",)) and (urlparse(url).hostname or "").lower() != "comic.pixiv.net"


PLUGIN = SitePlugin(
    id="pixiv",
    name="Pixiv",
    description="解析 Pixiv 小说、小说系列和多页插画作品。",
    category="novel",
    domains=("pixiv.net",),
    book_kinds=("长小说", "漫画"),
    tags=("日文", "小说", "插画"),
    preview_handler="pixiv",
    chapter_handler="pixiv",
    matcher=_matches,
)
