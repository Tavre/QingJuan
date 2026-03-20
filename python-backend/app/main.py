from __future__ import annotations

# QingJuan
# Author: Tavre
# License: GPL-3.0-only

import asyncio
import argparse
import json
import mimetypes
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    from .db import (
        DATA_DIR,
        get_book,
        init_db,
        list_books,
        list_pending_tasks,
        list_tasks,
        load_reading_progress,
        load_settings,
        create_task,
        delete_book,
        get_task,
        save_book,
        save_reading_progress,
        save_settings,
        save_task,
    )
    from .models import (
        AddBookPayload,
        BookDetailResponse,
        BookRecord,
        ChapterActionPayload,
        ChapterContentResponse,
        ChapterRecord,
        PreviewResponse,
        ReadingProgressPayload,
        ReadingProgressRecord,
        TaskRecord,
        TranslationSettings,
    )
    from .scraper import (
        build_translated_filename,
        download_book,
        download_selected_chapters,
        load_manifest,
        preview_from_url,
        save_manifest,
        translate_selected_chapters,
    )
except ImportError:
    from app.db import (
        DATA_DIR,
        get_book,
        init_db,
        list_books,
        list_pending_tasks,
        list_tasks,
        load_reading_progress,
        load_settings,
        create_task,
        delete_book,
        get_task,
        save_book,
        save_reading_progress,
        save_settings,
        save_task,
    )
    from app.models import (
        AddBookPayload,
        BookDetailResponse,
        BookRecord,
        ChapterActionPayload,
        ChapterContentResponse,
        ChapterRecord,
        PreviewResponse,
        ReadingProgressPayload,
        ReadingProgressRecord,
        TaskRecord,
        TranslationSettings,
    )
    from app.scraper import (
        build_translated_filename,
        download_book,
        download_selected_chapters,
        load_manifest,
        preview_from_url,
        save_manifest,
        translate_selected_chapters,
    )

LIBRARY_ROOT = DATA_DIR / "library"
TASK_QUEUE: asyncio.Queue[str] = asyncio.Queue()

app = FastAPI(title="青卷后端", version="0.1.10")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    for task in list_pending_tasks():
        task.status = "queued"
        task.message = "等待队列处理"
        task.error = None
        task.updatedAt = _now()
        save_task(task)
        TASK_QUEUE.put_nowait(task.id)
    app.state.queue_worker = asyncio.create_task(_task_worker())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    worker = getattr(app.state, "queue_worker", None)
    if worker is not None:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "qingjuan-backend", "dataDir": str(DATA_DIR)}


@app.get("/books", response_model=list[BookRecord])
async def get_books() -> list[BookRecord]:
    books: list[BookRecord] = []
    for book in list_books():
        books.append(await _hydrate_book_record_async(book))
    return books


@app.get("/tasks", response_model=list[TaskRecord])
async def get_tasks() -> list[TaskRecord]:
    return list_tasks()


@app.get("/books/{book_id}", response_model=BookDetailResponse)
async def get_book_detail(book_id: str) -> BookDetailResponse:
    return _build_book_detail(await _hydrate_book_record_async(_get_book_or_404(book_id)))


@app.delete("/books/{book_id}")
async def delete_book_route(book_id: str) -> dict[str, str]:
    book = _get_book_or_404(book_id)
    book_dir = _resolve_book_dir(book)
    delete_book(book.id)
    if book_dir.exists():
        shutil.rmtree(book_dir, ignore_errors=True)
    return {"status": "ok", "bookId": book.id}


