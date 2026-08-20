from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

FANQIE_HOSTS = frozenset({"fanqienovel.com", "www.fanqienovel.com"})
FANQIE_BOOK_PATH_PATTERN = re.compile(r"^/page/(?P<book_id>\d+)/?$")
FANQIE_READER_PATH_PATTERN = re.compile(r"^/reader/(?P<item_id>\d+)/?$")
_INITIAL_STATE_MARKER = "window.__INITIAL_STATE__="
_MAX_INITIAL_STATE_CHARS = 5_000_000
_MAX_CHAPTERS = 20_000
_MIN_COMPLETE_TEXT_RATIO = 0.85
_RESTRICTION_TEXT_MARKERS = (
    "下载番茄小说app继续阅读",
    "本章内容需在番茄小说app内阅读",
    "本章内容暂不支持网页阅读",
    "登录后继续阅读",
    "购买后继续阅读",
    "开通会员后继续阅读",
)

# 番茄网页正文使用私用区字符配合自绘字体显示。映射表改编自
# naiyQAQ/fanqie-assistant 的 src/fontDecrypt.ts（GPL-3.0）：
# https://github.com/naiyQAQ/fanqie-assistant/blob/57f7a8ca8d59e9e3f402b265fb1d078102443881/src/fontDecrypt.ts
# QingJuan 同样以 GPL-3.0 发布；未知映射项保留原字符，避免静默损坏正文。
_FONT_CODEPOINT_START = 58_344
_FONT_MAPPING = (
    "D在主特家军然表场4要只v和?6别还g现儿岁??此象月3出战工相o男直失世F都平文什VO将真T那当?会立些u是十张学气大爱两命全后东性通被1它乐接而感车山公了常"
    "以何可话先pi叫轻M士w着变尔快l个说少色里安花远7难师放t报认面道S?克地度I好机U民写把万同水新没书电吃像斯5为y白几日教看但第加候作上拉住有法r事应位利你"
    "声身国问马女他Y比父xAHNsX边美对所金活回意到z从j知又内因点Q三定8Rb正或夫向德听更?得告并本q过记L让打f人就者去原满体做经K走如孩cG给使物?最笑部"
    "?员等受k行一条果动光门头见往自解成处天能于名其发总母的死手入路进心来h时力多开已许d至由很界n小与Z想代么分生口再妈望次西风种带J?实情才这?E我神格长觉间年"
    "眼无不亲关结0友信下却重己老2音字m呢明之前高PB目太e9起稜她也W用方子英每理便四数期中C外样a海们任"
)


class FanqieParseError(ValueError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"番茄小说{stage}解析失败：{message}")
        self.stage = stage


@dataclass(frozen=True)
class FanqieChapter:
    item_id: str
    title: str
    url: str
    order: int
    volume_name: str
    is_locked: bool


@dataclass(frozen=True)
class FanqieBook:
    book_id: str
    title: str
    author: str | None
    synopsis: str
    cover_url: str | None
    total_chapter_count: int
    chapters: tuple[FanqieChapter, ...]

@dataclass(frozen=True)
class FanqieReaderChapter:
    item_id: str
    book_id: str
    title: str
    text: str
    image_urls: tuple[str, ...]
    content_source: str
    authorization_method: str
    access_restricted: bool
    declared_word_count: int


def is_fanqie_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme.lower() in {"http", "https"} and (parsed.hostname or "").lower() in FANQIE_HOSTS


def fanqie_book_id_from_url(url: str) -> str | None:
    if not is_fanqie_url(url):
        return None
    match = FANQIE_BOOK_PATH_PATTERN.fullmatch(urlparse(url).path)
    return match.group("book_id") if match else None


def fanqie_item_id_from_url(url: str) -> str | None:
    if not is_fanqie_url(url):
        return None
    match = FANQIE_READER_PATH_PATTERN.fullmatch(urlparse(url).path)
    return match.group("item_id") if match else None


def canonical_fanqie_book_url(book_id: str) -> str:
    if not book_id.isdigit():
        raise FanqieParseError("链接", "作品编号无效")
    return f"https://fanqienovel.com/page/{book_id}"


def decode_fanqie_text(text: str) -> str:
    decoded: list[str] = []
    for character in text:
        mapping_index = ord(character) - _FONT_CODEPOINT_START
        if 0 <= mapping_index < len(_FONT_MAPPING):
            mapped = _FONT_MAPPING[mapping_index]
            decoded.append(character if mapped == "?" else mapped)
        else:
            decoded.append(character)
    return "".join(decoded)


def _extract_balanced_object(source: str, start: int) -> str:
    if start >= len(source) or source[start] != "{":
        raise FanqieParseError("页面状态", "__INITIAL_STATE__ 不是对象")

    depth = 0
    quote = ""
    escaped = False
    for index in range(start, min(len(source), start + _MAX_INITIAL_STATE_CHARS)):
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise FanqieParseError("页面状态", "__INITIAL_STATE__ 超长或结构不完整")


