from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from app import main as main_module
from app.local_import import LocalImportError, inspect_local_document, write_local_document
from app.models import BookExportPayload, BookRecord


def _write_test_epub(source: Path) -> None:
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
            <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
            </container>""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
            <package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">
              <metadata><dc:title>EPUB 书名</dc:title><dc:creator>EPUB 作者</dc:creator><dc:description>EPUB 简介</dc:description></metadata>
              <manifest>
                <item id="chapter-2" href="Text/chapter2.xhtml" media-type="application/xhtml+xml"/>
                <item id="chapter-1" href="Text/chapter1.xhtml" media-type="application/xhtml+xml"/>
              </manifest>
              <spine><itemref idref="chapter-1"/><itemref idref="chapter-2"/></spine>
            </package>""",
        )
        archive.writestr(
            "OEBPS/Text/chapter1.xhtml", "<html><body><h1>第一章</h1><p>第一章正文。</p></body></html>"
        )
        archive.writestr(
            "OEBPS/Text/chapter2.xhtml", "<html><body><h1>第二章</h1><p>第二章正文。</p></body></html>"
        )


def test_docx_import_reads_metadata_and_splits_heading_chapters(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "docProps/core.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <cp:coreProperties
              xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
              xmlns:dc="http://purl.org/dc/elements/1.1/">
              <dc:title>来自 Word 的书名</dc:title>
              <dc:creator>测试作者</dc:creator>
              <dc:description>Word 简介</dc:description>
            </cp:coreProperties>""",
        )
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章 初见</w:t></w:r></w:p>
                <w:p><w:r><w:t>第一章正文。</w:t></w:r></w:p>
                <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第二章 再会</w:t></w:r></w:p>
                <w:p><w:r><w:t>第二章正文。</w:t></w:r></w:p>
              </w:body>
            </w:document>""",
        )

    plan = inspect_local_document(source, original_name=source.name, requested_kind="长小说")
    manifest = write_local_document(plan, source, tmp_path / "book")

    assert plan.title == "来自 Word 的书名"
    assert plan.author == "测试作者"
    assert plan.synopsis == "Word 简介"
    assert [chapter.title for chapter in plan.chapters] == ["第一章 初见", "第二章 再会"]
    assert len(manifest) == 2
    assert (tmp_path / "book" / str(manifest[0]["file_name"])).read_text(encoding="utf-8") == "第一章正文。"


def test_epub_import_uses_spine_order_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.epub"
    _write_test_epub(source)

    plan = inspect_local_document(source, original_name=source.name, requested_kind="轻小说")
    manifest = write_local_document(plan, source, tmp_path / "book")

    assert plan.title == "EPUB 书名"
    assert plan.author == "EPUB 作者"
    assert plan.book_kind == "轻小说"
    assert [chapter.title for chapter in plan.chapters] == ["第一章", "第二章"]
    assert len(manifest) == 2


def test_pdf_import_renders_every_page_as_one_manga_chapter(tmp_path: Path) -> None:
    source = tmp_path / "本地漫画.pdf"
    first = Image.new("RGB", (120, 180), "white")
    second = Image.new("RGB", (160, 100), "black")
    first.save(source, "PDF", save_all=True, append_images=[second])

    plan = inspect_local_document(source, original_name=source.name, requested_kind="长小说")
    manifest = write_local_document(plan, source, tmp_path / "book")

    assert plan.book_kind == "漫画"
    assert plan.page_count == 2
    assert len(manifest) == 1
    assert manifest[0]["page_count"] == 2
    assert len(manifest[0]["image_files"]) == 2
    for relative_path in manifest[0]["image_files"]:
        with Image.open(tmp_path / "book" / str(relative_path)) as rendered:
            assert rendered.width >= 120
            assert rendered.height >= 100


def test_unsupported_legacy_doc_has_actionable_error(tmp_path: Path) -> None:
    source = tmp_path / "旧文档.doc"
    source.write_bytes(b"legacy-word")

    with pytest.raises(LocalImportError, match="DOCX"):
        inspect_local_document(source, original_name=source.name, requested_kind="长小说")


@pytest.mark.asyncio
async def test_local_import_route_persists_epub_metadata_and_removes_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "接口导入.epub"
    _write_test_epub(source)
    data_dir = tmp_path / "data"
    library_root = data_dir / "library"
    saved_records = []
    monkeypatch.setattr(main_module, "LIBRARY_ROOT", library_root)
    monkeypatch.setattr(main_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(main_module, "save_book", saved_records.append)
    monkeypatch.setattr(
        main_module,
        "require_user_access",
        lambda _: SimpleNamespace(owner_id="user-admin"),
    )
    upload = UploadFile(io.BytesIO(source.read_bytes()), filename=source.name)

    record = await main_module.post_import_local(
        file=upload,
        bookKind="长小说",
        language="中文",
        request=object(),  # type: ignore[arg-type]
        needTranslation=False,
        title="",
    )

    manifest_path = data_dir / record.localPath / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert record.title == "EPUB 书名"
    assert record.chapterCount == 2
    assert len(saved_records) == 1
    assert manifest["author"] == "EPUB 作者"
    assert manifest["source_format"] == "EPUB"
    assert not any((data_dir / "import-cache").iterdir())


@pytest.mark.parametrize(
    ("export_format", "extension"),
    [("txt", ".txt"), ("text", ".text"), ("docx", ".docx"), ("epub", ".epub")],
)
def test_single_novel_chapter_exports_to_importable_formats(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    export_format: str,
    extension: str,
) -> None:
    book, book_dir = _write_export_book(tmp_path, book_kind="长小说")
    monkeypatch.setattr(main_module, "EXPORT_ROOT", tmp_path / "exports")

    exported_path, file_count = main_module._export_chapter(
        book,
        chapter_index=1,
        export_format=export_format,
    )

    assert exported_path.suffix == extension
    assert exported_path.is_file()
    assert exported_path.stat().st_size > 0
    assert file_count == 1
    if export_format in {"txt", "text"}:
        assert "第一章正文" in exported_path.read_text(encoding="utf-8")
    plan = inspect_local_document(
        exported_path,
        original_name=exported_path.name,
        requested_kind="长小说",
    )
    if export_format not in {"txt", "text"}:
        assert plan.chapters[0].title == "第一章"
    assert "第一章正文" in plan.chapters[0].content


def test_single_manga_chapter_exports_ordered_images_and_importable_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    book, book_dir = _write_export_book(tmp_path, book_kind="漫画")
    monkeypatch.setattr(main_module, "EXPORT_ROOT", tmp_path / "exports")
    images_dir = book_dir / "images"
    images_dir.mkdir(parents=True)
    Image.new("RGB", (80, 120), "red").save(images_dir / "page-b.jpg")
    Image.new("RGB", (100, 70), "blue").save(images_dir / "page-a.png")
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["chapters"][0].update(
        {
            "illustration": True,
            "image_files": ["images/page-b.jpg", "images/page-a.png"],
            "page_count": 2,
        }
    )
    main_module.save_manifest(book_dir, manifest)

    exported_zip, image_count = main_module._export_chapter(
        book,
        chapter_index=1,
        export_format="images",
    )

    assert exported_zip.is_file()
    assert image_count == 2
    with zipfile.ZipFile(exported_zip) as archive:
        assert [Path(name).name for name in archive.namelist()] == ["001.jpg", "002.png"]

    repeated_zip, repeated_count = main_module._export_chapter(
        book,
        chapter_index=1,
        export_format="images",
    )
    assert repeated_zip != exported_zip
    assert repeated_count == 2

    exported_pdf, page_count = main_module._export_chapter(
        book,
        chapter_index=1,
        export_format="pdf",
    )
    plan = inspect_local_document(
        exported_pdf,
        original_name=exported_pdf.name,
        requested_kind="漫画",
    )
    assert page_count == 2
    assert plan.book_kind == "漫画"
    assert plan.page_count == 2


@pytest.mark.parametrize(
    ("export_format", "extension"),
    [("txt", ".txt"), ("text", ".text"), ("docx", ".docx"), ("epub", ".epub")],
)
def test_selected_novel_chapters_export_as_one_importable_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    export_format: str,
    extension: str,
) -> None:
    book, _ = _write_export_book(tmp_path, book_kind="长小说", chapter_count=2)
    monkeypatch.setattr(main_module, "EXPORT_ROOT", tmp_path / "exports")

    exported_path, chapter_count, file_count = main_module._export_book(
        book,
        export_format=export_format,
        chapter_indexes=[2],
    )

    assert exported_path.suffix == extension
    assert chapter_count == 1
    assert file_count == 1
    plan = inspect_local_document(
        exported_path,
        original_name=exported_path.name,
        requested_kind="长小说",
    )
    imported_content = "\n".join(chapter.content for chapter in plan.chapters)
    assert "第二章正文" in imported_content
    assert "第一章正文" not in imported_content


@pytest.mark.asyncio
async def test_book_export_route_reports_selected_chapter_and_file_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    book, _ = _write_export_book(tmp_path, book_kind="长小说", chapter_count=2)
    monkeypatch.setattr(main_module, "_get_book_or_404", lambda _, __: book)
    monkeypatch.setattr(
        main_module,
        "require_user_access",
        lambda _: SimpleNamespace(owner_id="user-admin"),
    )
    monkeypatch.setattr(main_module, "EXPORT_ROOT", tmp_path / "exports")

    response = await main_module.post_book_export(
        book.id,
        BookExportPayload(
            format="docx",
            chapterIndexes=[2],
        ),
        object(),  # type: ignore[arg-type]
    )

    assert response.artifactId
    assert response.downloadUrl.endswith(response.artifactId)
    assert response.sizeBytes > 0
    assert response.chapterCount == 1
    assert response.fileCount == 1


def test_selected_manga_chapters_export_as_zip_and_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    book, book_dir = _write_export_book(tmp_path, book_kind="漫画", chapter_count=2)
    monkeypatch.setattr(main_module, "EXPORT_ROOT", tmp_path / "exports")
    images_dir = book_dir / "images"
    images_dir.mkdir(parents=True)
    image_specs = (
        ("chapter-1-a.jpg", "red"),
        ("chapter-1-b.png", "green"),
        ("chapter-2-a.png", "blue"),
        ("chapter-2-b.jpg", "yellow"),
    )
    for file_name, color in image_specs:
        Image.new("RGB", (72, 96), color).save(images_dir / file_name)
    manifest = json.loads((book_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["chapters"][0].update(
        {
            "image_files": ["images/chapter-1-a.jpg", "images/chapter-1-b.png"],
            "page_count": 2,
        }
    )
    manifest["chapters"][1].update(
        {
            "image_files": ["images/chapter-2-a.png", "images/chapter-2-b.jpg"],
            "page_count": 2,
        }
    )
    main_module.save_manifest(book_dir, manifest)

    exported_zip, chapter_count, image_count = main_module._export_book(
        book,
        export_format="images",
        chapter_indexes=[2],
    )
    assert chapter_count == 1
    assert image_count == 2
    with zipfile.ZipFile(exported_zip) as archive:
        names = archive.namelist()
    assert [Path(name).name for name in names] == ["001.png", "002.jpg"]
    assert all("0002-第二章" in name for name in names)

    exported_pdf, chapter_count, page_count = main_module._export_book(
        book,
        export_format="pdf",
        chapter_indexes=[1, 2],
    )
    plan = inspect_local_document(
        exported_pdf,
        original_name=exported_pdf.name,
        requested_kind="漫画",
    )
    assert chapter_count == 2
    assert page_count == 4
    assert plan.page_count == 4


def _write_export_book(
    tmp_path: Path,
    *,
    book_kind: str,
    chapter_count: int = 1,
) -> tuple[BookRecord, Path]:
    book_dir = tmp_path / "library" / "export-book"
    book_dir.mkdir(parents=True)
    chapter_titles = ["第一章", "第二章"]
    chapters = []
    for index in range(1, chapter_count + 1):
        title = chapter_titles[index - 1]
        chapter_file = f"{index:04d}-{title}.txt"
        (book_dir / chapter_file).write_text(f"{title}正文。", encoding="utf-8")
        chapters.append(
            {
                "index": index,
                "title": title,
                "file_name": chapter_file,
                "downloaded": True,
                "translated": False,
                "illustration": book_kind == "漫画",
                "image_files": [],
                "translated_image_files": [],
                "page_count": 0,
            }
        )
    main_module.save_manifest(
        book_dir,
        {
            "title": "导出测试",
            "author": "测试作者",
            "book_kind": book_kind,
            "chapters": chapters,
        },
    )
    return (
        BookRecord(
            id="book-export-test",
            title="导出测试",
            sourceUrl="",
            bookKind=book_kind,
            language="中文",
            status="已下载",
            chapterCount=chapter_count,
            translated=False,
            localPath=str(book_dir),
        ),
        book_dir,
    )