@app.get("/books/{book_id}/chapters/{chapter_index}", response_model=ChapterContentResponse)
async def get_chapter_content(
    book_id: str,
    chapter_index: int,
    mode: str = Query(default="translated"),
) -> ChapterContentResponse:
    book = _get_book_or_404(book_id)
    chapter, chapter_path = _load_single_chapter(book, chapter_index, mode)
    content = chapter_path.read_text(encoding="utf-8")

    return ChapterContentResponse(
        bookId=book.id,
        chapter=chapter,
        content=content,
        paragraphs=_split_paragraphs(content),
        mode="translated" if chapter_path.name.endswith(".translated.txt") else "original",
        translatedAvailable=_translated_path_for_chapter(_resolve_book_dir(book), chapter).exists(),
        imageSources=[_build_book_asset_url(book.id, asset_path) for asset_path in chapter.imageFiles],
    )


@app.get("/books/{book_id}/assets/{asset_path:path}")
async def get_book_asset(book_id: str, asset_path: str) -> FileResponse:
    book = _get_book_or_404(book_id)
    book_dir = _resolve_book_dir(book).resolve()
    target_path = (book_dir / asset_path).resolve()
    if not target_path.is_relative_to(book_dir):
        raise HTTPException(status_code=400, detail="非法资源路径")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"资源不存在：{asset_path}")

    media_type, _ = mimetypes.guess_type(target_path.name)
    return FileResponse(target_path, media_type=media_type or "application/octet-stream")


@app.post("/books/{book_id}/cover", response_model=BookRecord)
async def post_book_cover(book_id: str, file: UploadFile = File(...)) -> BookRecord:
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
            if previous_path.exists() and previous_path.is_file() and previous_path.parent == target_dir.resolve() and previous_path != target_path.resolve():
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


@app.put("/books/{book_id}/progress", response_model=ReadingProgressRecord)
async def put_reading_progress(book_id: str, payload: ReadingProgressPayload) -> ReadingProgressRecord:
    book = _get_book_or_404(book_id)
    chapters = _load_chapter_records(book)
    if not any(chapter.index == payload.chapterIndex for chapter in chapters):
        raise HTTPException(status_code=404, detail=f"未找到章节：{payload.chapterIndex}")

    progress = ReadingProgressRecord(
        bookId=book.id,
        lastChapterIndex=payload.chapterIndex,
        lastReadAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return save_reading_progress(progress)


@app.get("/books/{book_id}/tasks", response_model=list[TaskRecord])
async def get_book_tasks(book_id: str) -> list[TaskRecord]:
    _get_book_or_404(book_id)
    return list_tasks(book_id)


@app.post("/books/{book_id}/chapters/download", response_model=TaskRecord)
async def post_download_chapters(book_id: str, payload: ChapterActionPayload) -> TaskRecord:
    book = _get_book_or_404(book_id)
    _load_or_initialize_manifest(book, _resolve_book_dir(book))
    return _enqueue_task(book, "download", payload)


@app.post("/books/{book_id}/chapters/translate", response_model=TaskRecord)
async def post_translate_chapters(book_id: str, payload: ChapterActionPayload) -> TaskRecord:
    book = _get_book_or_404(book_id)
    _load_or_initialize_manifest(book, _resolve_book_dir(book))
    return _enqueue_task(book, "translate", payload)


@app.post("/tasks/{task_id}/retry", response_model=TaskRecord)
async def post_retry_task(task_id: str) -> TaskRecord:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"未找到任务：{task_id}")
    if task.status != "failed":
        raise HTTPException(status_code=400, detail="只有失败任务才能重试")

    book = _get_book_or_404(task.bookId)
    payload = ChapterActionPayload(chapterIndexes=task.chapterIndexes)
    return _enqueue_task(book, task.taskType, payload)


@app.post("/books/preview", response_model=PreviewResponse)
async def post_preview(payload: AddBookPayload) -> PreviewResponse:
    try:
        return await preview_from_url(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"解析失败：{exc}") from exc