def _replace_javascript_literals(source: str) -> str:
    replacements = {"undefined": "null", "NaN": "null", "Infinity": "null"}
    output: list[str] = []
    index = 0
    quote = ""
    escaped = False
    while index < len(source):
        character = source[index]
        if quote:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = ""
            index += 1
            continue
        if character == '"':
            quote = character
            output.append(character)
            index += 1
            continue
        replaced = False
        for literal, replacement in replacements.items():
            if not source.startswith(literal, index):
                continue
            before = source[index - 1] if index else ""
            after_index = index + len(literal)
            after = source[after_index] if after_index < len(source) else ""
            if (not before or not (before.isalnum() or before in "_$")) and (
                not after or not (after.isalnum() or after in "_$")
            ):
                output.append(replacement)
                index = after_index
                replaced = True
                break
        if not replaced:
            output.append(character)
            index += 1
    return "".join(output)


def _initial_state_from_html(html: str) -> dict[str, Any]:
    marker_index = html.find(_INITIAL_STATE_MARKER)
    if marker_index < 0:
        raise FanqieParseError("页面状态", "缺少 __INITIAL_STATE__")
    object_start = html.find("{", marker_index + len(_INITIAL_STATE_MARKER))
    if object_start < 0:
        raise FanqieParseError("页面状态", "缺少状态对象")
    raw_state = _extract_balanced_object(html, object_start)
    try:
        state = json.loads(_replace_javascript_literals(raw_state))
    except json.JSONDecodeError as exc:
        raise FanqieParseError("页面状态", f"状态 JSON 无效（位置 {exc.pos}）") from exc
    if not isinstance(state, dict):
        raise FanqieParseError("页面状态", "状态根节点类型异常")
    return state


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_restricted_chapter(chapter: dict[str, Any]) -> bool:
    return bool(
        chapter.get("isChapterLock")
        or chapter.get("isPaidPublication")
        or chapter.get("isPaidStory")
        or _integer(chapter.get("needPay")) != 0
    )


def _declared_word_count(chapter: dict[str, Any]) -> int:
    for key in ("chapterWordNumber", "chapter_word_number", "wordCount", "wordNumber"):
        value = _integer(chapter.get(key))
        if value > 0:
            return value
    return 0


def _visible_character_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _has_restriction_message(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text).lower()
    return any(marker in normalized for marker in _RESTRICTION_TEXT_MARKERS)


def _validate_reader_content(
    *,
    text: str,
    image_urls: tuple[str, ...],
    declared_word_count: int,
) -> None:
    if not text and not image_urls:
        raise FanqieParseError("章节正文", "网页没有返回可用正文")

    visible_count = _visible_character_count(text)
    if _has_restriction_message(text):
        raise FanqieParseError("章节正文", "网页仍要求登录、购买或开通会员")

    if declared_word_count > 0:
        minimum_complete_count = max(1, int(declared_word_count * _MIN_COMPLETE_TEXT_RATIO))
        if visible_count < minimum_complete_count:
            raise FanqieParseError(
                "章节正文",
                f"网页只返回了试读片段（正文 {visible_count} 字，章节声明 {declared_word_count} 字）",
            )
        return

def _chapter_items(page: dict[str, Any]) -> list[dict[str, Any]]:
    groups = page.get("chapterListWithVolume")
    if not isinstance(groups, list):
        raise FanqieParseError("目录", "缺少 chapterListWithVolume")
    items: list[dict[str, Any]] = []
    for group in groups:
        if isinstance(group, list):
            items.extend(item for item in group if isinstance(item, dict))
            continue
        if not isinstance(group, dict):
            continue
        for key in ("chapterList", "chapters", "items"):
            nested = group.get(key)
            if isinstance(nested, list):
                items.extend(item for item in nested if isinstance(item, dict))
                break
    if not items:
        raise FanqieParseError("目录", "没有找到章节")
    if len(items) > _MAX_CHAPTERS:
        raise FanqieParseError("目录", f"章节数量超过安全上限 {_MAX_CHAPTERS}")
    return items


