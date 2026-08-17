from __future__ import annotations

import html
import json
import math
import re
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

YANMAGA_ORIGIN = "https://yanmaga.jp"
YANMAGA_VIEWER_ORIGIN = "https://yanmaga.jp/viewer"
YANMAGA_CONTENT_HOSTS = frozenset({"sbc.yanmaga.jp"})

_SPEEDBINB_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_SPEEDBINB_VALUES = {character: index for index, character in enumerate(_SPEEDBINB_ALPHABET)}
_SPEEDBINB_F_KEY = re.compile(r"^=(\d+)-(\d+)([-+])(\d+)-([-_0-9A-Za-z]+)$")


class YanmagaParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class YanmagaEpisode:
    id: str
    title: str
    url: str
    publicly_readable: bool
    restriction: str | None = None


@dataclass(frozen=True, slots=True)
class YanmagaBookPage:
    book_path: str
    title: str
    author: str | None
    synopsis: str
    cover: str | None
    episode_count: int
    episodes: tuple[YanmagaEpisode, ...]
    next_path: str | None
    next_offset: int | None


def yanmaga_resource_from_url(url: str) -> tuple[str, str | None] | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme.lower() not in {"http", "https"} or host != "yanmaga.jp":
        return None
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) not in {2, 3} or parts[0] != "comics":
        return None
    book_path = parts[1].strip()
    if not book_path or book_path in {"authors", "series"}:
        return None
    episode_id = parts[2].strip() if len(parts) == 3 else None
    return book_path, episode_id or None


def canonical_yanmaga_url(book_path: str, episode_id: str | None = None) -> str:
    url = f"{YANMAGA_ORIGIN}/comics/{quote(book_path, safe='')}"
    if episode_id:
        url += f"/{quote(episode_id, safe='')}"
    return url


def parse_yanmaga_book_page(html_text: str, source_url: str) -> YanmagaBookPage:
    resource = yanmaga_resource_from_url(source_url)
    if resource is None or resource[1] is not None:
        raise YanmagaParseError("Yanmaga 仅支持 /comics/作品路径 形式的作品页")
    book_path = resource[0]
    soup = BeautifulSoup(html_text, "html.parser")
    title_node = soup.select_one("h1.detailv2-outline-title")
    if title_node is None:
        raise YanmagaParseError("Yanmaga 作品页缺少作品信息，页面结构可能已变化")

    authors = [node.get_text(" ", strip=True) for node in soup.select("ul.detailv2-outline-author a")]
    authors = [item for item in authors if item]
    synopsis_node = soup.select_one("p.detailv2-description")
    cover_node = soup.select_one(".detailv2-thumbnail-image img")
    cover = None
    if cover_node is not None:
        raw_cover = str(cover_node.get("data-src") or cover_node.get("src") or "").strip()
        cover = urljoin(source_url, raw_cover) if raw_cover else None

    count_node = soup.select_one("#contents")
    try:
        episode_count = max(0, int(count_node.get("data-count") or 0)) if count_node else 0
    except (TypeError, ValueError):
        episode_count = 0

    first_list = soup.select_one("ul.mod-episode-list")
    episode_nodes = first_list.select(":scope > li.mod-episode-item") if first_list else []
    if not episode_nodes:
        episode_nodes = soup.select("li.mod-episode-item")
    episodes = _parse_yanmaga_episode_nodes(episode_nodes, book_path)

    more = soup.select_one("button.mod-episode-more-button")
    next_path = str(more.get("data-path") or "").strip() or None if more else None
    try:
        next_offset = int(more.get("data-offset")) if more and more.get("data-offset") is not None else None
    except (TypeError, ValueError):
        next_offset = None

    return YanmagaBookPage(
        book_path=book_path,
        title=title_node.get_text(" ", strip=True),
        author="、".join(authors) or None,
        synopsis=synopsis_node.get_text(" ", strip=True) if synopsis_node else "",
        cover=cover,
        episode_count=episode_count,
        episodes=tuple(episodes),
        next_path=next_path,
        next_offset=next_offset,
    )