@app.post("/books/import", response_model=BookRecord)
async def post_import(payload: AddBookPayload) -> BookRecord:
    try:
        preview = await preview_from_url(payload)
        result = await download_book(payload, preview, LIBRARY_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"导入失败：{exc}") from exc

    record = BookRecord(
        id=f"book-{uuid4()}",
        title=result.title,
        sourceUrl=str(payload.sourceUrl),
        bookKind=payload.bookKind,
        language=payload.language,
        status="已下载",
        chapterCount=len(result.chapters),
        translated=False,
        localPath=str(result.local_path),
        updatedAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        synopsis=result.synopsis,
        cover=result.cover,
    )
    save_book(record)
    return _hydrate_book_record(record)


@app.post("/books/import-local", response_model=BookRecord)
async def post_import_local(
    file: UploadFile = File(...),
    bookKind: str = Form(...),
    language: str = Form(...),
    needTranslation: bool = Form(False),
    title: str = Form(default=""),
) -> BookRecord:
    try:
        normalized_book_kind = _validate_book_kind(bookKind)
        normalized_language = _validate_language(language)
        original_name = _normalize_form_text(file.filename or "")
        content = _decode_local_novel(await file.read())
        imported_title = _normalize_form_text(title or "").strip() or Path(original_name).stem.strip() or "未命名本地小说"
        chapters = _split_local_novel_into_chapters(content)
        book_dir = _allocate_book_dir(LIBRARY_ROOT, normalized_language, imported_title)
        book_dir.mkdir(parents=True, exist_ok=False)
        chapter_manifest = _write_local_book_chapters(book_dir, chapters)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"本地导入失败：{exc}") from exc
    finally:
        await file.close()

    record = BookRecord(
        id=f"book-{uuid4()}",
        title=imported_title,
        sourceUrl="",
        bookKind=normalized_book_kind,
        language=normalized_language,
        status="已下载",
        chapterCount=len(chapter_manifest),
        translated=False,
        localPath=str(book_dir),
        updatedAt=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        synopsis=f"从本地文件导入，共 {len(chapter_manifest)} 章",
        cover=None,
    )
    save_manifest(
        book_dir,
        {
            "title": imported_title,
            "author": None,
            "source_url": None,
            "book_kind": normalized_book_kind,
            "language": normalized_language,
            "need_translation": needTranslation,
            "synopsis": record.synopsis,
            "cover_url": None,
            "cover_file": None,
            "chapter_count": len(chapter_manifest),
            "chapters": chapter_manifest,
        },
    )
    save_book(record)
    return _hydrate_book_record(record)


@app.get("/settings", response_model=TranslationSettings)
async def get_settings() -> TranslationSettings:
    return load_settings()


