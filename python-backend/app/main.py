from __future__ import annotations

import argparse
import ast

# QingJuan
# Author: Tavre
# License: GPL-3.0-only
import asyncio
import copy
import html
import ipaddress
import json
import mimetypes
import os
import re
import shutil
import sys
import unicodedata
import warnings
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4

import httpx
import uvicorn
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image, UnidentifiedImageError

# 部分书源返回 XML/RSS，统一用 html.parser 解析时 bs4 会刷 XMLParsedAsHTMLWarning。
# 解析结果不受影响，这里屏蔽该告警避免污染日志。
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

try:
    from .api.routers import (
        API_ROUTERS,
        PUBLIC_ROUTERS,
        health_router,
        library_router,
        settings_router,
        sources_router,
        system_router,
        tasks_router,
    )
    from .application import create_application
    from .db import (
        DATA_DIR,
        append_task_log,
        create_task,
        delete_book,
        get_book,
        get_book_source,
        get_task,
        init_db,
        list_book_sources,
        list_books,
        list_builtin_book_source_base_urls,
        list_pending_tasks,
        list_task_logs,
        list_tasks,
        load_reading_progress,
        load_settings,
        save_book,
        save_book_source,
        save_reading_progress,
        save_settings,
        save_task,
    )
    from .link_jobs import LinkJobStore
    from .local_import import (
        LOCAL_FILE_SIZE_LIMITS,
        SUPPORTED_LOCAL_EXTENSIONS,
        LocalImportError,
        inspect_local_document,
        write_local_document,
    )
    from .models import (
        AddBookPayload,
        BookDetailResponse,
        BookExportPayload,
        BookExportResponse,
        BookRecord,
        BookSourceImportResult,
        BookSourceRecord,
        BookSourceSearchPayload,
        BookSourceSearchResult,
        BookSourceTextImportPayload,
        BookSourceUrlImportPayload,
        BuiltinSiteSearchPayload,
        BuiltinSiteSearchResult,
        ChapterActionPayload,
        ChapterContentResponse,
        ChapterExportPayload,
        ChapterExportResponse,
        ChapterRecord,
        LinkJobRecord,
        LinkJobStartPayload,
        PreviewResponse,
        PublicBookRecord,
        PublicBookSourceRecord,
        PublicLinkJobRecord,
        ReadingProgressPayload,
        ReadingProgressRecord,
        ServiceMetaResponse,
        TaskLogRecord,
        TaskPageResultRecord,
        TaskPageTextRecord,
        TaskRecord,
        TranslationSettings,
        TranslationSettingsView,
    )
    from .process_lifecycle import start_parent_process_watcher
    from .scraper import (
        _fetch_with_edge_cdp,
        _normalize_search_text,
        _normalize_source_url,
        build_translated_filename,
        create_book_manifest_only,
        download_book,
        download_selected_chapters,
        load_manga_translation_page_payloads,
        load_manifest,
        load_translated_page_payload,
        preview_from_url,
        repair_18comic_chapter_images,
        save_manifest,
        search_builtin_site_books,
        translate_selected_chapters,
        translate_single_manga_image,
        translated_image_payload_is_current,
    )
    from .security import API_PREFIX, API_VERSION, authentication_enabled
except ImportError:
    from app.api.routers import (
        API_ROUTERS,
        PUBLIC_ROUTERS,
        health_router,
        library_router,
        settings_router,
        sources_router,
        system_router,
        tasks_router,
    )
    from app.application import create_application
    from app.db import (
        DATA_DIR,
        append_task_log,
        create_task,
        delete_book,
        get_book,
        get_book_source,
        get_task,
        init_db,
        list_book_sources,
        list_books,
        list_builtin_book_source_base_urls,
        list_pending_tasks,
        list_task_logs,
        list_tasks,
        load_reading_progress,
        load_settings,
        save_book,
        save_book_source,
        save_reading_progress,
        save_settings,
        save_task,
    )
    from app.link_jobs import LinkJobStore
    from app.local_import import (
        LOCAL_FILE_SIZE_LIMITS,
        SUPPORTED_LOCAL_EXTENSIONS,
        LocalImportError,
        inspect_local_document,
        write_local_document,
    )
    from app.models import (
        AddBookPayload,
        BookDetailResponse,
        BookExportPayload,
        BookExportResponse,
        BookRecord,
        BookSourceImportResult,
        BookSourceRecord,
        BookSourceSearchPayload,
        BookSourceSearchResult,
        BookSourceTextImportPayload,
        BookSourceUrlImportPayload,
        BuiltinSiteSearchPayload,
        BuiltinSiteSearchResult,
        ChapterActionPayload,
        ChapterContentResponse,
        ChapterExportPayload,
        ChapterExportResponse,
        ChapterRecord,
        LinkJobRecord,
        LinkJobStartPayload,
        PreviewResponse,
        PublicBookRecord,
        PublicBookSourceRecord,
        PublicLinkJobRecord,
        ReadingProgressPayload,
        ReadingProgressRecord,
        ServiceMetaResponse,
        TaskLogRecord,
        TaskPageResultRecord,
        TaskPageTextRecord,
        TaskRecord,
        TranslationSettings,
        TranslationSettingsView,
    )
    from app.process_lifecycle import start_parent_process_watcher
    from app.scraper import (
        _fetch_with_edge_cdp,
        _normalize_search_text,
        _normalize_source_url,
        build_translated_filename,
        create_book_manifest_only,
        download_book,
        download_selected_chapters,
        load_manga_translation_page_payloads,
        load_manifest,
        load_translated_page_payload,
        preview_from_url,
        repair_18comic_chapter_images,
        save_manifest,
        search_builtin_site_books,
        translate_selected_chapters,
        translate_single_manga_image,
        translated_image_payload_is_current,
    )
    from app.security import API_PREFIX, API_VERSION, authentication_enabled

LIBRARY_ROOT = DATA_DIR / "library"
EXPORT_ROOT = DATA_DIR / "exports"
EXPORT_TTL = timedelta(hours=24)
TASK_QUEUE: asyncio.Queue[str] = asyncio.Queue()
LINK_JOB_STORE = LinkJobStore()
SOURCE_CHAPTER_CACHE_AHEAD = 20
SOURCE_IMPORT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}
SOURCE_IMPORT_TIMEOUT = 60.0
SOURCE_IMPORT_CONNECT_TIMEOUT = 10.0
SOURCE_IMPORT_JSON_KEYS = ("data", "bookSources", "sources", "items", "list", "result")
SOURCE_IMPORT_JSONP_NAME_PATTERN = re.compile(r"^[\w$.]+$")
LEGADO_SEARCH_DEFAULT_PAGE = "1"
# 书源体量通常上千、且多数站点失效或较慢，旧参数（并发 12 / 总超时 5s）在 5 秒内
# 只能实际查询二三十个源，命中率约 3%，导致“搜索热门书也无结果”。放宽并发与超时
# 窗口后可覆盖数百个源；配合命中后的落定窗口在拿到首批结果后再多等几秒收集更多。
LEGADO_SEARCH_CONCURRENCY = 48
LEGADO_SEARCH_SOURCE_TIMEOUT = 4.0
LEGADO_SEARCH_CONNECT_TIMEOUT = 2.0
LEGADO_SEARCH_TOTAL_TIMEOUT = 18.0
LEGADO_SEARCH_RESULT_SETTLE_TIMEOUT = 4.0


async def _run_startup(app_instance: FastAPI) -> None:
    init_db()
    _migrate_book_storage_keys()
    await asyncio.to_thread(_cleanup_expired_exports)
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    app_instance.state.deleted_book_ids = set()
    app_instance.state.export_cleanup_worker = asyncio.create_task(_export_cleanup_loop())
    app_instance.state.reader_cache_tasks = set()
    app_instance.state.reader_cache_keys = set()
    app_instance.state.reader_cache_locks = {}
    app_instance.state.link_job_tasks = set()
    for task in list_pending_tasks():
        task.status = "queued"
        task.message = "等待队列处理"
        task.error = None
        task.updatedAt = _now()
        save_task(task)
        TASK_QUEUE.put_nowait(task.id)
    app_instance.state.queue_worker = asyncio.create_task(_task_worker())


async def _run_shutdown(app_instance: FastAPI) -> None:
    export_cleanup_worker = getattr(app_instance.state, "export_cleanup_worker", None)
    if export_cleanup_worker is not None:
        export_cleanup_worker.cancel()
        with suppress(asyncio.CancelledError):
            await export_cleanup_worker

    link_job_tasks = getattr(app_instance.state, "link_job_tasks", set())
    if isinstance(link_job_tasks, set):
        for task in list(link_job_tasks):
            task.cancel()
        await asyncio.gather(*link_job_tasks, return_exceptions=True)
        link_job_tasks.clear()

    reader_cache_tasks = getattr(app_instance.state, "reader_cache_tasks", set())
    if isinstance(reader_cache_tasks, set):
        for task in list(reader_cache_tasks):
            task.cancel()
        await asyncio.gather(*reader_cache_tasks, return_exceptions=True)
        reader_cache_tasks.clear()

    worker = getattr(app_instance.state, "queue_worker", None)
    if worker is not None:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


@asynccontextmanager
async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    await _run_startup(app_instance)
    try:
        yield
    finally:
        await _run_shutdown(app_instance)


@health_router.get("/healthz")
@health_router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


@system_router.get("/meta", response_model=ServiceMetaResponse)
async def get_service_meta() -> ServiceMetaResponse:
    return ServiceMetaResponse(
        service="qingjuan-backend",
        appVersion=app.version,
        apiVersion=API_VERSION,
        instanceId=_load_or_create_instance_id(),
        capabilities={
            "rapidOcr": True,
            "windowsOcr": os.name == "nt",
            "browserFallback": _browser_fallback_available(),
        },
    )


@sources_router.get("/sources", response_model=list[PublicBookSourceRecord])
async def get_sources() -> list[BookSourceRecord]:
    return list_book_sources()