def parse_fanqie_book_page(html: str, source_url: str) -> FanqieBook:
    expected_book_id = fanqie_book_id_from_url(source_url)
    if not expected_book_id:
        raise FanqieParseError("链接", "请使用 https://fanqienovel.com/page/作品编号 格式")

    page = _mapping(_initial_state_from_html(html).get("page"))
    book_id = str(page.get("bookId") or "").strip()
    if book_id != expected_book_id:
        raise FanqieParseError("作品信息", "页面作品编号与链接不一致")
    title = str(page.get("bookName") or "").strip()
    if not title:
        raise FanqieParseError("作品信息", "缺少书名")

    origin = "https://fanqienovel.com"
    chapters: list[FanqieChapter] = []
    seen_item_ids: set[str] = set()
    for position, item in enumerate(_chapter_items(page), start=1):
        item_id = str(item.get("itemId") or "").strip()
        chapter_title = str(item.get("title") or "").strip()
        if not item_id.isdigit() or not chapter_title or item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        order = _integer(item.get("realChapterOrder"), position)
        if order <= 0:
            order = position
        chapters.append(
            FanqieChapter(
                item_id=item_id,
                title=chapter_title[:180],
                url=f"{origin}/reader/{item_id}",
                order=order,
                volume_name=str(item.get("volume_name") or "").strip()[:180],
                is_locked=_is_restricted_chapter(item),
            )
        )
    if not chapters:
        raise FanqieParseError("目录", "章节条目均无效")
    chapters.sort(key=lambda chapter: (chapter.order, chapter.item_id))

    cover = str(page.get("thumbUrl") or page.get("thumbUri") or "").strip()
    if cover and urlparse(cover).scheme.lower() not in {"http", "https"}:
        cover = ""
    total = _integer(page.get("chapterTotal"), len(chapters))
    return FanqieBook(
        book_id=book_id,
        title=title,
        author=str(page.get("authorName") or page.get("author") or "").strip() or None,
        synopsis=str(page.get("abstract") or page.get("description") or "").strip(),
        cover_url=cover or None,
        total_chapter_count=max(total, len(chapters)),
        chapters=tuple(chapters),
    )


def _reader_text_and_images(content: str, base_url: str) -> tuple[str, tuple[str, ...]]:
    soup = BeautifulSoup(content, "html.parser")
    for node in soup.select("script, style, noscript"):
        node.decompose()
    blocks = [decode_fanqie_text(node.get_text(" ", strip=True)) for node in soup.select("p")]
    text = "\n\n".join(block for block in blocks if block).strip()
    if not text:
        text = decode_fanqie_text(soup.get_text("\n", strip=True))

    image_urls: list[str] = []
    for image in soup.select("img"):
        candidate = str(image.get("data-src") or image.get("src") or "").strip()
        if not candidate or candidate.startswith("{{"):
            continue
        absolute = urljoin(base_url, candidate)
        if urlparse(absolute).scheme.lower() in {"http", "https"} and absolute not in image_urls:
            image_urls.append(absolute)
    return text, tuple(image_urls)


def parse_fanqie_chapter_content(
    *,
    item_id: str,
    book_id: str,
    title: str,
    content: str,
    source_url: str,
    access_restricted: bool = False,
    declared_word_count: int = 0,
    content_source: str = "web_initial_state",
    authorization_method: str = "public_web",
) -> FanqieReaderChapter:
    """解析已取得的番茄章节 HTML。

    网页 SSR 和 APP 全文接口返回的正文格式相同，统一在这里做字体解码、
    图片提取以及完整性校验，避免不同入口产生不一致的章节结果。
    """
    normalized_item_id = str(item_id or "").strip()
    if not normalized_item_id.isdigit():
        raise FanqieParseError("章节信息", "章节编号无效")
    text, image_urls = _reader_text_and_images(str(content or ""), source_url)
    _validate_reader_content(
        text=text,
        image_urls=image_urls,
        declared_word_count=max(0, int(declared_word_count or 0)),
    )
    return FanqieReaderChapter(
        item_id=normalized_item_id,
        book_id=str(book_id or "").strip(),
        title=str(title or "").strip() or f"章节 {normalized_item_id}",
        text=text,
        image_urls=image_urls,
        content_source=content_source,
        authorization_method=authorization_method,
        access_restricted=access_restricted,
        declared_word_count=max(0, int(declared_word_count or 0)),
    )


def parse_fanqie_reader_page(html: str, source_url: str) -> FanqieReaderChapter:
    expected_item_id = fanqie_item_id_from_url(source_url)
    if not expected_item_id:
        raise FanqieParseError("链接", "章节链接格式无效")
    reader = _mapping(_initial_state_from_html(html).get("reader"))
    chapter = _mapping(reader.get("chapterData"))
    item_id = str(chapter.get("itemId") or chapter.get("groupId") or "").strip()
    if item_id != expected_item_id:
        raise FanqieParseError("章节信息", "页面章节编号与链接不一致")

    access_restricted = _is_restricted_chapter(chapter)
    declared_word_count = _declared_word_count(chapter)
    return parse_fanqie_chapter_content(
        item_id=item_id,
        book_id=str(chapter.get("bookId") or "").strip(),
        title=str(chapter.get("title") or "").strip(),
        content=str(chapter.get("content") or ""),
        source_url=source_url,
        access_restricted=access_restricted,
        declared_word_count=declared_word_count,
        content_source="web_initial_state",
        authorization_method="public_web",
    )
