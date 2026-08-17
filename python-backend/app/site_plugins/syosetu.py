from urllib.parse import urlparse

from .base import SitePlugin, host_matches


def _matches(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host_matches(url, ("syosetu.com",)) and host != "novel18.syosetu.com"


PLUGIN = SitePlugin(
    id="syosetu",
    name="Syosetu",
    description="解析小説家になろう系列的公开作品目录与章节。",
    category="novel",
    domains=("syosetu.com",),
    book_kinds=("长小说",),
    tags=("日文", "网络小说"),
    preview_handler="syosetu",
    chapter_handler="syosetu",
    matcher=_matches,
)