@sources_router.post("/sources/search", response_model=list[BookSourceSearchResult])
async def post_source_search(payload: BookSourceSearchPayload) -> list[BookSourceSearchResult]:
    keyword = payload.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空")

    source_ids = {source_id.strip() for source_id in payload.sourceIds if source_id.strip()}
    sources = [
        source
        for source in list_book_sources()
        if source.enabled and (not source_ids or source.id in source_ids)
    ]
    if not sources:
        raise HTTPException(status_code=400, detail="请先导入并启用 Legado 书源")

    searchable_sources = [source for source in sources if _source_has_search_rule(source)]
    if not searchable_sources:
        raise HTTPException(
            status_code=400,
            detail="当前没有可搜索的 Legado 书源，请重新导入包含 searchUrl 与 ruleSearch 的书源",
        )

    per_source_limit = max(
        1, min(payload.limit, max(4, payload.limit // max(1, len(searchable_sources)) + 2))
    )
    search_keywords = _fuzzy_source_search_keywords(keyword)
    results: list[BookSourceSearchResult] = []
    for search_keyword in search_keywords:
        results = await _search_legado_sources(
            searchable_sources, search_keyword, per_source_limit, payload.limit
        )
        if results:
            break
    return _rank_source_search_results(_dedupe_source_search_results(results), keyword)[: payload.limit]


@sources_router.post("/sources/search-stream")
async def post_source_search_stream(payload: BookSourceSearchPayload, request: Request) -> StreamingResponse:
    """流式搜索：边搜边出。每个书源返回即刻推送结果，客户端可随时断开以停止。

    采用 NDJSON（按行的 JSON）协议，逐行推送以下事件：
    - {"type":"meta","total":N}                 搜索开始，共 N 个可搜索书源
    - {"type":"result","data":{...}}            命中一条结果（去重后）
    - {"type":"progress","done":k,"total":N,...} 已完成 k 个书源
    - {"type":"done","results":m,...}           搜索自然结束
    """
    keyword = payload.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空")

    source_ids = {source_id.strip() for source_id in payload.sourceIds if source_id.strip()}
    sources = [
        source
        for source in list_book_sources()
        if source.enabled and (not source_ids or source.id in source_ids)
    ]
    if not sources:
        raise HTTPException(status_code=400, detail="请先导入并启用 Legado 书源")

    searchable_sources = [source for source in sources if _source_has_search_rule(source)]
    if not searchable_sources:
        raise HTTPException(
            status_code=400,
            detail="当前没有可搜索的 Legado 书源，请重新导入包含 searchUrl 与 ruleSearch 的书源",
        )

    generator = _stream_legado_search(request, searchable_sources, keyword, payload.limit)
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(generator, media_type="application/x-ndjson", headers=headers)


def _ndjson_line(event: dict[str, object]) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


async def _stream_legado_search(
    request: Request,
    sources: list[BookSourceRecord],
    keyword: str,
    total_limit: int,
) -> AsyncIterator[bytes]:
    per_source_limit = max(1, min(total_limit, max(4, total_limit // max(1, len(sources)) + 2)))
    keywords = _fuzzy_source_search_keywords(keyword)
    search_keyword = keywords[0] if keywords else keyword
    semaphore = asyncio.Semaphore(LEGADO_SEARCH_CONCURRENCY)
    queue: asyncio.Queue[tuple[str, list[BookSourceSearchResult]]] = asyncio.Queue()

    async def worker(source: BookSourceRecord) -> None:
        async with semaphore:
            try:
                source_results = await _search_legado_source(source, search_keyword, per_source_limit)
            except Exception:
                source_results = []
            await queue.put(("result", source_results))

    workers = [asyncio.create_task(worker(source)) for source in sources]

    async def watch_completion() -> None:
        await asyncio.gather(*workers, return_exceptions=True)
        await queue.put(("__done__", []))

    completion_task = asyncio.create_task(watch_completion())

    seen_urls: set[str] = set()
    emitted = 0
    done_count = 0
    total = len(sources)

    try:
        yield _ndjson_line({"type": "meta", "total": total})
        while True:
            try:
                kind, source_results = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                # 队列空闲时探测客户端是否已断开（用户点了停止 / 离开页面）。
                if await request.is_disconnected():
                    break
                continue

            if kind == "__done__":
                break

            done_count += 1
            reached_limit = False
            for result in source_results:
                if result.sourceUrl in seen_urls:
                    continue
                seen_urls.add(result.sourceUrl)
                emitted += 1
                yield _ndjson_line({"type": "result", "data": result.model_dump(mode="json")})
                if emitted >= total_limit:
                    reached_limit = True
                    break

            yield _ndjson_line({"type": "progress", "done": done_count, "total": total, "results": emitted})
            if reached_limit:
                break

        yield _ndjson_line({"type": "done", "results": emitted, "done": done_count, "total": total})
    finally:
        # 客户端断开或自然结束都要回收并发请求，避免后台残留搜索任务。
        for task in workers:
            task.cancel()
        completion_task.cancel()
        await asyncio.gather(*workers, completion_task, return_exceptions=True)


@sources_router.post("/builtin-sites/search", response_model=list[BuiltinSiteSearchResult])
async def post_builtin_site_search(payload: BuiltinSiteSearchPayload) -> list[BuiltinSiteSearchResult]:
    source = _get_source_or_404(payload.sourceId)
    keyword = payload.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="搜索关键词不能为空")
    try:
        return await search_builtin_site_books(source, keyword, payload.limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"内置站点作品搜索失败：{exc}") from exc


@sources_router.post("/sources/import-url", response_model=BookSourceImportResult)
async def post_source_import_url(payload: BookSourceUrlImportPayload) -> BookSourceImportResult:
    try:
        content = await _fetch_book_source_import_payload(str(payload.url))
        return _import_book_sources(content, import_url=str(payload.url))
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=400, detail=f"无法获取远程书源：{exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@sources_router.post("/sources/import-text", response_model=BookSourceImportResult)
async def post_source_import_text(payload: BookSourceTextImportPayload) -> BookSourceImportResult:
    try:
        return _import_book_sources(payload.content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@sources_router.put("/sources/{source_id}", response_model=PublicBookSourceRecord)
async def put_source(source_id: str, payload: BookSourceRecord) -> BookSourceRecord:
    current = _get_source_or_404(source_id)
    if current.origin == "builtin":
        raise HTTPException(status_code=400, detail="内置书源不支持手动修改")
    updated = payload.model_copy(
        update={
            "id": current.id,
            "createdAt": current.createdAt,
            "updatedAt": _now(),
        }
    )
    return save_book_source(updated)


@library_router.get("/books", response_model=list[PublicBookRecord])
async def get_books() -> list[BookRecord]:
    books: list[BookRecord] = []
    for book in list_books():
        books.append(await _hydrate_book_record_async(book))
    return books


@tasks_router.get("/tasks", response_model=list[TaskRecord])
async def get_tasks() -> list[TaskRecord]:
    return list_tasks()


@library_router.get("/books/{book_id}", response_model=BookDetailResponse)
async def get_book_detail(book_id: str) -> BookDetailResponse:
    return _build_book_detail(
        await _hydrate_book_record_async(_get_book_or_404(book_id), fetch_remote_metadata=True)
    )


@library_router.delete("/books/{book_id}")
async def delete_book_route(book_id: str) -> dict[str, str]:
    book = _get_book_or_404(book_id)
    book_dir = _resolve_book_dir(book)
    deleted_book_ids: set[str] = getattr(app.state, "deleted_book_ids", set())
    deleted_book_ids.add(book.id)
    app.state.deleted_book_ids = deleted_book_ids
    delete_book(book.id)
    if book_dir.exists():
        shutil.rmtree(book_dir, ignore_errors=True)
    return {"status": "ok", "bookId": book.id}


@library_router.get("/books/{book_id}/chapters/{chapter_index}", response_model=ChapterContentResponse)
async def get_chapter_content(
    book_id: str,
    chapter_index: int,
    mode: str = Query(default="translated"),
) -> ChapterContentResponse:
    book = _get_book_or_404(book_id)
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    try:
        manifest = await _ensure_source_chapter_cached(book, book_dir, manifest, chapter_index)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"章节缓存失败：{exc}") from exc
    with suppress(Exception):
        repair_18comic_chapter_images(book_dir, manifest, chapter_index)
    chapter, chapter_path = _load_single_chapter(book, chapter_index, mode)
    content = chapter_path.read_text(encoding="utf-8")
    is_translated_mode = chapter_path.name.endswith(".translated.txt")
    page_translations = load_translated_page_payload(book_dir, chapter.fileName) if is_translated_mode else []
    translated_images_current = (
        translated_image_payload_is_current(book_dir, chapter.fileName) if is_translated_mode else False
    )
    translated_image_assets = [
        asset_path for asset_path in chapter.translatedImageFiles if (book_dir / asset_path).exists()
    ]
    image_assets = (
        translated_image_assets
        if is_translated_mode and translated_images_current and translated_image_assets
        else chapter.imageFiles
    )

    response = ChapterContentResponse(
        bookId=book.id,
        chapter=chapter,
        content=content,
        paragraphs=_split_paragraphs(content),
        mode="translated" if is_translated_mode else "original",
        translatedAvailable=_translated_path_for_chapter(book_dir, chapter).exists(),
        imageSources=[_build_book_asset_url(book.id, asset_path) for asset_path in image_assets],
        pageTranslations=page_translations,
    )
    _schedule_source_chapter_cache_ahead(book, book_dir, manifest, chapter_index)
    return response


@library_router.get("/books/{book_id}/assets/{asset_path:path}")
async def get_book_asset(book_id: str, asset_path: str) -> FileResponse:
    book = _get_book_or_404(book_id)
    book_dir = _resolve_book_dir(book).resolve()
    target_path = (book_dir / asset_path).resolve()
    if not target_path.is_relative_to(book_dir):
        raise HTTPException(status_code=400, detail="非法资源路径")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"资源不存在：{asset_path}")

    media_type = _guess_asset_media_type(target_path)
    return FileResponse(target_path, media_type=media_type or "application/octet-stream")


@library_router.post("/books/{book_id}/export", response_model=BookExportResponse)
async def post_book_export(book_id: str, payload: BookExportPayload) -> BookExportResponse:
    book = _get_book_or_404(book_id)
    export_path, chapter_count, file_count = _export_book(
        book,
        payload.format,
        payload.chapterIndexes,
    )
    file_name = _book_export_file_name(book, payload.format)
    return BookExportResponse(
        bookId=book.id,
        format=payload.format,
        artifactId=export_path.stem,
        fileName=file_name,
        downloadUrl=_build_export_download_url(book.id, export_path.stem),
        contentType=_export_content_type(export_path),
        sizeBytes=export_path.stat().st_size,
        expiresAt=_artifact_expiry(export_path),
        chapterCount=chapter_count,
        fileCount=file_count,
    )


@library_router.post(
    "/books/{book_id}/chapters/{chapter_index}/export",
    response_model=ChapterExportResponse,
)
async def post_chapter_export(
    book_id: str,
    chapter_index: int,
    payload: ChapterExportPayload,
) -> ChapterExportResponse:
    book = _get_book_or_404(book_id)
    export_path, file_count = _export_chapter(
        book,
        chapter_index=chapter_index,
        export_format=payload.format,
    )
    chapter = _load_chapter_export_item(book, chapter_index)[1]["chapter"]
    return ChapterExportResponse(
        bookId=book.id,
        chapterIndex=chapter_index,
        format=payload.format,
        artifactId=export_path.stem,
        fileName=_chapter_export_file_name(chapter, payload.format),
        downloadUrl=_build_export_download_url(book.id, export_path.stem),
        contentType=_export_content_type(export_path),
        sizeBytes=export_path.stat().st_size,
        expiresAt=_artifact_expiry(export_path),
        fileCount=file_count,
    )


@library_router.get("/books/{book_id}/exports/{artifact_id}")
async def get_book_export(book_id: str, artifact_id: str) -> FileResponse:
    _get_book_or_404(book_id)
    export_dir = (EXPORT_ROOT / book_id).resolve()
    if not re.fullmatch(r"[0-9a-f]{32}", artifact_id):
        raise HTTPException(status_code=400, detail="非法导出产物 ID")
    matches = [path for path in export_dir.glob(f"{artifact_id}.*") if path.is_file()]
    target_path = matches[0].resolve() if len(matches) == 1 else export_dir / "missing"
    if not target_path.is_relative_to(export_dir):
        raise HTTPException(status_code=400, detail="非法导出产物路径")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="导出产物不存在或已过期")
    if datetime.now(UTC) - datetime.fromtimestamp(target_path.stat().st_mtime, UTC) > EXPORT_TTL:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="导出产物不存在或已过期")
    return FileResponse(target_path, media_type=_export_content_type(target_path))


@library_router.post("/books/{book_id}/cover", response_model=PublicBookRecord)
async def post_book_cover(book_id: str, file: Annotated[UploadFile, File()]) -> BookRecord:
    try:
        book = _get_book_or_404(book_id)
        book_dir = _resolve_book_dir(book)
        if not book_dir.exists():
            raise HTTPException(status_code=404, detail="书籍目录不存在，无法保存封面")

        original_name = _normalize_form_text(file.filename or "").strip()
        extension = _validate_cover_extension(original_name, file.content_type)
        target_dir = book_dir / "covers"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"custom-cover{extension}"

        previous_manifest = _load_or_initialize_manifest(book, book_dir)
        previous_cover_file = _read_optional_string(previous_manifest, "cover_file")
        if previous_cover_file:
            previous_path = (book_dir / previous_cover_file).resolve()
            if (
                previous_path.exists()
                and previous_path.is_file()
                and previous_path.parent == target_dir.resolve()
                and previous_path != target_path.resolve()
            ):
                previous_path.unlink(missing_ok=True)

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="封面文件为空")
        target_path.write_bytes(content)

        manifest = _load_or_initialize_manifest(book, book_dir)
        manifest["cover_file"] = f"covers/{target_path.name}"
        manifest["cover_url"] = None
        save_manifest(book_dir, manifest)

        updated_book = book.model_copy(update={"updatedAt": _now()})
        save_book(updated_book)
        return _hydrate_book_record(updated_book)
    finally:
        await file.close()


@library_router.post("/images/translate")
async def post_translate_image(
    file: Annotated[UploadFile, File()],
    language: Annotated[str, Form()],
    title: Annotated[str, Form()] = "",
) -> Response:
    try:
        normalized_language = _validate_language(language)
        diagnostic_payload: dict[str, object] = {}

        async def _collect_translate_log(level: str, message: str) -> None:
            del level
            prefix = "[single-image-diagnostics]"
            if not isinstance(message, str) or not message.startswith(prefix):
                return
            raw_payload = message[len(prefix) :].strip()
            if not raw_payload:
                return
            try:
                parsed = json.loads(raw_payload)
            except json.JSONDecodeError:
                return
            if isinstance(parsed, dict):
                diagnostic_payload.update(parsed)

        original_name = _normalize_form_text(file.filename or "").strip() or "upload.png"
        _validate_cover_extension(original_name, file.content_type)

        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="图片文件为空")

        translated_bytes, _ = await translate_single_manga_image(
            image_bytes=image_bytes,
            original_name=original_name,
            target_language=normalized_language,
            settings=load_settings(),
            title=_normalize_form_text(title or "").strip() or "单图翻译",
            log_callback=_collect_translate_log,
        )
        return Response(
            content=translated_bytes,
            media_type="image/png",
            headers=_build_translate_image_response_headers(diagnostic_payload),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"图片翻译失败：{exc}") from exc
    finally:
        await file.close()


@library_router.put("/books/{book_id}/progress", response_model=ReadingProgressRecord)
async def put_reading_progress(book_id: str, payload: ReadingProgressPayload) -> ReadingProgressRecord:
    book = _get_book_or_404(book_id)
    chapters = _load_chapter_records(book)
    if not any(chapter.index == payload.chapterIndex for chapter in chapters):
        raise HTTPException(status_code=404, detail=f"未找到章节：{payload.chapterIndex}")

    progress = ReadingProgressRecord(
        bookId=book.id,
        lastChapterIndex=payload.chapterIndex,
        lastScrollRatio=_clamp_unit_float(payload.scrollRatio),
        lastAnchorType=_normalize_progress_anchor_type(payload.anchorType),
        lastAnchorIndex=max(0, payload.anchorIndex),
        lastAnchorOffsetRatio=_clamp_unit_float(payload.anchorOffsetRatio),
        lastReadAt=_now(),
    )
    return save_reading_progress(progress)


@tasks_router.get("/books/{book_id}/tasks", response_model=list[TaskRecord])
async def get_book_tasks(book_id: str) -> list[TaskRecord]:
    _get_book_or_404(book_id)
    return list_tasks(book_id)


@tasks_router.get("/tasks/{task_id}/logs", response_model=list[TaskLogRecord])
async def get_task_logs(task_id: str, after: int = Query(default=0, ge=0)) -> list[TaskLogRecord]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    return list_task_logs(task.id, after)


@tasks_router.get(
    "/tasks/{task_id}/page-results",
    response_model=list[TaskPageResultRecord],
)
async def get_task_page_results(
    task_id: str,
    after: int = Query(default=0, ge=0),
) -> list[TaskPageResultRecord]:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    book = _get_book_or_404(task.bookId)
    if task.taskType != "translate" or book.bookKind != "漫画":
        return []

    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    chapter_lookup = _build_manifest_lookup(manifest)
    results: list[TaskPageResultRecord] = []
    sequence = 0
    for chapter_position, chapter_index in enumerate(task.chapterIndexes, start=1):
        chapter = chapter_lookup.get(chapter_index)
        if not isinstance(chapter, dict):
            continue
        filename = str(chapter.get("file_name") or f"{chapter_index:04d}-chapter-{chapter_index}.txt")
        pages = load_manga_translation_page_payloads(
            book_dir,
            filename,
            include_final=chapter_position <= task.completedCount,
        )
        total_pages = len(_read_string_list(chapter.get("image_files"))) or len(pages)
        chapter_title = str(chapter.get("title") or f"第{chapter_index}话")
        for page in pages:
            sequence += 1
            if sequence <= after:
                continue
            texts = [
                TaskPageTextRecord(
                    order=region.order,
                    sourceText=region.source_text.strip(),
                    translation=region.translation.strip(),
                )
                for region in page.regions
                if region.source_text.strip() or region.translation.strip()
            ]
            if not texts and page.page_translation.strip():
                texts = [
                    TaskPageTextRecord(
                        order=0,
                        translation=page.page_translation.strip(),
                    )
                ]
            results.append(
                TaskPageResultRecord(
                    sequence=sequence,
                    taskId=task.id,
                    chapterIndex=chapter_index,
                    chapterTitle=chapter_title,
                    pageNumber=page.page_number,
                    totalPages=total_pages,
                    texts=texts,
                )
            )
    return results


@tasks_router.post("/books/{book_id}/chapters/download", response_model=TaskRecord)
async def post_download_chapters(book_id: str, payload: ChapterActionPayload) -> TaskRecord:
    book = _get_book_or_404(book_id)
    _load_or_initialize_manifest(book, _resolve_book_dir(book))
    return _enqueue_task(book, "download", payload)


@tasks_router.post("/books/{book_id}/chapters/translate", response_model=TaskRecord)
async def post_translate_chapters(book_id: str, payload: ChapterActionPayload) -> TaskRecord:
    book = _get_book_or_404(book_id)
    _load_or_initialize_manifest(book, _resolve_book_dir(book))
    return _enqueue_task(book, "translate", payload)


@tasks_router.post("/tasks/{task_id}/retry", response_model=TaskRecord)
async def post_retry_task(task_id: str) -> TaskRecord:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    if task.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败任务才能重试")

    _get_book_or_404(task.bookId)
    task.status = "queued"
    task.completedCount = 0
    task.progress = 0
    task.message = "等待重试"
    task.error = None
    task.updatedAt = _now()
    save_task(task)
    TASK_QUEUE.put_nowait(task.id)
    return task