@app.put("/settings", response_model=TranslationSettings)
async def put_settings(payload: TranslationSettings) -> TranslationSettings:
    return save_settings(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="青卷后端服务")
    parser.add_argument("command", nargs="?", default="serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19453)
    args = parser.parse_args()

    if args.command != "serve":
        raise SystemExit(f"Unsupported command: {args.command}")

    uvicorn.run(app, host=args.host, port=args.port, reload=False)


def _get_book_or_404(book_id: str) -> BookRecord:
    book = get_book(book_id)
    if book is None:
        raise HTTPException(status_code=404, detail=f"未找到书籍：{book_id}")
    return book


def _resolve_book_dir(book: BookRecord) -> Path:
    book_dir = Path(book.localPath)
    if book_dir.is_absolute():
        return book_dir

    candidate_paths = [DATA_DIR / book.localPath, LIBRARY_ROOT / book.localPath]
    for candidate in candidate_paths:
        if candidate.exists():
            return candidate

    return candidate_paths[0]


def _validate_book_kind(value: str) -> str:
    normalized = _normalize_form_text(value).strip()
    if normalized not in {"长小说", "轻小说"}:
        raise HTTPException(status_code=400, detail=f"不支持的小说类型：{value}")
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


def _sanitize_book_title(title: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", title).strip().strip(".")
    return sanitized[:80] or "未命名本地小说"


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


def _decode_local_novel(raw_content: bytes) -> str:
    if not raw_content:
        raise HTTPException(status_code=400, detail="本地文件为空")

    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5", "shift_jis"):
        try:
            content = raw_content.decode(encoding)
            if content.strip():
                return content.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue

    raise HTTPException(status_code=400, detail="无法识别文件编码，请确认是 TXT 文本文件")


def _split_local_novel_into_chapters(content: str) -> list[tuple[str, str]]:
    normalized = content.replace("\ufeff", "").strip()
    if not normalized:
        return [("第1章", "")]

    chapter_heading = re.compile(
        r"(?im)^(?P<title>\s*(?:章节目录\s*)?(?:第\s*[0-9零一二三四五六七八九十百千万两〇]+(?:章|节|卷|回|部|篇)[^\n]*|chapter\s+\d+[^\n]*))\s*$"
    )
    matches = list(chapter_heading.finditer(normalized))
    if not matches:
        return [("第1章", normalized)]

    chapters: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = _normalize_local_chapter_title(match.group("title"), index + 1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[start:end].strip()
        if body:
            chapters.append((title or f"第{index + 1}章", body))

    return chapters or [("第1章", normalized)]


def _normalize_local_chapter_title(raw_title: str, chapter_number: int) -> str:
    normalized = re.sub(r"^\s*章节目录\s*", "", raw_title.strip(), flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return f"第{chapter_number}章"

    match = re.match(
        r"^(第\s*[0-9零一二三四五六七八九十百千万两〇]+(?:章|节|卷|回|部|篇))(?P<suffix>.*)$",
        normalized,
        flags=re.I,
    )
    if not match:
        return normalized

    prefix = re.sub(r"\s+", "", match.group(1))
    suffix = re.sub(r"\s+", " ", match.group("suffix") or "").strip()
    return f"{prefix} {suffix}".strip()


def _write_local_book_chapters(book_dir: Path, chapters: list[tuple[str, str]]) -> list[dict[str, object]]:
    chapter_manifest: list[dict[str, object]] = []
    for index, (title, body) in enumerate(chapters, start=1):
        safe_chapter_title = _sanitize_book_title(title)[:80]
        file_name = f"{index:04d}-{safe_chapter_title}.txt"
        (book_dir / file_name).write_text(body.strip(), encoding="utf-8")
        chapter_manifest.append(
            {
                "index": index,
                "title": title or f"第{index}章",
                "url": None,
                "file_name": file_name,
                "downloaded": True,
                "translated": False,
                "translated_file_name": build_translated_filename(file_name),
                "illustration": False,
                "image_urls": [],
                "image_files": [],
            }
        )
    return chapter_manifest


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
            )
        )

    return chapters


def _load_single_chapter(book: BookRecord, chapter_index: int, mode: str = "translated") -> tuple[ChapterRecord, Path]:
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
            path for path in book_dir.glob("*.txt") if path.is_file() and not path.name.endswith(".translated.txt")
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
                    "illustration": False,
                    "image_urls": [],
                    "image_files": [],
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
            chapter.setdefault("title", _title_from_filename(book_dir / filename, index))
            chapter.setdefault("illustration", False)
            chapter["image_urls"] = _read_string_list(chapter.get("image_urls"))
            chapter["image_files"] = _read_string_list(chapter.get("image_files"))
            changed = True

    manifest["title"] = manifest.get("title") or book.title
    manifest["synopsis"] = manifest.get("synopsis") or book.synopsis
    if "cover_url" not in manifest:
        manifest["cover_url"] = book.cover
        changed = True
    manifest["cover_file"] = _read_optional_string(manifest, "cover_file")
    manifest["chapter_count"] = len(chapters)

    if changed:
        save_manifest(book_dir, manifest)

    return manifest


def _hydrate_book_record(book: BookRecord) -> BookRecord:
    manifest = _load_or_initialize_manifest(book, _resolve_book_dir(book))
    cover = _resolve_book_cover(book, manifest)
    if cover == book.cover:
        return book
    return book.model_copy(update={"cover": cover})


async def _hydrate_book_record_async(book: BookRecord) -> BookRecord:
    hydrated = _hydrate_book_record(book)
    if hydrated.cover:
        return hydrated

    try:
        preview = await preview_from_url(
            AddBookPayload(
                sourceUrl=book.sourceUrl,
                bookKind=book.bookKind,
                language=book.language,
                needTranslation=book.translated,
                title=book.title,
            )
        )
    except Exception:
        return hydrated

    if not preview.cover and not preview.author:
        return hydrated

    manifest = _load_or_initialize_manifest(book, _resolve_book_dir(book))
    changed = False
    if preview.cover and not _read_optional_string(manifest, "cover_url"):
        manifest["cover_url"] = preview.cover
        changed = True
    if preview.author and not _read_optional_string(manifest, "author"):
        manifest["author"] = preview.author
        changed = True
    if changed:
        save_manifest(_resolve_book_dir(book), manifest)

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
                lastReadAt=progress.lastReadAt,
            )
        )

    return BookDetailResponse(
        book=refreshed_book,
        title=refreshed_book.title,
        author=_read_optional_string(manifest, "author"),
        synopsis=_read_optional_string(manifest, "synopsis") or refreshed_book.synopsis,
        addedAt=refreshed_book.updatedAt,
        totalWords=sum(chapter.wordCount for chapter in chapters),
        downloadedChapterCount=len([chapter for chapter in chapters if chapter.downloaded]),
        translatedChapterCount=len([chapter for chapter in chapters if chapter.translated]),
        progress=progress,
        chapters=chapters,
    )