def parse_yanmaga_episode_fragment(fragment: str, book_path: str) -> tuple[YanmagaEpisode, ...]:
    decoded = html.unescape(
        fragment.replace('\\"', '"').replace("\\/", "/").replace("\\n", "\n").replace("\\'", "'")
    )
    soup = BeautifulSoup(decoded, "html.parser")
    return tuple(_parse_yanmaga_episode_nodes(soup.select("li.mod-episode-item"), book_path))


def _parse_yanmaga_episode_nodes(nodes: list[Any], book_path: str) -> list[YanmagaEpisode]:
    episodes: list[YanmagaEpisode] = []
    seen: set[str] = set()
    for node in nodes:
        anchor = node.select_one("a.mod-episode-link[href], a[href]")
        raw_url = str(node.get("data-original-url") or (anchor.get("href") if anchor else "") or "").strip()
        episode_id = raw_url.rstrip("/").split("/")[-1].strip()
        title = str(node.get("data-episode-title") or "").strip()
        if not title and anchor is not None:
            title = anchor.get_text(" ", strip=True)
        if not episode_id or not title or episode_id in seen:
            continue

        is_free = str(node.get("data-is-free") or "").lower() == "true"
        free_node = node.select_one(".mod-episode-point--free")
        free_label = free_node.get_text(" ", strip=True) if free_node else ""
        publicly_readable = free_label == "無料" or (is_free and "初回" not in free_label)
        restriction = None
        if not publicly_readable:
            if "初回" in free_label:
                restriction = "该章节属于登录账号单次免费内容"
            elif node.get("data-modal"):
                restriction = "该章节需要注册、登录或点数"
            else:
                restriction = "该章节当前未对匿名访问公开"

        seen.add(episode_id)
        episodes.append(
            YanmagaEpisode(
                id=episode_id,
                title=title[:180],
                url=canonical_yanmaga_url(book_path, episode_id),
                publicly_readable=publicly_readable,
                restriction=restriction,
            )
        )
    return episodes


def speedbinb_request_key(content_id: str, now_milliseconds: int | None = None) -> str:
    if not content_id:
        raise YanmagaParseError("Yanmaga Viewer 缺少内容编号")
    now_hex = format(now_milliseconds or int(time.time() * 1000), "x").rjust(16, "x")[:16]
    repeated = content_id * math.ceil(16 / len(content_id))
    first = repeated[:16]
    last = repeated[-16:]
    left = middle = right = 0
    output: list[str] = []
    for index, character in enumerate(now_hex):
        left ^= ord(character)
        middle ^= ord(first[index])
        right ^= ord(last[index])
        output.append(character + _SPEEDBINB_ALPHABET[(left + middle + right) & 63])
    return "".join(output)


def decode_speedbinb_table(content_id: str, key: str, encrypted: str) -> list[str]:
    seed = 0
    for index, character in enumerate(f"{content_id}:{key}"):
        seed += ord(character) << (index % 16)
    seed &= 2_147_483_647
    state = seed or 305_419_896
    output: list[str] = []
    for character in encrypted:
        state = (state >> 1) ^ (1_210_056_708 & -(state & 1))
        output.append(chr((ord(character) - 32 + state) % 94 + 32))
    try:
        decoded = json.loads("".join(output))
    except json.JSONDecodeError as exc:
        raise YanmagaParseError("Yanmaga Viewer 置换表解析失败") from exc
    if not isinstance(decoded, list) or len(decoded) < 8 or not all(isinstance(item, str) for item in decoded):
        raise YanmagaParseError("Yanmaga Viewer 返回了无效置换表")
    return decoded


def speedbinb_page_keys(source: str, content_table: list[str], position_table: list[str]) -> tuple[str, str]:
    indexes = [0, 0]
    filename = source.rsplit("/", 1)[-1]
    for index, character in enumerate(filename):
        indexes[index % 2] += ord(character)
    return position_table[indexes[0] % 8], content_table[indexes[1] % 8]