@library_router.post("/books/preview", response_model=PreviewResponse)
async def post_preview(payload: AddBookPayload) -> PreviewResponse:
    try:
        return await preview_from_url(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析失败：{exc}") from exc


def _is_fanqie_source_url(value: str) -> bool:
    hostname = (urlparse(value.strip()).hostname or "").lower()
    return hostname == "fanqienovel.com" or hostname.endswith(".fanqienovel.com")


def _uses_manifest_only_import(payload: AddBookPayload) -> bool:
    if payload.sourceId:
        return True
    return payload.downloadMode == "on_demand" and _is_fanqie_source_url(
        str(payload.sourceUrl)
    )


async def _create_imported_book(payload: AddBookPayload, preview: PreviewResponse) -> BookRecord:
    lightweight_import = _uses_manifest_only_import(payload)
    result = (
        await create_book_manifest_only(payload, preview, LIBRARY_ROOT)
        if lightweight_import
        else await download_book(payload, preview, LIBRARY_ROOT)
    )
    record = BookRecord(
        id=f"book-{uuid4()}",
        title=result.title,
        sourceUrl=str(payload.sourceUrl),
        bookKind=preview.bookKind,
        language=payload.language,
        status="待处理" if lightweight_import else "已下载",
        chapterCount=len(result.chapters),
        translated=False,
        localPath=_storage_key_for_path(result.local_path),
        updatedAt=_now(),
        synopsis=result.synopsis,
        cover=result.cover,
    )
    save_book(record)
    return _hydrate_book_record(record)


async def _run_link_job_stage(
    job_id: str,
    operation: asyncio.Task[Any],
    *,
    message: str,
    start_progress: float,
    end_progress: float,
) -> Any:
    elapsed_seconds = 0
    try:
        while True:
            done, _ = await asyncio.wait({operation}, timeout=3)
            if operation in done:
                return operation.result()
            elapsed_seconds += 3
            progress = min(end_progress - 1, start_progress + elapsed_seconds / 3)
            LINK_JOB_STORE.append_log(
                job_id,
                "info",
                f"{message}，已等待 {elapsed_seconds} 秒",
                progress=progress,
            )
    except BaseException:
        if not operation.done():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
        raise


async def _run_link_job(job_id: str) -> None:
    request = LINK_JOB_STORE.get(job_id)
    payload = LINK_JOB_STORE.payload_for(job_id)
    LINK_JOB_STORE.start(job_id, "开始识别作品链接")
    LINK_JOB_STORE.append_log(job_id, "info", f"已提交链接：{payload.sourceUrl}", progress=5)
    try:
        preview = await _run_link_job_stage(
            job_id,
            asyncio.create_task(preview_from_url(payload)),
            message="正在获取作品元数据和章节目录",
            start_progress=12,
            end_progress=60,
        )
        LINK_JOB_STORE.append_log(
            job_id,
            "info",
            f"已解析《{preview.title}》，共 {preview.chapterCount} 章",
            progress=65 if request.mode == "import" else 95,
        )
        if request.mode == "preview":
            LINK_JOB_STORE.complete(job_id, "链接解析完成", preview=preview)
            return

        manifest_only = _uses_manifest_only_import(payload)
        import_start_message = (
            "开始创建章节目录，正文将在阅读时按需下载"
            if manifest_only
            else "开始下载全部正文并写入本地书库"
        )
        import_wait_message = (
            "正在写入章节目录"
            if manifest_only
            else "正在下载全部正文并写入本地书库"
        )
        LINK_JOB_STORE.append_log(job_id, "info", import_start_message, progress=68)
        book = await _run_link_job_stage(
            job_id,
            asyncio.create_task(_create_imported_book(payload, preview)),
            message=import_wait_message,
            start_progress=68,
            end_progress=98,
        )
        completion_message = (
            "链接导入完成，已启用边看边下" if manifest_only else "链接导入完成"
        )
        LINK_JOB_STORE.complete(job_id, completion_message, preview=preview, book=book)
    except asyncio.CancelledError:
        LINK_JOB_STORE.fail(job_id, "应用正在关闭，链接任务已取消")
        raise
    except Exception as exc:
        LINK_JOB_STORE.fail(job_id, exc)


@library_router.post("/books/link-jobs", response_model=PublicLinkJobRecord)
async def post_link_job(request: LinkJobStartPayload) -> LinkJobRecord:
    job = LINK_JOB_STORE.create(request.mode, request.payload)
    task = asyncio.create_task(_run_link_job(job.id))
    link_job_tasks: set[asyncio.Task[Any]] = getattr(app.state, "link_job_tasks", set())
    link_job_tasks.add(task)
    app.state.link_job_tasks = link_job_tasks
    task.add_done_callback(link_job_tasks.discard)
    return job


@library_router.get("/books/link-jobs/{job_id}", response_model=PublicLinkJobRecord)
async def get_link_job(job_id: str) -> LinkJobRecord:
    try:
        return LINK_JOB_STORE.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.post("/books/import", response_model=PublicBookRecord)
async def post_import(payload: AddBookPayload) -> BookRecord:
    try:
        preview = await preview_from_url(payload)
        return await _create_imported_book(payload, preview)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"导入失败：{exc}") from exc


@library_router.post("/books/import-local", response_model=PublicBookRecord)
async def post_import_local(
    file: Annotated[UploadFile, File()],
    bookKind: Annotated[str, Form()],
    language: Annotated[str, Form()],
    needTranslation: Annotated[bool, Form()] = False,
    title: Annotated[str, Form()] = "",
) -> BookRecord:
    book_dir: Path | None = None
    temp_path: Path | None = None
    try:
        requested_book_kind = _validate_book_kind(bookKind)
        normalized_language = _validate_language(language)
        original_name = _normalize_form_text(file.filename or "")
        temp_path = await _save_local_upload(file, original_name)
        plan = await asyncio.to_thread(
            inspect_local_document,
            temp_path,
            original_name=original_name,
            requested_kind=requested_book_kind,
        )
        imported_title = (
            _normalize_form_text(title or "").strip()
            or plan.title.strip()
            or Path(original_name).stem.strip()
            or "未命名本地作品"
        )
        normalized_book_kind = plan.book_kind
        book_dir = _allocate_book_dir(LIBRARY_ROOT, normalized_language, imported_title)
        book_dir.mkdir(parents=True, exist_ok=False)
        chapter_manifest = await asyncio.to_thread(write_local_document, plan, temp_path, book_dir)
        synopsis = (
            plan.synopsis.strip() or f"从本地 {plan.source_format} 文件导入，共 {len(chapter_manifest)} 章"
        )
        record = BookRecord(
            id=f"book-{uuid4()}",
            title=imported_title,
            sourceUrl="",
            bookKind=normalized_book_kind,
            language=normalized_language,
            status="已下载",
            chapterCount=len(chapter_manifest),
            translated=False,
            localPath=_storage_key_for_path(book_dir),
            updatedAt=_now(),
            synopsis=synopsis,
            cover=None,
        )
        save_manifest(
            book_dir,
            {
                "title": imported_title,
                "author": plan.author,
                "source_url": None,
                "book_kind": normalized_book_kind,
                "language": normalized_language,
                "need_translation": needTranslation,
                "synopsis": record.synopsis,
                "cover_url": None,
                "cover_file": None,
                "chapter_count": len(chapter_manifest),
                "chapters": chapter_manifest,
                "source_format": plan.source_format,
            },
        )
        save_book(record)
        return _hydrate_book_record(record)
    except HTTPException:
        if book_dir is not None and book_dir.exists():
            shutil.rmtree(book_dir, ignore_errors=True)
        raise
    except LocalImportError as exc:
        if book_dir is not None and book_dir.exists():
            shutil.rmtree(book_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"本地导入失败：{exc}") from exc
    except Exception as exc:
        if book_dir is not None and book_dir.exists():
            shutil.rmtree(book_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=f"本地导入失败：{exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        await file.close()


@settings_router.get("/settings", response_model=TranslationSettingsView)
async def get_settings() -> TranslationSettingsView:
    return _settings_view(load_settings())


@settings_router.put("/settings", response_model=TranslationSettingsView)
async def put_settings(payload: TranslationSettings) -> TranslationSettingsView:
    current = load_settings()
    merged = payload.model_copy(deep=True)
    merged.translationModel.apiKey = _merge_secret(
        current.translationModel.apiKey,
        payload.translationModel.apiKey,
        payload.translationModel.apiKeyAction,
    )
    merged.mangaOcr.apiKey = _merge_secret(
        current.mangaOcr.apiKey,
        payload.mangaOcr.apiKey,
        payload.mangaOcr.apiKeyAction,
    )
    merged.bika.password = _merge_secret(
        current.bika.password,
        payload.bika.password,
        payload.bika.passwordAction,
    )
    if not merged.bika.email.strip():
        merged.bika.email = current.bika.email
    return _settings_view(save_settings(merged))


def _merge_secret(current: str, submitted: str, action: str) -> str:
    if action == "clear":
        return ""
    if action == "replace" or submitted:
        return submitted.strip()
    return current


def _settings_view(settings: TranslationSettings) -> TranslationSettingsView:
    return TranslationSettingsView(
        systemPrompt=settings.systemPrompt,
        autoTranslateNextChapters=settings.autoTranslateNextChapters,
        downloadConcurrency=settings.downloadConcurrency,
        translationModel={
            "enabled": settings.translationModel.enabled,
            "baseUrl": settings.translationModel.baseUrl,
            "model": settings.translationModel.model,
            "supportsVision": settings.translationModel.supportsVision,
            "apiKeyConfigured": bool(settings.translationModel.apiKey),
        },
        mangaOcr={
            "enabled": settings.mangaOcr.enabled,
            "baseUrl": settings.mangaOcr.baseUrl,
            "apiKeyConfigured": bool(settings.mangaOcr.apiKey),
        },
        bika={
            "emailConfigured": bool(settings.bika.email),
            "passwordConfigured": bool(settings.bika.password),
        },
    )


def _load_or_create_instance_id() -> str:
    instance_file = DATA_DIR / "instance-id"
    try:
        value = instance_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    value = str(uuid4())
    temporary = instance_file.with_suffix(".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(instance_file)
    return value


def _browser_fallback_available() -> bool:
    configured = os.getenv("QINGJUAN_BROWSER_EXECUTABLE", "").strip()
    if configured:
        return Path(configured).expanduser().is_file()
    names = ("msedge", "msedge.exe", "chromium", "chromium-browser", "google-chrome")
    return any(shutil.which(name) for name in names)


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _configure_unicode_stream(stream: Any) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    except (LookupError, OSError, ValueError):
        return


def _configure_standard_streams() -> None:
    _configure_unicode_stream(sys.stdout)
    _configure_unicode_stream(sys.stderr)


def _startup_console_lines(host: str, port: int) -> tuple[str, ...]:
    public_url = os.getenv("QINGJUAN_PUBLIC_URL", "").strip().rstrip("/")
    if not public_url:
        display_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        public_url = f"http://{display_host}:{port}"

    def console_safe(value: object) -> str:
        return "".join(character if character.isprintable() else "?" for character in str(value))

    return (
        "============================================================",
        "青卷 FastAPI 后端已启动",
        f"客户端地址：{console_safe(public_url)}",
        f"监听地址：{console_safe(host)}:{port}",
        f"业务 API：{console_safe(public_url)}/api/v1",
        f"健康检查：{console_safe(public_url)}/healthz",
        f"数据目录：{console_safe(DATA_DIR)}",
        f"Bearer 认证：{'已启用' if authentication_enabled() else '未启用（仅允许回环监听）'}",
        "原始连接 Token 不写入服务日志；管理员使用 sudo qingjuan-info 查看。",
        "============================================================",
    )


def main() -> None:
    _configure_standard_streams()
    parser = argparse.ArgumentParser(description="青卷后端服务")
    parser.add_argument("command", nargs="?", default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19453)
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()

    if args.command != "serve":
        raise SystemExit(f"Unsupported command: {args.command}")

    if not _is_loopback_host(args.host) and not authentication_enabled():
        raise SystemExit(
            "监听非回环地址必须配置 QINGJUAN_AUTH_TOKEN_SHA256"
        )

    for line in _startup_console_lines(args.host, args.port):
        print(line, flush=True)

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, reload=False))
    if args.parent_pid:
        start_parent_process_watcher(
            args.parent_pid,
            lambda: setattr(server, "should_exit", True),
        )
    server.run()


def _get_book_or_404(book_id: str) -> BookRecord:
    book = get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"未找到书籍：{book_id}")
    return book


def _get_source_or_404(source_id: str) -> BookSourceRecord:
    source = get_book_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"未找到书源：{source_id}")
    return source


def _resolve_book_dir(book: BookRecord) -> Path:
    local_path = (book.localPath or "").strip()
    if not local_path or _contains_invalid_windows_path_chars(local_path):
        return LIBRARY_ROOT / f"{_sanitize_book_title(book.title)}-{book.id[:8]}"

    book_dir = Path(local_path)
    if book_dir.is_absolute():
        return book_dir

    candidate = (DATA_DIR / local_path).resolve()
    if candidate.is_relative_to(DATA_DIR.resolve()):
        return candidate
    return LIBRARY_ROOT / f"{_sanitize_book_title(book.title)}-{book.id[:8]}"