def _refresh_book_state(book: BookRecord, chapters: list[ChapterRecord] | None = None) -> BookRecord:
    current_chapters = chapters or _load_chapter_records(book)
    translated = any(chapter.translated for chapter in current_chapters)
    status = "已完成" if current_chapters and all(chapter.translated for chapter in current_chapters) else "已下载"
    if (
        book.chapterCount == len(current_chapters)
        and book.translated == translated
        and book.status == status
    ):
        return book

    refreshed = book.model_copy(
        update={
            "chapterCount": len(current_chapters),
            "translated": translated,
            "status": status,
            "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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

    try:
        if task.taskType == "download":
            await _process_download_task(task, book)
        else:
            await _process_translate_task(task, book)

        task.status = "completed"
        task.completedCount = task.totalCount
        task.progress = 100
        task.message = "任务已完成"
        task.updatedAt = _now()
        save_task(task)
        _refresh_book_state(book)
    except Exception as exc:
        task.status = "failed"
        task.error = str(exc)
        task.message = "任务执行失败"
        task.updatedAt = _now()
        save_task(task)


async def _process_download_task(task: TaskRecord, book: BookRecord) -> None:
    book_dir = _resolve_book_dir(book)
    manifest = _load_or_initialize_manifest(book, book_dir)
    settings = load_settings()
    concurrency = max(1, min(settings.downloadConcurrency, 8))

    async def on_progress(completed_count: int, total_count: int, active_titles: list[str]) -> None:
        task.completedCount = completed_count
        task.progress = round(completed_count / total_count * 100, 2) if total_count else 0
        if active_titles:
            preview_titles = "、".join(active_titles[:3])
            if len(active_titles) > 3:
                preview_titles += " 等"
            task.message = f"{concurrency} 线程下载中，已完成 {completed_count}/{total_count} 章，当前：{preview_titles}"
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
    for index, chapter_index in enumerate(task.chapterIndexes, start=1):
        await translate_selected_chapters(
            book_dir=book_dir,
            manifest=manifest,
            chapter_indexes=[chapter_index],
            language=book.language,
            settings=settings,
        )
        task.completedCount = index
        task.progress = round(index / task.totalCount * 100, 2)
        task.message = f"已翻译 {index}/{task.totalCount} 章"
        task.updatedAt = _now()
        save_task(task)
        manifest = load_manifest(book_dir)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