def descramble_yanmaga_image(image_bytes: bytes, position_key: str, content_key: str) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            source = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise YanmagaParseError("Yanmaga 页面图片不是有效图像") from exc

    coordinates, output_width, output_height = _speedbinb_coordinates(
        position_key,
        content_key,
        source.width,
        source.height,
    )
    restored = Image.new("RGB", (output_width, output_height))
    for item in coordinates:
        box = (
            item["xsrc"],
            item["ysrc"],
            item["xsrc"] + item["width"],
            item["ysrc"] + item["height"],
        )
        restored.paste(source.crop(box), (item["xdest"], item["ydest"]))
    output = BytesIO()
    restored.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _parse_speedbinb_f_key(key: str) -> dict[str, Any] | None:
    match = _SPEEDBINB_F_KEY.match(key)
    if not match:
        return None
    columns = int(match.group(1))
    rows = int(match.group(2))
    margin = int(match.group(4))
    payload = match.group(5)
    if columns > 8 or rows > 8 or columns * rows > 64:
        return None
    if len(payload) != columns + rows + columns * rows:
        return None
    try:
        column_map = [_SPEEDBINB_VALUES[payload[index]] for index in range(columns)]
        row_map = [_SPEEDBINB_VALUES[payload[columns + index]] for index in range(rows)]
        cell_map = [
            _SPEEDBINB_VALUES[payload[columns + rows + index]]
            for index in range(columns * rows)
        ]
    except KeyError:
        return None
    return {
        "columns": columns,
        "rows": rows,
        "sign": match.group(3),
        "margin": margin,
        "column_map": column_map,
        "row_map": row_map,
        "cell_map": cell_map,
    }


def _speedbinb_coordinates(
    position_key: str,
    content_key: str,
    width: int,
    height: int,
) -> tuple[list[dict[str, int]], int, int]:
    content = _parse_speedbinb_f_key(content_key)
    position = _parse_speedbinb_f_key(position_key)
    if content is None or position is None:
        raise YanmagaParseError("Yanmaga 页面置换键格式不受支持")
    if content["sign"] == "-" and position["sign"] == "+":
        content, position = position, content
    if content["sign"] != "+" or position["sign"] != "-":
        raise YanmagaParseError("Yanmaga 页面置换键方向无效")
    if content["columns"] != position["columns"] or content["rows"] != position["rows"]:
        raise YanmagaParseError("Yanmaga 页面置换键尺寸不一致")

    columns = content["columns"]
    rows = content["rows"]
    margin = content["margin"]
    edge_x = 2 * columns * margin
    edge_y = 2 * rows * margin
    if width < 64 + edge_x or height < 64 + edge_y or width * height < (320 + edge_x) * (320 + edge_y):
        return [
            {
                "xsrc": 0,
                "ysrc": 0,
                "width": width,
                "height": height,
                "xdest": 0,
                "ydest": 0,
            }
        ], width, height

    cropped_width = width - edge_x
    cropped_height = height - edge_y
    cell_width = (cropped_width + columns - 1) // columns
    last_width = cropped_width - (columns - 1) * cell_width
    cell_height = (cropped_height + rows - 1) // rows
    last_height = cropped_height - (rows - 1) * cell_height

    content_rows = content["row_map"]
    content_columns = content["column_map"]
    position_rows = position["row_map"]
    position_columns = position["column_map"]
    mapping = [
        content["cell_map"][position["cell_map"][index]]
        for index in range(columns * rows)
    ]

    coordinates: list[dict[str, int]] = []
    for index in range(columns * rows):
        source_column = index % columns
        source_row = index // columns
        target_column = mapping[index] % columns
        target_row = mapping[index] // columns
        coordinates.append(
            {
                "xsrc": margin
                + source_column * (cell_width + 2 * margin)
                + (last_width - cell_width if position_rows[source_row] < source_column else 0),
                "ysrc": margin
                + source_row * (cell_height + 2 * margin)
                + (last_height - cell_height if position_columns[source_column] < source_row else 0),
                "width": last_width if position_rows[source_row] == source_column else cell_width,
                "height": last_height if position_columns[source_column] == source_row else cell_height,
                "xdest": target_column * cell_width
                + (last_width - cell_width if content_rows[target_row] < target_column else 0),
                "ydest": target_row * cell_height
                + (last_height - cell_height if content_columns[target_column] < target_row else 0),
            }
        )
    return coordinates, cropped_width, cropped_height