def _storage_key_for_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(DATA_DIR.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("书籍目录必须位于青卷数据目录中") from exc


def _migrate_book_storage_keys() -> None:
    data_root = DATA_DIR.resolve()
    for book in list_books():
        raw = (book.localPath or "").strip()
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            continue
        resolved = candidate.resolve()
        if not resolved.is_relative_to(data_root):
            continue
        save_book(book.model_copy(update={"localPath": resolved.relative_to(data_root).as_posix()}))


def _contains_invalid_windows_path_chars(path_value: str) -> bool:
    if os.name != "nt":
        return False
    _, path_tail = os.path.splitdrive(path_value)
    return bool(re.search(r'[<>:"|?*]', path_tail))


def _validate_book_kind(value: str) -> str:
    normalized = _normalize_form_text(value).strip()
    if normalized not in {"长小说", "轻小说", "漫画"}:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型：{value}")
    return normalized


def _validate_language(value: str) -> str:
    normalized = _normalize_form_text(value).strip()
    if normalized not in {"中文", "英文", "日文"}:
        raise HTTPException(status_code=400, detail=f"不支持的语言：{value}")
    return normalized


def _normalize_form_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""

    try:
        repaired = normalized.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return normalized
    return repaired.strip() or normalized


async def _fetch_book_source_import_payload(url: str) -> str:
    timeout = httpx.Timeout(
        SOURCE_IMPORT_TIMEOUT,
        connect=SOURCE_IMPORT_CONNECT_TIMEOUT,
        read=SOURCE_IMPORT_TIMEOUT,
    )
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=SOURCE_IMPORT_HEADERS,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
    except httpx.HTTPError:
        return await _fetch_book_source_import_payload_with_browser(url)

    if not text or not text.strip():
        return await _fetch_book_source_import_payload_with_browser(url)
    return text


async def _fetch_book_source_import_payload_with_browser(url: str) -> str:
    snapshot = await _fetch_with_edge_cdp(
        url,
        ready_expression="""
(() => {
  const text = (document.body?.innerText || document.body?.textContent || '').trim();
  return Boolean(text) && (text.startsWith('[') || text.startsWith('{'));
})()
""".strip(),
        headless=False,
        timeout_seconds=40.0,
        blocked_message="浏览器会话仍然无法读取 Legado 书源链接内容",
    )
    content = _extract_book_source_payload_from_html(snapshot.html)
    if not content:
        raise ValueError("浏览器会话未提取到有效的书源 JSON 内容")
    return content


def _extract_book_source_payload_from_html(document_html: str) -> str:
    text = BeautifulSoup(document_html, "html.parser").get_text("\n", strip=True)
    text = html.unescape(text).strip()
    start_positions = [position for position in (text.find("["), text.find("{")) if position >= 0]
    if not start_positions:
        return ""
    return text[min(start_positions) :].strip()


def _import_book_sources(content: str, import_url: str | None = None) -> BookSourceImportResult:
    payload = _parse_book_source_payload(content)
    existing_by_base = {
        _normalize_book_source_identity(source.baseUrl): source for source in list_book_sources()
    }
    # 内置书源不在 existing_by_base 中（list_book_sources 已过滤），但仍占用
    # base_url 唯一约束。预先收集内置站点 URL，导入时跳过冲突项，避免直接
    # INSERT 触发 UNIQUE constraint failed: book_sources.base_url。
    builtin_identities = {
        _normalize_book_source_identity(base_url) for base_url in list_builtin_book_source_base_urls()
    }
    result = BookSourceImportResult()

    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            result.ignored.append(f"第 {index} 项不是对象，已跳过")
            continue

        candidate = _build_imported_book_source(item, import_url=import_url)
        if candidate is None:
            display_name = (
                _normalize_form_text(str(item.get("bookSourceName") or "")).strip() or f"第 {index} 项"
            )
            result.ignored.append(f"{display_name} 缺少有效的 bookSourceUrl，已跳过")
            continue

        identity = _normalize_book_source_identity(candidate.baseUrl)
        existing = existing_by_base.get(identity)
        if existing is None and identity in builtin_identities:
            display_name = candidate.name or candidate.baseUrl
            result.ignored.append(f"{display_name} 与内置书源 URL（{candidate.baseUrl}）冲突，已跳过")
            continue
        if existing is not None:
            if candidate.rulePayload:
                merged = existing.model_copy(
                    update={
                        "name": candidate.name or existing.name,
                        "baseUrl": candidate.baseUrl,
                        "description": candidate.description or existing.description,
                        "bookKind": candidate.bookKind or existing.bookKind,
                        "language": candidate.language or existing.language,
                        "enabled": existing.enabled,
                        "supported": existing.supported,
                        "sampleUrl": candidate.sampleUrl or existing.sampleUrl,
                        "tags": candidate.tags or existing.tags,
                        "origin": candidate.origin or existing.origin,
                        "importUrl": candidate.importUrl or existing.importUrl,
                        "status": candidate.status or existing.status,
                        "statusMessage": candidate.statusMessage or existing.statusMessage,
                        "lastCheckedAt": existing.lastCheckedAt,
                        "rulePayload": copy.deepcopy(candidate.rulePayload),
                        "updatedAt": _now(),
                    }
                )
                saved = save_book_source(merged)
                existing_by_base[identity] = saved
                result.updated.append(saved)
                continue

            duplicate_name = candidate.name or existing.name or candidate.baseUrl
            result.duplicates.append(duplicate_name)
            continue

        saved = save_book_source(candidate)
        existing_by_base[identity] = saved
        result.imported.append(saved)

    return result


def _parse_book_source_payload(content: str) -> list[object]:
    normalized = _normalize_form_text(content).lstrip("\ufeff").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Legado 书源内容不能为空")

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as exc:
        if _looks_like_html(normalized):
            extracted = _extract_book_source_payload_from_html(normalized).lstrip("﻿").strip()
            if extracted:
                try:
                    payload = json.loads(extracted)
                except json.JSONDecodeError as exc_html:
                    payload, jsonp_error = _try_load_book_source_jsonp(extracted)
                    if payload is None:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Legado 书源内容不是合法 JSON：{jsonp_error or exc_html.msg}",
                        ) from exc_html
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Legado 书源内容不是合法 JSON：{exc.msg}",
                ) from exc
        else:
            payload, jsonp_error = _try_load_book_source_jsonp(normalized)
            if payload is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Legado 书源内容不是合法 JSON：{jsonp_error or exc.msg}",
                ) from exc

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in SOURCE_IMPORT_JSON_KEYS:
            nested = payload.get(key)
            if isinstance(nested, list):
                return nested
        return [payload]

    raise HTTPException(status_code=400, detail="Legado 书源内容必须是 JSON 对象或数组")


def _try_load_book_source_jsonp(raw: str) -> tuple[object | None, str | None]:
    inner = _strip_jsonp_wrapper(raw)
    if inner is None or inner == raw:
        return None, None
    try:
        return json.loads(inner), None
    except json.JSONDecodeError as exc:
        return None, exc.msg


def _strip_jsonp_wrapper(raw: str) -> str | None:
    text = raw.strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    if not text.endswith(")"):
        return None
    open_idx = text.find("(")
    if open_idx <= 0:
        return None
    head = text[:open_idx].strip()
    if not head or not SOURCE_IMPORT_JSONP_NAME_PATTERN.match(head):
        return None
    inner = text[open_idx + 1 : -1].strip()
    return inner or None


def _looks_like_html(text: str) -> bool:
    head = text[:512].lstrip().lower()
    if not head:
        return False
    if head.startswith("<!doctype") or head.startswith("<html") or head.startswith("<!--"):
        return True
    return "<body" in head or "<head" in head or "<script" in head


def _build_imported_book_source(
    entry: dict[str, object], import_url: str | None = None
) -> BookSourceRecord | None:
    name = _normalize_form_text(str(entry.get("bookSourceName") or "")).strip()
    base_url = _normalize_http_url(str(entry.get("bookSourceUrl") or ""))
    if not name or not base_url:
        return None

    group = _normalize_form_text(str(entry.get("bookSourceGroup") or "")).strip()
    comment = _normalize_form_text(str(entry.get("bookSourceComment") or "")).strip()
    source_type = _normalize_source_rule_type(entry.get("bookSourceType"))
    search_url = str(entry.get("searchUrl") or "").strip()

    return BookSourceRecord(
        id=f"source-imported-{uuid4()}",
        name=name,
        baseUrl=base_url,
        description=_build_imported_source_description(group, comment, search_url),
        bookKind=_map_imported_source_book_kind(source_type),
        language=None,
        enabled=_coerce_imported_source_enabled(entry.get("enabled"), default=True),
        supported=False,
        sampleUrl=_resolve_imported_source_sample_url(base_url, search_url),
        tags=_build_imported_source_tags(group, source_type, entry),
        origin="remote" if import_url else "manual",
        importUrl=import_url,
        status="unsupported",
        statusMessage="Legado 规则已保存",
        rulePayload=copy.deepcopy(entry),
    )


def _normalize_book_source_identity(url: str) -> str:
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def _normalize_http_url(value: str) -> str:
    normalized = _normalize_form_text(value).strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return ""
    cleaned_path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{cleaned_path}"


def _resolve_imported_source_sample_url(base_url: str, search_url: str) -> str | None:
    normalized_search_url = _normalize_form_text(search_url).strip()
    if not normalized_search_url:
        return base_url
    candidate = urljoin(f"{base_url}/", normalized_search_url)
    return _normalize_http_url(candidate) or base_url


def _normalize_source_rule_type(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _map_imported_source_book_kind(source_type: int | None) -> str | None:
    if source_type == 2:
        return "漫画"
    return None


def _coerce_imported_source_enabled(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _build_imported_source_tags(group: str, source_type: int | None, entry: dict[str, object]) -> list[str]:
    tags: list[str] = ["Legado", "阅读书源"]
    if group:
        tags.append(group)
    if source_type == 0:
        tags.append("文本规则")
    elif source_type == 1:
        tags.append("音频规则")
    elif source_type == 2:
        tags.append("图片规则")
    elif source_type == 3:
        tags.append("文件规则")

    if _normalize_form_text(str(entry.get("searchUrl") or "")).strip():
        tags.append("可搜索")
    if isinstance(entry.get("ruleToc"), dict):
        tags.append("目录规则")
    if isinstance(entry.get("ruleContent"), dict):
        tags.append("正文规则")
    if isinstance(entry.get("ruleBookInfo"), dict):
        tags.append("详情规则")

    unique_tags: list[str] = []
    for tag in tags:
        if tag and tag not in unique_tags:
            unique_tags.append(tag)
    return unique_tags


def _build_imported_source_description(group: str, comment: str, search_url: str) -> str:
    segments: list[str] = []
    if group:
        segments.append(f"分组：{group}")
    if comment:
        segments.append(comment)
    elif _normalize_form_text(search_url).strip():
        segments.append("包含搜索规则，已按 Legado/阅读书源格式保存")
    else:
        segments.append("从外部导入的 Legado/阅读书源配置")
    return " | ".join(segment for segment in segments if segment).strip()


async def _search_legado_sources(
    sources: list[BookSourceRecord],
    keyword: str,
    per_source_limit: int,
    total_limit: int,
) -> list[BookSourceSearchResult]:
    semaphore = asyncio.Semaphore(LEGADO_SEARCH_CONCURRENCY)
    results: list[BookSourceSearchResult] = []

    async def search_one(source: BookSourceRecord) -> list[BookSourceSearchResult]:
        async with semaphore:
            try:
                return await _search_legado_source(source, keyword, per_source_limit)
            except Exception:
                return []

    tasks = {asyncio.create_task(search_one(source)) for source in sources}
    loop = asyncio.get_running_loop()
    total_deadline = loop.time() + LEGADO_SEARCH_TOTAL_TIMEOUT
    result_deadline: float | None = None

    try:
        while tasks:
            deadline = total_deadline
            if result_deadline is not None:
                deadline = min(deadline, result_deadline)
            timeout = max(0.0, deadline - loop.time())
            if timeout <= 0:
                break

            done, tasks = await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                break

            for task in done:
                source_results = await task
                if source_results:
                    results.extend(source_results)

            if results and result_deadline is None:
                result_deadline = loop.time() + LEGADO_SEARCH_RESULT_SETTLE_TIMEOUT
            if len(results) >= total_limit:
                break
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    return results


def _source_has_search_rule(source: BookSourceRecord) -> bool:
    payload = source.rulePayload or {}
    if not isinstance(payload, dict):
        return False
    search_url = str(payload.get("searchUrl") or "").strip()
    rule_search = payload.get("ruleSearch")
    return bool(search_url and isinstance(rule_search, dict))


async def _search_legado_source(
    source: BookSourceRecord, keyword: str, limit: int
) -> list[BookSourceSearchResult]:
    payload = source.rulePayload or {}
    if not isinstance(payload, dict):
        raise ValueError("书源缺少原始规则")

    search_url = str(payload.get("searchUrl") or "").strip()
    rule_search = payload.get("ruleSearch")
    if not search_url or not isinstance(rule_search, dict):
        raise ValueError("书源缺少 searchUrl 或 ruleSearch")

    request = _build_legado_search_request(search_url, keyword, source.baseUrl, payload)
    if not request:
        raise ValueError("无法解析书源搜索地址，可能需要 Legado 脚本引擎")
    search_target = str(request.get("url") or "").strip()
    parsed_target = urlparse(search_target)
    if parsed_target.scheme.lower() not in {"http", "https"} or not parsed_target.netloc:
        raise ValueError("书源搜索地址不合法或缺少协议")

    method = str(request.get("method") or "GET").upper()
    body = request.get("body")
    headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
    charset = str(request.get("charset") or "").strip()
    timeout = httpx.Timeout(LEGADO_SEARCH_SOURCE_TIMEOUT, connect=LEGADO_SEARCH_CONNECT_TIMEOUT)
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout, headers=headers, verify=False
    ) as client:
        if method == "POST":
            response = await client.post(search_target, data=body)
        else:
            response = await client.get(search_target)
        response.raise_for_status()
        if charset:
            response.encoding = charset
        response_text = response.text

    return _parse_legado_search_results(source, response_text, str(response.url), rule_search, limit)


def _build_legado_search_request(
    search_url: str,
    keyword: str,
    base_url: str,
    payload: dict[str, object],
) -> dict[str, object] | None:
    raw_target = _extract_legado_search_target(search_url, base_url)
    if not raw_target:
        return None

    target_with_placeholders = _replace_legado_placeholders(raw_target, keyword)
    target_url, options = _split_legado_request_options(target_with_placeholders)
    resolved_url = _resolve_legado_search_url(target_url, base_url)
    if not resolved_url:
        return None

    headers = _build_legado_headers(payload)
    option_headers = options.get("headers")
    if isinstance(option_headers, dict):
        for key, value in option_headers.items():
            headers[str(key)] = str(value)

    method = str(options.get("method") or payload.get("searchMethod") or "GET").upper()
    body: object | None = None
    option_body = options.get("body")
    if option_body is not None:
        body = _replace_legado_placeholders(str(option_body), keyword)
    elif method == "POST":
        body = _build_legado_search_body(payload, keyword)

    return {
        "url": resolved_url,
        "method": method,
        "body": body,
        "headers": headers,
        "charset": str(options.get("charset") or "").strip(),
    }


def _extract_legado_search_target(search_url: str, base_url: str) -> str:
    target = _normalize_form_text(search_url).strip()
    if not target:
        return ""

    if target.startswith("@js:"):
        script = target[4:].strip()
        extracted = _extract_legado_url_from_js(script, base_url)
        return extracted or ""

    script_end = target.rfind("</js>")
    if script_end >= 0:
        suffix = target[script_end + len("</js>") :].strip()
        if suffix:
            return suffix
        script_start = target.find("<js>")
        if script_start >= 0:
            extracted = _extract_legado_url_from_js(target[script_start + len("<js>") : script_end], base_url)
            return extracted or ""

    return target.replace("{{k}}", "{{key}}")


def _extract_legado_url_from_js(script: str, base_url: str) -> str:
    base_expr = re.escape(base_url.rstrip("/"))
    candidates: list[str] = []

    for pattern in (
        r"url\s*=\s*([\"'])(?P<url>https?://.*?)\1",
        r"return\s+`(?P<url>https?://[^`]+)`",
        r"return\s+([\"'])(?P<url>https?://.*?)\1",
    ):
        for match in re.finditer(pattern, script, flags=re.IGNORECASE | re.DOTALL):
            candidates.append(str(match.group("url")).strip())

    for match in re.finditer(r"url\s*=\s*baseUrl\s*\+\s*([\"'])(?P<path>.*?)\1", script, flags=re.DOTALL):
        candidates.append(f"{base_url.rstrip('/')}{match.group('path').strip()}")

    for match in re.finditer(rf"([\"'])({base_expr}[^\"']*)\1", script, flags=re.DOTALL):
        candidates.append(str(match.group(2)).strip())

    return _pick_legado_js_url_candidate(candidates)


def _pick_legado_js_url_candidate(candidates: list[str]) -> str:
    cleaned: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in cleaned:
            cleaned.append(candidate)
    if not cleaned:
        return ""

    for candidate in cleaned:
        normalized = candidate.lower()
        if "{{key}}" in candidate and (
            "query=" in normalized or "keyword=" in normalized or "search" in normalized
        ):
            return candidate
    for candidate in cleaned:
        if "{{key}}" in candidate and "book_id={{key}}" not in candidate:
            return candidate
    return cleaned[0]


def _split_legado_request_options(target: str) -> tuple[str, dict[str, object]]:
    match = re.match(r"^(?P<url>.*?),\s*(?P<options>\{.*\})\s*$", target, flags=re.DOTALL)
    if not match:
        return target.strip(), {}

    options: dict[str, object] = {}
    try:
        parsed = ast.literal_eval(match.group("options"))
        if isinstance(parsed, dict):
            options = parsed
    except (SyntaxError, ValueError):
        options = {}
    return match.group("url").strip(), options


def _resolve_legado_search_url(target: str, base_url: str) -> str:
    normalized = target.strip()
    if not normalized:
        return ""
    if re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        return normalized
    normalized_base = base_url.strip().split("##", 1)[0].rstrip("/")
    if not normalized_base:
        return normalized
    return urljoin(f"{normalized_base}/", normalized)


def _apply_legado_search_url(search_url: str, keyword: str, base_url: str) -> str:
    request = _build_legado_search_request(search_url, keyword, base_url, {})
    return str(request.get("url") or "") if request else ""


def _build_legado_search_body(payload: dict[str, object], keyword: str) -> dict[str, str]:
    body: dict[str, str] = {}
    request_body = payload.get("searchBody")
    if isinstance(request_body, dict):
        for key, value in request_body.items():
            body[str(key)] = _replace_legado_placeholders(str(value), keyword)
    return body


def _replace_legado_placeholders(value: str, keyword: str) -> str:
    normalized = value.strip()
    encoded_keyword = quote(keyword)
    replacements = {
        "{{key}}": encoded_keyword,
        "{{searchKey}}": encoded_keyword,
        "{{keyword}}": encoded_keyword,
        "{{searchword}}": encoded_keyword,
        "{{k}}": encoded_keyword,
        "{{page}}": LEGADO_SEARCH_DEFAULT_PAGE,
        "{key}": encoded_keyword,
        "{keyword}": encoded_keyword,
        "$key": encoded_keyword,
        "$keyword": encoded_keyword,
    }
    for token, replacement in replacements.items():
        normalized = normalized.replace(token, replacement)
    normalized = re.sub(r"\{\{\s*\(?\s*page\s*-\s*1\s*\)?\s*\*\s*\d+\s*\}\}", "0", normalized)
    normalized = re.sub(r"\{\{\s*page\s*\}\}", LEGADO_SEARCH_DEFAULT_PAGE, normalized)
    return normalized


def _build_legado_headers(payload: dict[str, object]) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
    }
    custom_headers = payload.get("headers")
    if isinstance(custom_headers, dict):
        for key, value in custom_headers.items():
            headers[str(key)] = str(value)
    return headers


