from __future__ import annotations

import pytest

from app import main
from app.link_jobs import LinkJobStore
from app.models import AddBookPayload, PreviewResponse


def _payload() -> AddBookPayload:
    return AddBookPayload(
        sourceUrl="https://example.com/comic/1",
        bookKind="漫画",
        language="中文",
    )


def test_link_job_store_tracks_progress_and_incremental_logs() -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())

    store.start(job.id, "开始识别作品链接")
    first_log = store.append_log(job.id, "info", "正在连接目标站点", progress=20)
    second_log = store.append_log(job.id, "info", "正在解析章节目录", progress=55)

    snapshot = store.get(job.id)
    assert snapshot.status == "running"
    assert snapshot.progress == 55
    assert [item.sequence for item in snapshot.logs] == [first_log.sequence, second_log.sequence]
    assert [item.message for item in store.logs_after(job.id, first_log.sequence)] == ["正在解析章节目录"]


def test_link_job_store_keeps_preview_after_completion() -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())
    preview = PreviewResponse(
        title="测试漫画",
        chapterCount=2,
        chapters=[
            {"title": "第一话", "url": "https://example.com/comic/1/1"},
            {"title": "第二话", "url": "https://example.com/comic/1/2"},
        ],
        bookKind="漫画",
    )

    store.complete(job.id, "解析完成", preview=preview)

    snapshot = store.get(job.id)
    assert snapshot.status == "completed"
    assert snapshot.progress == 100
    assert snapshot.preview == preview
    assert store.payload_for(job.id) == _payload()


@pytest.mark.asyncio
async def test_preview_link_job_runs_in_background_and_keeps_logs(monkeypatch) -> None:
    store = LinkJobStore()
    job = store.create("preview", _payload())

    async def fake_preview(_: AddBookPayload) -> PreviewResponse:
        return PreviewResponse(
            title="后台解析作品",
            chapterCount=1,
            chapters=[{"title": "第一章", "url": "https://example.com/chapter/1"}],
            bookKind="漫画",
        )

    monkeypatch.setattr(main, "LINK_JOB_STORE", store)
    monkeypatch.setattr(main, "preview_from_url", fake_preview)

    await main._run_link_job(job.id)

    completed = store.get(job.id)
    assert completed.status == "completed"
    assert completed.preview is not None
    assert completed.preview.title == "后台解析作品"
    assert completed.logs[0].message.startswith("已提交链接")
    assert completed.logs[-1].message == "链接解析完成"