def _parse_legado_search_results(
    source: BookSourceRecord,
    response_text: str,
    base_url: str,
    rule_search: dict[str, object],
    limit: int,
) -> list[BookSourceSearchResult]:
    list_selector = _find_first_string(rule_search, ("bookList", "list", "searchList", "items"))
    if list_selector.strip().startswith("$"):
        return _parse_legado_json_search_results(source, response_text, base_url, rule_search, limit)
    return _parse_legado_html_search_results(source, response_text, base_url, rule_search, limit)


def _parse_legado_json_search_results(
    source: BookSourceRecord,
    response_text: str,
    base_url: str,
    rule_search: dict[str, object],
    limit: int,
) -> list[BookSourceSearchResult]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("书源返回内容不是合法 JSON") from exc

    list_selector = _find_first_string(rule_search, ("bookList", "list", "searchList", "items"))
    item_values = _extract_legado_json_values(payload, list_selector)
    item_nodes: list[object] = []
    for item in item_values:
        if isinstance(item, list):
            item_nodes.extend(item)
        else:
            item_nodes.append(item)
    if not item_nodes:
        raise ValueError("未找到搜索结果列表")

    title_selector = _find_first_string(rule_search, ("name", "title", "bookName"))
    author_selector = _find_first_string(rule_search, ("author", "bookAuthor"))
    intro_selector = _find_first_string(rule_search, ("intro", "desc", "description"))
    cover_selector = _find_first_string(rule_search, ("coverUrl", "cover", "image"))
    book_url_selector = _find_first_string(rule_search, ("bookUrl", "url", "detailUrl"))

    results: list[BookSourceSearchResult] = []
    seen: set[str] = set()
    for item in item_nodes:
        title = _normalize_form_text(_extract_legado_json_text(item, title_selector)).strip()
        source_url = _extract_legado_json_url(item, book_url_selector, base_url)
        if not title or not source_url:
            continue
        normalized_url = _normalize_source_url(source_url)
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        results.append(
            BookSourceSearchResult(
                title=title,
                author=_extract_legado_json_text(item, author_selector) or None,
                synopsis=_normalize_search_text(_extract_legado_json_text(item, intro_selector)),
                cover=_extract_legado_json_url(item, cover_selector, base_url),
                sourceUrl=normalized_url,
                bookKind=source.bookKind,
                sourceId=source.id,
                sourceName=source.name,
                sourceLanguage=source.language,
            )
        )
        if len(results) >= limit:
            break
    return results


def _parse_legado_html_search_results(
    source: BookSourceRecord,
    html_text: str,
    base_url: str,
    rule_search: dict[str, object],
    limit: int,
) -> list[BookSourceSearchResult]:
    soup = BeautifulSoup(html_text, "html.parser")
    list_selector = _find_first_string(rule_search, ("bookList", "list", "searchList", "items"))
    item_nodes = (
        _select_legado_nodes(soup, list_selector)
        if list_selector
        else soup.select("a[href], article, li, .book, .item, .result")
    )
    if not item_nodes:
        raise ValueError("未找到搜索结果列表")

    title_selector = _find_first_string(rule_search, ("name", "title", "bookName")) or ""
    author_selector = _find_first_string(rule_search, ("author", "bookAuthor")) or ""
    intro_selector = _find_first_string(rule_search, ("intro", "desc", "description")) or ""
    cover_selector = _find_first_string(rule_search, ("coverUrl", "cover", "image")) or ""
    book_url_selector = _find_first_string(rule_search, ("bookUrl", "url", "detailUrl")) or "a[href]"

    results: list[BookSourceSearchResult] = []
    seen: set[str] = set()
    for node in item_nodes:
        if not isinstance(node, Tag):
            continue
        title = _pick_legado_node_text(node, title_selector) or node.get_text(" ", strip=True)
        title = _normalize_form_text(title).strip()
        if not title:
            continue
        source_url = _pick_legado_node_url(node, book_url_selector, base_url)
        if not source_url:
            continue
        normalized_url = _normalize_source_url(source_url)
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        results.append(
            BookSourceSearchResult(
                title=title,
                author=_pick_legado_node_text(node, author_selector) or None,
                synopsis=_normalize_search_text(
                    _pick_legado_node_text(node, intro_selector) or node.get_text(" ", strip=True)
                ),
                cover=_pick_legado_node_url(node, cover_selector, base_url),
                sourceUrl=normalized_url,
                bookKind=source.bookKind,
                sourceId=source.id,
                sourceName=source.name,
                sourceLanguage=source.language,
            )
        )
        if len(results) >= limit:
            break
    return results


def _find_first_string(payload: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _pick_legado_node_text(node, selector: str) -> str:
    value = _extract_legado_node_value(node, selector, prefer_url=False)
    return _normalize_form_text(value).strip()


def _pick_legado_node_url(node, selector: str, base_url: str) -> str:
    value = _extract_legado_node_value(node, selector, prefer_url=True)
    if not value:
        return ""
    if value.startswith("http") or value.startswith("/"):
        return urljoin(base_url, value)
    return ""


def _clean_legado_selector(selector: str) -> str:
    cleaned = selector.split("@js:", 1)[0].strip()
    cleaned = cleaned.split("##", 1)[0].strip()
    return cleaned


def _select_legado_nodes(root: Any, selector: str) -> list[Tag]:
    cleaned = _clean_legado_selector(selector)
    if not cleaned:
        return []
    if cleaned.startswith("@css:"):
        cleaned = cleaned[5:].strip()
        try:
            return [node for node in root.select(cleaned) if isinstance(node, Tag)]
        except Exception:
            return []
    if "@" not in cleaned:
        try:
            return [node for node in root.select(cleaned) if isinstance(node, Tag)]
        except Exception:
            return []

    current: list[Any] = [root]
    for raw_segment in cleaned.split("@"):
        segment = raw_segment.strip()
        if not segment:
            continue
        next_nodes: list[Any] = []
        if segment.startswith("css:"):
            css_selector = segment[4:].strip()
            for node in current:
                next_nodes.extend(node.select(css_selector))
        elif segment.startswith("class."):
            next_nodes = _select_legado_class_segment(current, segment)
        elif segment.startswith("tag."):
            next_nodes = _select_legado_tag_segment(current, segment[4:])
        elif segment in {"text", "textNodes", "href", "src"}:
            break
        elif segment.startswith("#") or segment.startswith("."):
            for node in current:
                next_nodes.extend(node.select(segment))
        else:
            next_nodes = _select_legado_tag_segment(current, segment)
        current = [node for node in next_nodes if isinstance(node, Tag)]
        if not current:
            break
    return [node for node in current if isinstance(node, Tag)]


def _select_legado_class_segment(nodes: list[Any], segment: str) -> list[Any]:
    parts = segment.split(".")
    if len(parts) < 2:
        return []
    class_name = parts[1]
    index = _parse_legado_index(parts[2] if len(parts) > 2 else "")
    matches: list[Any] = []
    for node in nodes:
        matches.extend(node.find_all(class_=class_name))
    return _pick_legado_index(matches, index)


def _select_legado_tag_segment(nodes: list[Any], segment: str) -> list[Any]:
    exclude_index: int | None = None
    if "!" in segment:
        segment, excluded = segment.split("!", 1)
        exclude_index = _parse_legado_index(excluded)
    parts = segment.split(".")
    tag_name = parts[0]
    index = _parse_legado_index(parts[1] if len(parts) > 1 else "")
    matches: list[Any] = []
    for node in nodes:
        if isinstance(node, Tag):
            matches.extend(node.find_all(tag_name))
    if exclude_index is not None and 0 <= exclude_index < len(matches):
        matches = [item for idx, item in enumerate(matches) if idx != exclude_index]
    return _pick_legado_index(matches, index)


def _parse_legado_index(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pick_legado_index(nodes: list[Any], index: int | None) -> list[Any]:
    if index is None:
        return nodes
    if -len(nodes) <= index < len(nodes):
        return [nodes[index]]
    return []


def _extract_legado_node_value(node: Any, selector: str, *, prefer_url: bool) -> str:
    cleaned = _clean_legado_selector(selector)
    if not cleaned:
        return ""
    parts = [part.strip() for part in cleaned.split("&&") if part.strip()]
    for part in parts or [cleaned]:
        value = _extract_legado_node_value_once(node, part, prefer_url=prefer_url)
        if value:
            return value
    return ""


def _extract_legado_node_value_once(node: Any, selector: str, *, prefer_url: bool) -> str:
    if "@" in selector:
        segments = [segment.strip() for segment in selector.split("@") if segment.strip()]
        terminal = segments[-1] if segments else ""
        path = "@".join(segments[:-1]) if terminal in {"text", "textNodes", "href", "src"} else selector
        terminal = (
            terminal if terminal in {"text", "textNodes", "href", "src"} else "href" if prefer_url else "text"
        )
        targets = _select_legado_nodes(node, path)
        target = targets[0] if targets else None
        if isinstance(target, Tag):
            return _value_from_legado_target(target, terminal)
        return ""

    try:
        target = node.select_one(selector)
    except Exception:
        target = None
    if target is None:
        return ""
    if prefer_url:
        for attr in ("href", "src", "data-src", "data-original"):
            value = str(target.get(attr) or "").strip()
            if value:
                return value
    return target.get_text(" ", strip=True)


def _value_from_legado_target(target: Tag, terminal: str) -> str:
    if terminal in {"text", "textNodes"}:
        return target.get_text(" ", strip=True)
    value = str(target.get(terminal) or "").strip()
    if value:
        return value
    if terminal == "href":
        for attr in ("src", "data-src", "data-original"):
            value = str(target.get(attr) or "").strip()
            if value:
                return value
    return ""


def _extract_legado_json_values(payload: object, selector: str) -> list[object]:
    cleaned = _clean_legado_selector(selector)
    for part in [part.strip() for part in cleaned.split("&&") if part.strip()]:
        values = _extract_legado_json_path(payload, part)
        if values:
            return values
    return []


def _extract_legado_json_text(item: object, selector: str) -> str:
    values = _extract_legado_json_values(item, selector)
    if not values:
        return ""
    value = values[0]
    if isinstance(value, (dict, list)):
        return ""
    return _normalize_form_text(str(value)).strip()


def _extract_legado_json_url(item: object, selector: str, base_url: str) -> str:
    cleaned = _clean_legado_selector(selector)
    if "{{$." in cleaned:
        value = re.sub(
            r"\{\{(\$\.[^{}]+)\}\}",
            lambda match: quote(_first_json_path_text(item, match.group(1))),
            cleaned,
        )
    else:
        value = _extract_legado_json_text(item, cleaned)
    if not value:
        return ""
    return urljoin(base_url, value)


def _first_json_path_text(item: object, selector: str) -> str:
    values = _extract_legado_json_path(item, selector)
    if not values:
        return ""
    value = values[0]
    return "" if isinstance(value, (dict, list)) else str(value)


def _extract_legado_json_path(payload: object, selector: str) -> list[object]:
    path = selector.strip()
    if not path.startswith("$"):
        return []
    path = path.split("##", 1)[0].strip()
    if path.startswith("$.."):
        key_path = path[3:]
        key_name, rest = _split_json_path_head(key_path)
        matches = _find_json_key_recursive(payload, key_name)
        if rest:
            results: list[object] = []
            for match in matches:
                results.extend(_walk_json_path(match, rest))
            return results
        return matches
    if path.startswith("$."):
        return _walk_json_path(payload, path[2:])
    return [payload]


def _split_json_path_head(path: str) -> tuple[str, str]:
    if "." not in path:
        return path, ""
    head, rest = path.split(".", 1)
    return head, rest


def _find_json_key_recursive(payload: object, key: str) -> list[object]:
    key_name, index = _parse_json_key_index(key)
    results: list[object] = []
    if isinstance(payload, dict):
        if key_name in payload:
            value = payload[key_name]
            results.extend(_apply_json_index(value, index))
        for value in payload.values():
            results.extend(_find_json_key_recursive(value, key))
    elif isinstance(payload, list):
        for value in payload:
            results.extend(_find_json_key_recursive(value, key))
    return results


def _walk_json_path(payload: object, path: str) -> list[object]:
    current: list[object] = [payload]
    for segment in [segment for segment in path.split(".") if segment]:
        key_name, index = _parse_json_key_index(segment)
        next_values: list[object] = []
        for value in current:
            if isinstance(value, dict) and key_name in value:
                next_values.extend(_apply_json_index(value[key_name], index))
            elif isinstance(value, list) and key_name == "*":
                next_values.extend(value)
        current = next_values
        if not current:
            break
    return current


def _parse_json_key_index(segment: str) -> tuple[str, int | str | None]:
    match = re.match(r"^(?P<key>[^\[]+)(?:\[(?P<index>\*|\d+)\])?$", segment)
    if not match:
        return segment, None
    raw_index = match.group("index")
    if raw_index == "*":
        return match.group("key"), "*"
    return match.group("key"), int(raw_index) if raw_index is not None else None


def _apply_json_index(value: object, index: int | str | None) -> list[object]:
    if index == "*":
        return list(value) if isinstance(value, list) else []
    if isinstance(index, int):
        if isinstance(value, list) and 0 <= index < len(value):
            return [value[index]]
        return []
    return [value]


def _normalize_fuzzy_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in normalized if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _is_fuzzy_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    cursor = 0
    for char in needle:
        cursor = haystack.find(char, cursor)
        if cursor < 0:
            return False
        cursor += len(char)
    return True


def _fuzzy_match_score(haystack: str, keyword: str) -> int:
    normalized_haystack = _normalize_fuzzy_text(haystack)
    normalized_keyword = _normalize_fuzzy_text(keyword)
    if not normalized_keyword:
        return 0
    if normalized_haystack == normalized_keyword:
        return 100
    if normalized_haystack.startswith(normalized_keyword):
        return 80
    if normalized_keyword in normalized_haystack:
        return 60
    if _is_fuzzy_subsequence(normalized_keyword, normalized_haystack):
        return 30
    return 0


def _source_result_match_score(result: BookSourceSearchResult, keyword: str) -> int:
    title_score = _fuzzy_match_score(result.title, keyword)
    author_score = _fuzzy_match_score(result.author or "", keyword)
    synopsis_score = _fuzzy_match_score(result.synopsis, keyword)
    source_score = _fuzzy_match_score(result.sourceName, keyword)
    return max(title_score, author_score, synopsis_score // 2, source_score // 2)


def _rank_source_search_results(
    results: list[BookSourceSearchResult], keyword: str
) -> list[BookSourceSearchResult]:
    return sorted(
        results,
        key=lambda result: (
            _source_result_match_score(result, keyword),
            -len(result.title),
        ),
        reverse=True,
    )


def _fuzzy_source_search_keywords(keyword: str) -> list[str]:
    candidates = [keyword.strip()]
    normalized = _normalize_fuzzy_text(keyword)
    if normalized and normalized not in candidates:
        candidates.append(normalized)
    return [
        candidate
        for index, candidate in enumerate(candidates)
        if candidate and candidate not in candidates[:index]
    ]


def _dedupe_source_search_results(results: list[BookSourceSearchResult]) -> list[BookSourceSearchResult]:
    unique: list[BookSourceSearchResult] = []
    seen: set[str] = set()
    for result in results:
        if result.sourceUrl in seen:
            continue
        seen.add(result.sourceUrl)
        unique.append(result)
    return unique


def _header_safe_value(value: object, *, max_length: int = 96) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"[^0-9A-Za-z._:/-]+", "-", text).strip("-")
    if not text:
        return None
    return text[:max_length]


def _build_translate_image_response_headers(diagnostics: dict[str, object]) -> dict[str, str]:
    headers: dict[str, str] = {}
    candidates = {
        "X-QingJuan-Manga-Source": diagnostics.get("source_image"),
        "X-QingJuan-Manga-Trace": diagnostics.get("trace_id"),
        "X-QingJuan-Manga-Mode": diagnostics.get("render_mode"),
        "X-QingJuan-Manga-Regions": diagnostics.get("region_count"),
        "X-QingJuan-Manga-Empty-Regions": diagnostics.get("empty_translation_count"),
        "X-QingJuan-Manga-Overflow-Regions": diagnostics.get("overflow_region_count"),
        "X-QingJuan-Manga-Pipeline-Ms": diagnostics.get("pipeline_ms"),
    }
    for name, value in candidates.items():
        safe_value = _header_safe_value(value)
        if safe_value:
            headers[name] = safe_value
    return headers


def _sanitize_book_title(title: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", title).strip().strip(".")
    return sanitized[:80] or "未命名本地小说"


async def _save_local_upload(file: UploadFile, original_name: str) -> Path:
    suffix = Path(original_name).suffix.lower()
    if suffix == ".doc":
        raise LocalImportError("暂不支持旧版 DOC 文件，请先使用 Word 另存为 DOCX 后再导入")
    if suffix not in SUPPORTED_LOCAL_EXTENSIONS:
        raise LocalImportError("不支持该文件格式；小说支持 TXT、TEXT、DOCX、EPUB，漫画支持 PDF")

    cache_dir = DATA_DIR / "import-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    target_path = cache_dir / f"{uuid4().hex}{suffix}"
    byte_limit = LOCAL_FILE_SIZE_LIMITS[suffix]
    written = 0
    try:
        with target_path.open("xb") as target:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > byte_limit:
                    raise LocalImportError(
                        f"{suffix.removeprefix('.').upper()} 文件超过 {byte_limit // 1024 // 1024} MB 限制"
                    )
                target.write(chunk)
        if written == 0:
            raise LocalImportError("本地文件为空")
        return target_path
    except Exception:
        target_path.unlink(missing_ok=True)
        raise


def _validate_cover_extension(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    content_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    if content_type in content_map:
        return content_map[content_type]

    raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WEBP 封面文件")


def _allocate_book_dir(root_dir: Path, language: str, title: str) -> Path:
    base_dir = root_dir / language
    safe_title = _sanitize_book_title(title)
    candidate = base_dir / safe_title
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        suffixed = base_dir / f"{safe_title}-{counter}"
        if not suffixed.exists():
            return suffixed
        counter += 1


def _load_chapter_records(book: BookRecord) -> list[ChapterRecord]:
    book_dir = _resolve_book_dir(book)
    if not book_dir.exists():
        raise HTTPException(status_code=404, detail=f"本地书籍目录不存在：{book.localPath}")

    manifest = _load_or_initialize_manifest(book, book_dir)
    manifest_lookup = _build_manifest_lookup(manifest)
    chapters: list[ChapterRecord] = []

    for index in sorted(manifest_lookup):
        meta = manifest_lookup[index]
        filename = str(meta.get("file_name") or f"{index:04d}-chapter-{index}.txt")
        chapter_path = book_dir / filename
        translated_path = _translated_path_for_filename(book_dir, filename)
        content = chapter_path.read_text(encoding="utf-8") if chapter_path.exists() else ""
        title = str(meta.get("title") or _title_from_filename(chapter_path, index))
        source_url = meta.get("url")
        downloaded = chapter_path.exists()
        translated = translated_path.exists()

        chapters.append(
            ChapterRecord(
                id=f"{book.id}-chapter-{index}",
                index=index,
                title=title,
                fileName=filename,
                wordCount=_count_words(content),
                downloaded=downloaded,
                translated=translated,
                sourceUrl=str(source_url) if source_url else None,
                illustration=bool(meta.get("illustration")),
                imageCount=len(_read_string_list(meta.get("image_urls"))),
                imageUrls=_read_string_list(meta.get("image_urls")),
                imageFiles=_read_string_list(meta.get("image_files")),
                translatedImageFiles=_read_string_list(meta.get("translated_image_files")),
                pageCount=int(
                    meta.get("page_count")
                    or len(_read_string_list(meta.get("image_files")))
                    or len(_read_string_list(meta.get("image_urls")))
                    or 0
                ),
            )
        )

    return chapters


def _load_single_chapter(
    book: BookRecord, chapter_index: int, mode: str = "translated"
) -> tuple[ChapterRecord, Path]:
    chapters = _load_chapter_records(book)
    chapter = next((item for item in chapters if item.index == chapter_index), None)
    if chapter is None:
        raise HTTPException(status_code=404, detail=f"未找到章节：{chapter_index}")

    chapter_path = _resolve_book_dir(book) / chapter.fileName
    translated_path = _translated_path_for_chapter(_resolve_book_dir(book), chapter)
    if mode == "translated" and translated_path.exists():
        return chapter, translated_path

    if not chapter_path.exists():
        raise HTTPException(status_code=404, detail=f"章节文件不存在：{chapter.fileName}")

    return chapter, chapter_path


def _chapter_needs_source_cache(book_dir: Path, chapter: dict | None) -> bool:
    if not isinstance(chapter, dict):
        return False
    source_url = str(chapter.get("url") or "").strip()
    if not source_url:
        return False
    filename = str(chapter.get("file_name") or "").strip()
    if not filename:
        return True
    return not (book_dir / filename).exists()


def _source_chapter_cache_indexes(
    book_dir: Path,
    manifest: dict,
    chapter_index: int,
    *,
    ahead_count: int = SOURCE_CHAPTER_CACHE_AHEAD,
) -> list[int]:
    lookup = _build_manifest_lookup(manifest)
    end_index = chapter_index + max(0, ahead_count)
    indexes: list[int] = []
    for index in range(chapter_index, end_index + 1):
        if _chapter_needs_source_cache(book_dir, lookup.get(index)):
            indexes.append(index)
    return indexes


def _get_reader_cache_locks() -> dict[str, asyncio.Lock]:
    locks = getattr(app.state, "reader_cache_locks", None)
    if not isinstance(locks, dict):
        locks = {}
        app.state.reader_cache_locks = locks
    return locks


def _get_reader_cache_keys() -> set[str]:
    keys = getattr(app.state, "reader_cache_keys", None)
    if not isinstance(keys, set):
        keys = set()
        app.state.reader_cache_keys = keys
    return keys


def _reader_cache_key(book_id: str, chapter_index: int) -> str:
    return f"{book_id}:{chapter_index}"


def _reader_cache_lock_for_book(book_id: str) -> asyncio.Lock:
    locks = _get_reader_cache_locks()
    lock = locks.get(book_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[book_id] = lock
    return lock


async def _cache_one_source_chapter(book: BookRecord, book_dir: Path, chapter_index: int) -> dict:
    lock = _reader_cache_lock_for_book(book.id)
    async with lock:
        if _is_book_deleted(book.id):
            raise HTTPException(status_code=404, detail="书籍已被删除")
        manifest = _load_or_initialize_manifest(book, book_dir)
        lookup = _build_manifest_lookup(manifest)
        if not _chapter_needs_source_cache(book_dir, lookup.get(chapter_index)):
            return manifest
        await download_selected_chapters(
            book_dir=book_dir,
            manifest=manifest,
            chapter_indexes=[chapter_index],
            concurrency=1,
        )
        _refresh_book_state(book)
        return _load_or_initialize_manifest(book, book_dir)


async def _ensure_source_chapter_cached(
    book: BookRecord,
    book_dir: Path,
    manifest: dict,
    chapter_index: int,
) -> dict:
    lookup = _build_manifest_lookup(manifest)
    if not _chapter_needs_source_cache(book_dir, lookup.get(chapter_index)):
        return manifest
    return await _cache_one_source_chapter(book, book_dir, chapter_index)


async def _cache_source_chapters_ahead(book: BookRecord, book_dir: Path, chapter_indexes: list[int]) -> None:
    keys = _get_reader_cache_keys()
    try:
        for chapter_index in chapter_indexes:
            if _is_book_deleted(book.id):
                return
            try:
                await _cache_one_source_chapter(book, book_dir, chapter_index)
            except Exception as exc:
                print(f"[qingjuan-reader-cache] {book.id} chapter {chapter_index} failed: {exc}")
    finally:
        for chapter_index in chapter_indexes:
            keys.discard(_reader_cache_key(book.id, chapter_index))


def _track_reader_cache_task(task: asyncio.Task[None]) -> None:
    tasks = getattr(app.state, "reader_cache_tasks", None)
    if not isinstance(tasks, set):
        tasks = set()
        app.state.reader_cache_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _schedule_source_chapter_cache_ahead(
    book: BookRecord,
    book_dir: Path,
    manifest: dict,
    chapter_index: int,
) -> None:
    candidate_indexes = _source_chapter_cache_indexes(book_dir, manifest, chapter_index)
    if not candidate_indexes:
        return

    keys = _get_reader_cache_keys()
    chapter_indexes: list[int] = []
    for index in candidate_indexes:
        key = _reader_cache_key(book.id, index)
        if key in keys:
            continue
        keys.add(key)
        chapter_indexes.append(index)

    if not chapter_indexes:
        return

    task = asyncio.create_task(_cache_source_chapters_ahead(book, book_dir, chapter_indexes))
    _track_reader_cache_task(task)


def _build_manifest_lookup(manifest: dict) -> dict[int, dict]:
    payload = manifest.get("chapters", [])
    lookup: dict[int, dict] = {}

    if not isinstance(payload, list):
        return lookup

    for item in payload:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, int):
            lookup[index] = item

    return lookup


def _load_or_initialize_manifest(book: BookRecord, book_dir: Path) -> dict:
    manifest = load_manifest(book_dir)
    changed = False
    chapters = manifest.get("chapters")
    if not isinstance(chapters, list):
        chapters = []
        manifest["chapters"] = chapters
        changed = True

    file_map = {
        path.name: path
        for path in sorted(
            path
            for path in book_dir.glob("*.txt")
            if path.is_file() and not path.name.endswith(".translated.txt")
        )
    }
    existing_lookup = _build_manifest_lookup(manifest)

    if not chapters and file_map:
        for index, file_path in enumerate(file_map.values(), start=1):
            chapters.append(
                {
                    "index": index,
                    "title": _title_from_filename(file_path, index),
                    "url": None,
                    "file_name": file_path.name,
                    "downloaded": True,
                    "translated": _translated_path_for_filename(book_dir, file_path.name).exists(),
                    "translated_file_name": build_translated_filename(file_path.name),
                    "translated_meta_file_name": f"{Path(file_path.name).stem}.translated.json",
                    "illustration": False,
                    "image_urls": [],
                    "image_files": [],
                    "translated_image_files": [],
                    "page_count": 0,
                }
            )
        changed = True
    else:
        for index, chapter in existing_lookup.items():
            filename = str(chapter.get("file_name") or f"{index:04d}-chapter-{index}.txt")
            chapter["file_name"] = filename
            chapter["downloaded"] = (book_dir / filename).exists()
            translated_path = _translated_path_for_filename(book_dir, filename)
            chapter["translated"] = translated_path.exists()
            chapter["translated_file_name"] = build_translated_filename(filename)
            chapter["translated_meta_file_name"] = str(
                chapter.get("translated_meta_file_name") or f"{Path(filename).stem}.translated.json"
            )
            chapter.setdefault("title", _title_from_filename(book_dir / filename, index))
            chapter.setdefault("illustration", False)
            chapter["image_urls"] = _read_string_list(chapter.get("image_urls"))
            chapter["image_files"] = _read_string_list(chapter.get("image_files"))
            chapter["translated_image_files"] = _read_string_list(chapter.get("translated_image_files"))
            chapter["page_count"] = int(
                chapter.get("page_count") or len(chapter["image_files"]) or len(chapter["image_urls"]) or 0
            )
            chapter["images_repaired"] = bool(chapter.get("images_repaired"))
            changed = True

    manifest["title"] = manifest.get("title") or book.title
    manifest["synopsis"] = manifest.get("synopsis") or book.synopsis
    manifest["book_kind"] = manifest.get("book_kind") or book.bookKind
    if "cover_url" not in manifest:
        manifest["cover_url"] = book.cover
        changed = True
    manifest["cover_file"] = _read_optional_string(manifest, "cover_file")
    manifest["chapter_count"] = len(chapters)

    if changed and book_dir.exists():
        save_manifest(book_dir, manifest)

    return manifest


def _hydrate_book_record(book: BookRecord) -> BookRecord:
    manifest = _load_or_initialize_manifest(book, _resolve_book_dir(book))
    cover = _resolve_book_cover(book, manifest)
    if cover == book.cover:
        return book
    return book.model_copy(update={"cover": cover})


async def _hydrate_book_record_async(book: BookRecord, *, fetch_remote_metadata: bool = False) -> BookRecord:
    hydrated = _hydrate_book_record(book)
    if hydrated.cover or not fetch_remote_metadata or not book.sourceUrl.strip():
        return hydrated

    try:
        preview = await asyncio.wait_for(
            preview_from_url(
                AddBookPayload(
                    sourceUrl=book.sourceUrl,
                    bookKind=book.bookKind,
                    language=book.language,
                    needTranslation=book.translated,
                    title=book.title,
                )
            ),
            timeout=8,
        )
    except (TimeoutError, Exception):
        return hydrated

    if not preview.cover and not preview.author:
        return hydrated

    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    changed = False
    if preview.cover and not _read_optional_string(manifest, "cover_url"):
        manifest["cover_url"] = preview.cover
        changed = True
    if preview.author and not _read_optional_string(manifest, "author"):
        manifest["author"] = preview.author
        changed = True
    if changed and book_dir.exists():
        save_manifest(book_dir, manifest)

    return hydrated.model_copy(update={"cover": preview.cover or hydrated.cover})


def _build_book_detail(book: BookRecord) -> BookDetailResponse:
    chapters = _load_chapter_records(book)
    manifest = _load_or_initialize_manifest(book, _resolve_book_dir(book))
    refreshed_book = _hydrate_book_record(_refresh_book_state(book, chapters))
    progress = load_reading_progress(book.id)
    max_index = chapters[-1].index if chapters else 0
    if progress.lastChapterIndex > max_index:
        progress = save_reading_progress(
            ReadingProgressRecord(
                bookId=book.id,
                lastChapterIndex=max_index,
                lastScrollRatio=0,
                lastAnchorType="top",
                lastAnchorIndex=0,
                lastAnchorOffsetRatio=0,
                lastReadAt=progress.lastReadAt,
            )
        )

    return BookDetailResponse(
        book=refreshed_book,
        title=refreshed_book.title,
        author=_read_optional_string(manifest, "author"),
        synopsis=_read_optional_string(manifest, "synopsis") or refreshed_book.synopsis,
        addedAt=refreshed_book.updatedAt,
        totalWords=sum(chapter.pageCount for chapter in chapters)
        if refreshed_book.bookKind == "漫画"
        else sum(chapter.wordCount for chapter in chapters),
        downloadedChapterCount=len([chapter for chapter in chapters if chapter.downloaded]),
        translatedChapterCount=len([chapter for chapter in chapters if chapter.translated]),
        progress=progress,
        chapters=chapters,
    )


def _clamp_unit_float(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(float(value), 1.0))


def _normalize_progress_anchor_type(value: str | None) -> str:
    if value in {"top", "paragraph", "image"}:
        return value
    return "top"


def _refresh_book_state(book: BookRecord, chapters: list[ChapterRecord] | None = None) -> BookRecord:
    current_chapters = chapters or _load_chapter_records(book)
    translated = any(chapter.translated for chapter in current_chapters)
    downloaded_count = len([chapter for chapter in current_chapters if chapter.downloaded])
    if current_chapters and all(chapter.translated for chapter in current_chapters):
        status = "已完成"
    elif current_chapters and downloaded_count == len(current_chapters):
        status = "已下载"
    elif downloaded_count > 0:
        status = "解析中"
    else:
        status = "待处理"
    if book.chapterCount == len(current_chapters) and book.translated == translated and book.status == status:
        return book

    refreshed = book.model_copy(
        update={
            "chapterCount": len(current_chapters),
            "translated": translated,
            "status": status,
            "updatedAt": _now(),
        }
    )
    save_book(refreshed)
    return refreshed


def _normalize_chapter_indexes(chapter_indexes: list[int]) -> list[int]:
    normalized = sorted({index for index in chapter_indexes if index > 0})
    if not normalized:
        raise HTTPException(status_code=400, detail="至少选择一个有效章节")
    return normalized


def _translated_path_for_filename(book_dir: Path, filename: str) -> Path:
    return book_dir / build_translated_filename(filename)


def _translated_path_for_chapter(book_dir: Path, chapter: ChapterRecord) -> Path:
    return _translated_path_for_filename(book_dir, chapter.fileName)


def _title_from_filename(chapter_path: Path, index: int) -> str:
    stem = chapter_path.stem
    if "-" in stem:
        _, title = stem.split("-", 1)
        title = title.strip()
        if title:
            return title
    return f"第{index}章"


def _count_words(content: str) -> int:
    return len("".join(content.split()))


def _split_paragraphs(content: str) -> list[str]:
    paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    if paragraphs:
        return paragraphs

    fallback = content.strip()
    return [fallback] if fallback else []


def _read_optional_string(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _read_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        if isinstance(item, str):
            normalized = item.strip()
            if normalized:
                items.append(normalized)
    return items


def _resolve_book_cover(book: BookRecord, manifest: dict) -> str | None:
    cover_file = _read_optional_string(manifest, "cover_file")
    if cover_file:
        return _build_book_asset_url(book.id, cover_file)
    return _read_optional_string(manifest, "cover_url") or book.cover


def _build_book_asset_url(book_id: str, asset_path: str) -> str:
    normalized = "/".join(part for part in Path(asset_path).parts if part not in {"", "."})
    return f"/books/{book_id}/assets/{normalized}"


def _guess_asset_media_type(path: Path) -> str | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        header = b""

    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"

    media_type, _ = mimetypes.guess_type(path.name)
    return media_type


def _build_export_download_url(book_id: str, artifact_id: str) -> str:
    return f"/books/{book_id}/exports/{quote(artifact_id)}"


def _build_file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _safe_export_stem(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return cleaned[:120] or "未命名小说"


def _export_extension(export_format: str) -> str:
    return {
        "txt": ".txt",
        "text": ".text",
        "docx": ".docx",
        "epub": ".epub",
        "pdf": ".pdf",
        "images": ".zip",
    }[export_format]


def _book_export_file_name(book: BookRecord, export_format: str) -> str:
    return f"{_safe_export_stem(book.title)}{_export_extension(export_format)}"


def _chapter_export_file_name(chapter: ChapterRecord, export_format: str) -> str:
    stem = _safe_export_stem(f"{chapter.index:04d}-{chapter.title}")
    return f"{stem}{_export_extension(export_format)}"


def _export_content_type(path: Path) -> str:
    return {
        ".txt": "text/plain; charset=utf-8",
        ".text": "text/plain; charset=utf-8",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".epub": "application/epub+zip",
        ".pdf": "application/pdf",
        ".zip": "application/zip",
    }.get(path.suffix.lower(), "application/octet-stream")


def _artifact_expiry(path: Path) -> str:
    expires = datetime.fromtimestamp(path.stat().st_mtime, UTC) + EXPORT_TTL
    return expires.isoformat().replace("+00:00", "Z")


def _cleanup_expired_exports() -> None:
    if not EXPORT_ROOT.exists():
        return
    cutoff = datetime.now(UTC) - EXPORT_TTL
    for candidate in EXPORT_ROOT.rglob("*"):
        if not candidate.is_file():
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
        if modified < cutoff:
            candidate.unlink(missing_ok=True)


async def _export_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        await asyncio.to_thread(_cleanup_expired_exports)


def _epub_language(language: str) -> str:
    return {
        "中文": "zh-CN",
        "英文": "en",
        "日文": "ja",
    }.get(language, "zh-CN")


def _export_file_path(book: BookRecord, export_format: str) -> Path:
    extensions = {
        "txt": ".txt",
        "text": ".text",
        "docx": ".docx",
        "epub": ".epub",
        "pdf": ".pdf",
        "images": ".zip",
    }
    extension = extensions.get(export_format)
    if extension is None:
        raise HTTPException(status_code=400, detail=f"不支持的文件导出格式：{export_format}")

    export_dir = EXPORT_ROOT / book.id
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / f"{uuid4().hex}{extension}"


def _load_export_chapters(
    book: BookRecord,
    chapter_indexes: list[int] | None = None,
) -> tuple[dict, list[dict[str, object]]]:
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    chapter_records = _load_chapter_records(book)
    selected_indexes = (
        set(_normalize_chapter_indexes(chapter_indexes)) if chapter_indexes else None
    )
    export_items: list[dict[str, object]] = []
    exported_indexes: set[int] = set()

    for chapter in chapter_records:
        if selected_indexes is not None and chapter.index not in selected_indexes:
            continue
        source_path = book_dir / chapter.fileName
        translated_path = _translated_path_for_chapter(book_dir, chapter)
        use_path = translated_path if translated_path.exists() else source_path
        if not use_path.exists():
            continue
        content = use_path.read_text(encoding="utf-8")
        image_paths: list[Path] = []
        translated_image_assets = [
            asset_path for asset_path in chapter.translatedImageFiles if (book_dir / asset_path).exists()
        ]
        image_assets = (
            translated_image_assets
            if (
                use_path == translated_path
                and translated_image_assets
                and translated_image_payload_is_current(book_dir, chapter.fileName)
            )
            else chapter.imageFiles
        )
        for asset_path in image_assets:
            candidate = (book_dir / asset_path).resolve()
            if candidate.exists() and candidate.is_file():
                image_paths.append(candidate)
        export_items.append(
            {
                "chapter": chapter,
                "content": content,
                "image_paths": image_paths,
                "mode": "translated" if use_path == translated_path else "original",
            }
        )
        exported_indexes.add(chapter.index)

    if selected_indexes is not None and exported_indexes != selected_indexes:
        unavailable = "、".join(
            str(index) for index in sorted(selected_indexes - exported_indexes)
        )
        raise HTTPException(
            status_code=400,
            detail=f"所选章节尚未下载或不存在：{unavailable}",
        )

    if not export_items:
        raise HTTPException(status_code=400, detail="当前书籍暂无可导出的章节内容")

    return manifest, export_items


def _write_txt_export(
    book: BookRecord, manifest: dict, export_items: list[dict[str, object]], target_path: Path
) -> None:
    lines = [
        book.title,
        f"作者：{_read_optional_string(manifest, 'author') or '未知'}",
        f"语言：{book.language}",
        f"原始链接：{book.sourceUrl or '本地导入'}",
        f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    synopsis = _read_optional_string(manifest, "synopsis") or book.synopsis
    if synopsis:
        lines.extend(["简介：", synopsis, ""])

    separator = "=" * 48
    for item in export_items:
        chapter = item["chapter"]
        content = str(item["content"])
        image_paths = item["image_paths"]
        lines.extend([separator, str(chapter.title), ""])
        if content.strip():
            lines.append(content.strip())
        if image_paths:
            lines.extend(["", "插图文件："])
            lines.extend(str(path) for path in image_paths)
        lines.extend(["", ""])

    target_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _epub_paragraphs(content: str) -> str:
    paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return "<p>（本章无正文）</p>"
    blocks: list[str] = []
    for paragraph in paragraphs:
        escaped = html.escape(paragraph).replace("\n", "<br/>")
        blocks.append(f"<p>{escaped}</p>")
    return "\n".join(blocks)


def _write_epub_export(
    book: BookRecord, manifest: dict, export_items: list[dict[str, object]], target_path: Path
) -> None:
    book_uuid = str(uuid4())
    language = _epub_language(book.language)
    author = html.escape(_read_optional_string(manifest, "author") or "未知")
    title = html.escape(book.title)
    synopsis = html.escape(_read_optional_string(manifest, "synopsis") or book.synopsis or "")
    chapter_entries: list[dict[str, str]] = []
    nav_items: list[str] = ['<li><a href="cover.xhtml">书籍信息</a></li>']
    manifest_items: list[str] = [
        '<item id="nav" href="Text/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="cover" href="Text/cover.xhtml" media-type="application/xhtml+xml"/>',
        '<item id="style" href="Styles/book.css" media-type="text/css"/>',
    ]
    spine_items: list[str] = []
    image_entries: dict[str, Path] = {}

    for index, item in enumerate(export_items, start=1):
        chapter = item["chapter"]
        content = str(item["content"])
        image_paths: list[Path] = list(item["image_paths"])
        chapter_file = f"chapter-{index:04d}.xhtml"
        chapter_id = f"chapter-{index:04d}"
        title_html = html.escape(str(chapter.title))
        body_parts = [f"<h1>{title_html}</h1>", _epub_paragraphs(content)]
        if image_paths:
            for image_number, image_path in enumerate(image_paths, start=1):
                image_name = f"{index:04d}-{image_number:02d}-{image_path.name}"
                image_entries[image_name] = image_path
                body_parts.append(
                    '<figure class="chapter-image">'
                    f'<img src="../Images/{html.escape(image_name)}" alt="{title_html} 插图 {image_number}"/>'
                    "</figure>"
                )
                manifest_items.append(
                    f'<item id="image-{index:04d}-{image_number:02d}" href="Images/{html.escape(image_name)}" media-type="{mimetypes.guess_type(image_name)[0] or "image/jpeg"}"/>'
                )
        chapter_entries.append({"file_name": chapter_file, "body": "\n".join(body_parts)})
        manifest_items.append(
            f'<item id="{chapter_id}" href="Text/{chapter_file}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{chapter_id}"/>')
        nav_items.append(f'<li><a href="{chapter_file}">{title_html}</a></li>')

    synopsis_section = ""
    if synopsis:
        synopsis_section = (
            f'<section class="synopsis"><h2>简介</h2><p>{synopsis.replace(chr(10), "<br/>")}</p></section>'
        )

    cover_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
  <head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="../Styles/book.css"/>
  </head>
  <body>
    <section class="cover-page">
      <h1>{title}</h1>
      <p class="meta">作者：{author}</p>
      <p class="meta">语言：{html.escape(book.language)}</p>
      <p class="meta">导出时间：{html.escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>
      <p class="meta">来源：{html.escape(book.sourceUrl or "本地导入")}</p>
      {synopsis_section}
    </section>
  </body>
</html>
"""
    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}" xmlns:epub="http://www.idpf.org/2007/ops">
  <head>
    <title>目录</title>
    <link rel="stylesheet" type="text/css" href="../Styles/book.css"/>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>目录</h1>
      <ol>
        {"".join(nav_items)}
      </ol>
    </nav>
  </body>
</html>
"""
    content_opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:{book_uuid}</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>{language}</dc:language>
    <dc:creator>{author}</dc:creator>
    <meta property="dcterms:modified">{datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}</meta>
  </metadata>
  <manifest>
    {"".join(manifest_items)}
  </manifest>
  <spine>
    {"".join(spine_items)}
  </spine>
</package>
"""
    css_content = """
body { font-family: serif; line-height: 1.8; padding: 0 1rem; }
h1, h2 { line-height: 1.4; }
.cover-page { margin-top: 2rem; }
.meta { color: #555; }
.synopsis { margin-top: 2rem; }
.chapter-image { margin: 1.5rem 0; text-align: center; }
.chapter-image img { max-width: 100%; height: auto; }
"""

    with zipfile.ZipFile(target_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr("OEBPS/Styles/book.css", css_content)
        archive.writestr("OEBPS/Text/cover.xhtml", cover_xhtml)
        archive.writestr("OEBPS/Text/nav.xhtml", nav_xhtml)
        archive.writestr("OEBPS/content.opf", content_opf)
        for entry in chapter_entries:
            archive.writestr(
                f"OEBPS/Text/{entry['file_name']}",
                f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
  <head>
    <title>{title}</title>
    <link rel="stylesheet" type="text/css" href="../Styles/book.css"/>
  </head>
  <body>
    {entry["body"]}
  </body>
</html>
""",
            )
        for image_name, image_path in image_entries.items():
            archive.write(image_path, f"OEBPS/Images/{image_name}")


def _chapter_export_file_path(book: BookRecord, export_format: str) -> Path:
    extensions = {
        "txt": ".txt",
        "text": ".text",
        "docx": ".docx",
        "epub": ".epub",
        "pdf": ".pdf",
        "images": ".zip",
    }
    extension = extensions.get(export_format)
    if extension is None:
        raise HTTPException(status_code=400, detail=f"不支持的章节导出格式：{export_format}")

    export_dir = EXPORT_ROOT / book.id
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / f"{uuid4().hex}{extension}"


def _load_chapter_export_item(
    book: BookRecord, chapter_index: int
) -> tuple[dict, dict[str, object]]:
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    chapter, content_path = _load_single_chapter(book, chapter_index, mode="translated")
    content = content_path.read_text(encoding="utf-8")
    translated_path = _translated_path_for_chapter(book_dir, chapter)
    translated_images = [
        asset_path for asset_path in chapter.translatedImageFiles if (book_dir / asset_path).is_file()
    ]
    use_translated_images = (
        content_path == translated_path
        and bool(translated_images)
        and translated_image_payload_is_current(book_dir, chapter.fileName)
    )
    image_assets = translated_images if use_translated_images else chapter.imageFiles
    image_paths = [
        candidate
        for asset_path in image_assets
        if (candidate := (book_dir / asset_path).resolve()).is_file()
    ]
    return manifest, {
        "chapter": chapter,
        "content": content,
        "image_paths": image_paths,
        "mode": "translated" if content_path == translated_path else "original",
    }


def _docx_paragraph_xml(text: str, *, heading: bool = False) -> str:
    paragraph_properties = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if heading else ""
    escaped = html.escape(text)
    return (
        f"<w:p>{paragraph_properties}<w:r><w:t xml:space=\"preserve\">"
        f"{escaped}</w:t></w:r></w:p>"
    )


def _write_docx_export(
    book: BookRecord,
    manifest: dict,
    export_items: list[dict[str, object]],
    target_path: Path,
) -> None:
    document_paragraphs: list[str] = []
    for export_item in export_items:
        chapter = export_item["chapter"]
        content = str(export_item["content"])
        document_paragraphs.append(_docx_paragraph_xml(str(chapter.title), heading=True))
        document_paragraphs.extend(
            _docx_paragraph_xml(paragraph)
            for paragraph in _split_paragraphs(content)
            if paragraph.strip()
        )
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{"".join(document_paragraphs)}<w:sectPr/></w:body>
</w:document>'''
    core_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{html.escape(book.title)}</dc:title>
  <dc:creator>{html.escape(_read_optional_string(manifest, "author") or "未知")}</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}</dcterms:created>
</cp:coreProperties>'''
    content_types_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>'''
    relationships_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>'''
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", relationships_xml)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("docProps/core.xml", core_xml)


def _write_pdf_chapter_export(image_paths: list[Path], target_path: Path) -> None:
    if not image_paths:
        raise HTTPException(status_code=400, detail="所选章节没有可导出的漫画图片")

    pages: list[Image.Image] = []
    try:
        for image_path in image_paths:
            with Image.open(image_path) as source:
                pages.append(source.convert("RGB"))
        first_page, *remaining_pages = pages
        first_page.save(
            target_path,
            format="PDF",
            save_all=True,
            append_images=remaining_pages,
            resolution=100.0,
        )
    except (OSError, UnidentifiedImageError) as exc:
        raise HTTPException(status_code=400, detail=f"漫画图片无法写入 PDF：{exc}") from exc
    finally:
        for page in pages:
            page.close()


def _write_manga_images_zip(
    book: BookRecord,
    export_items: list[dict[str, object]],
    target_path: Path,
) -> int:
    missing_titles = [
        str(item["chapter"].title)
        for item in export_items
        if not list(item["image_paths"])
    ]
    if missing_titles:
        raise HTTPException(
            status_code=400,
            detail=f"以下章节没有可导出的漫画图片：{'、'.join(missing_titles)}",
        )

    image_count = 0
    book_stem = _safe_export_stem(book.title)
    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in export_items:
            chapter = item["chapter"]
            chapter_stem = _safe_export_stem(f"{chapter.index:04d}-{chapter.title}")
            for index, image_path in enumerate(list(item["image_paths"]), start=1):
                extension = image_path.suffix.lower() or ".png"
                archive.write(
                    image_path,
                    f"{book_stem}/{chapter_stem}/{index:03d}{extension}",
                )
                image_count += 1
    return image_count


def _export_chapter(
    book: BookRecord,
    chapter_index: int,
    export_format: str,
) -> tuple[Path, int]:
    novel_formats = {"txt", "text", "docx", "epub"}
    manga_formats = {"pdf", "images"}
    allowed_formats = manga_formats if book.bookKind == "漫画" else novel_formats
    if export_format not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"{book.bookKind}不支持导出为 {export_format.upper()}",
        )

    manifest, export_item = _load_chapter_export_item(book, chapter_index)
    chapter = export_item["chapter"]
    image_paths: list[Path] = list(export_item["image_paths"])
    try:
        final_path = _chapter_export_file_path(book, export_format)
        if export_format == "images":
            file_count = _write_manga_images_zip(book, [export_item], final_path)
        elif export_format in {"txt", "text"}:
            content = str(export_item["content"]).strip()
            final_path.write_text(f"{chapter.title}\n\n{content}\n", encoding="utf-8")
            file_count = 1
        elif export_format == "docx":
            _write_docx_export(book, manifest, [export_item], final_path)
            file_count = 1
        elif export_format == "epub":
            _write_epub_export(book, manifest, [export_item], final_path)
            file_count = 1
        else:
            _write_pdf_chapter_export(image_paths, final_path)
            file_count = len(image_paths)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"章节导出失败：{exc}") from exc
    return final_path, file_count


def _export_book(
    book: BookRecord,
    export_format: str,
    chapter_indexes: list[int] | None = None,
) -> tuple[Path, int, int]:
    novel_formats = {"txt", "text", "docx", "epub"}
    manga_formats = {"pdf", "images"}
    allowed_formats = manga_formats if book.bookKind == "漫画" else novel_formats
    if export_format not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"{book.bookKind}不支持导出为 {export_format.upper()}",
        )

    manifest, export_items = _load_export_chapters(book, chapter_indexes)
    chapter_count = len(export_items)
    if export_format == "images":
        export_path = _export_file_path(book, export_format)
        image_count = _write_manga_images_zip(book, export_items, export_path)
        return export_path, chapter_count, image_count

    final_path = _export_file_path(book, export_format)
    if export_format in {"txt", "text"}:
        _write_txt_export(book, manifest, export_items, final_path)
    elif export_format == "docx":
        _write_docx_export(book, manifest, export_items, final_path)
    elif export_format == "epub":
        _write_epub_export(book, manifest, export_items, final_path)
    else:
        image_paths = [
            image_path
            for item in export_items
            for image_path in list(item["image_paths"])
        ]
        _write_pdf_chapter_export(image_paths, final_path)
    file_count = len(image_paths) if export_format == "pdf" else 1
    return final_path, chapter_count, file_count


def _enqueue_task(book: BookRecord, task_type: str, payload: ChapterActionPayload) -> TaskRecord:
    chapter_indexes = _normalize_chapter_indexes(payload.chapterIndexes)
    now = _now()
    task = TaskRecord(
        id=f"task-{uuid4()}",
        bookId=book.id,
        taskType=task_type,  # type: ignore[arg-type]
        chapterIndexes=chapter_indexes,
        status="queued",
        totalCount=len(chapter_indexes),
        completedCount=0,
        progress=0,
        message="等待队列处理",
        error=None,
        attempts=0,
        createdAt=now,
        updatedAt=now,
    )
    create_task(task)
    TASK_QUEUE.put_nowait(task.id)
    return task


def _is_book_deleted(book_id: str) -> bool:
    deleted_book_ids: set[str] = getattr(app.state, "deleted_book_ids", set())
    return book_id in deleted_book_ids or get_book(book_id) is None


def _is_task_deleted(task_id: str) -> bool:
    return get_task(task_id) is None


def _ensure_task_resources_exist(task_id: str, book_id: str) -> None:
    if _is_task_deleted(task_id) or _is_book_deleted(book_id):
        raise HTTPException(status_code=404, detail="任务或书籍已被删除")


def _append_task_runtime_log(
    task: TaskRecord, level: str, message: str, *, update_message: bool = True
) -> None:
    normalized = message.strip()
    if not normalized:
        return
    timestamp = _now()
    append_task_log(task.id, level, normalized, timestamp)
    if update_message:
        task.message = normalized
        task.updatedAt = timestamp
        save_task(task)


async def _task_worker() -> None:
    while True:
        task_id = await TASK_QUEUE.get()
        try:
            try:
                await _run_task(task_id)
            except HTTPException:
                # 书籍或任务被删除时直接忽略，避免队列 worker 退出。
                pass
            except Exception as exc:
                print(f"[qingjuan-task-worker] {task_id} failed: {exc}")
        finally:
            TASK_QUEUE.task_done()


async def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    if task is None or task.status not in {"queued", "running"}:
        return

    book = _get_book_or_404(task.bookId)
    task.status = "running"
    task.attempts += 1
    task.error = None
    task.message = "任务开始执行"
    task.updatedAt = _now()
    save_task(task)
    _append_task_runtime_log(task, "info", "任务开始执行", update_message=False)

    try:
        if task.taskType == "download":
            await _process_download_task(task, book)
        else:
            await _process_translate_task(task, book)

        if _is_task_deleted(task.id) or _is_book_deleted(book.id):
            return
        task.status = "completed"
        task.completedCount = task.totalCount
        task.progress = 100
        task.message = "任务已完成"
        task.updatedAt = _now()
        save_task(task)
        _append_task_runtime_log(task, "info", "任务已完成", update_message=False)
        if not _is_book_deleted(book.id):
            _refresh_book_state(book)
    except Exception as exc:
        if _is_task_deleted(task.id) or _is_book_deleted(book.id):
            return
        task.status = "failed"
        task.error = str(exc)
        task.message = "任务执行失败"
        task.updatedAt = _now()
        save_task(task)
        _append_task_runtime_log(task, "error", str(exc), update_message=False)


async def _process_download_task(task: TaskRecord, book: BookRecord) -> None:
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    settings = load_settings()
    concurrency = max(1, min(settings.downloadConcurrency, 8))

    async def on_progress(completed_count: int, total_count: int, active_titles: list[str]) -> None:
        _ensure_task_resources_exist(task.id, book.id)
        task.completedCount = completed_count
        task.progress = round(completed_count / total_count * 100, 2) if total_count else 0
        if active_titles:
            preview_titles = "、".join(active_titles[:3])
            if len(active_titles) > 3:
                preview_titles += " 等"
            task.message = (
                f"{concurrency} 线程下载中，已完成 {completed_count}/{total_count} 章，当前：{preview_titles}"
            )
        else:
            task.message = f"{concurrency} 线程下载中，已完成 {completed_count}/{total_count} 章"
        task.updatedAt = _now()
        save_task(task)

    await download_selected_chapters(
        book_dir=book_dir,
        manifest=manifest,
        chapter_indexes=task.chapterIndexes,
        concurrency=concurrency,
        progress_callback=on_progress,
    )


async def _process_translate_task(task: TaskRecord, book: BookRecord) -> None:
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    settings = load_settings()
    unit = "话" if book.bookKind == "漫画" else "章"

    async def on_log(level: str, message: str) -> None:
        _ensure_task_resources_exist(task.id, book.id)
        _append_task_runtime_log(task, level, message)

    for index, chapter_index in enumerate(task.chapterIndexes, start=1):
        _ensure_task_resources_exist(task.id, book.id)
        chapter_label = f"{unit} {chapter_index}"
        _append_task_runtime_log(task, "info", f"开始处理{chapter_label}")

        async def on_page_progress(
            completed_pages: int,
            total_pages: int,
            chapter_position: int = index,
        ) -> None:
            _ensure_task_resources_exist(task.id, book.id)
            chapter_fraction = completed_pages / total_pages if total_pages else 0
            task.completedCount = chapter_position - 1
            task.progress = round(
                ((chapter_position - 1) + chapter_fraction) / task.totalCount * 100,
                2,
            )
            task.message = (
                f"正在翻译第 {chapter_position}/{task.totalCount} {unit}，"
                f"本{unit}已完成 {completed_pages}/{total_pages} 页"
            )
            task.updatedAt = _now()
            save_task(task)

        await translate_selected_chapters(
            book_dir=book_dir,
            manifest=manifest,
            chapter_indexes=[chapter_index],
            language=book.language,
            settings=settings,
            log_callback=on_log,
            progress_callback=on_page_progress,
        )
        _ensure_task_resources_exist(task.id, book.id)
        task.completedCount = index
        task.progress = round(index / task.totalCount * 100, 2)
        task.message = f"已翻译 {index}/{task.totalCount} {unit}"
        task.updatedAt = _now()
        save_task(task)
        _append_task_runtime_log(task, "info", f"已完成{chapter_label}", update_message=False)
        manifest = load_manifest(book_dir)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


app = create_application(
    routers=API_ROUTERS,
    public_routers=PUBLIC_ROUTERS,
    api_prefix=API_PREFIX,
    authenticate=True,
    lifespan=lifespan,
)


if __name__ == "__main__":
    main()
