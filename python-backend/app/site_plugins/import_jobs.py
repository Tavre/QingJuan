from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..models import SitePluginBookshelfImportItem, SitePluginBookshelfImportJob


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SitePluginImportJobStore:
    def __init__(self, *, maximum_jobs: int = 32) -> None:
        self._jobs: dict[str, SitePluginBookshelfImportJob] = {}
        self._maximum_jobs = maximum_jobs

    def create(self, plugin_id: str) -> SitePluginBookshelfImportJob:
        if any(
            job.pluginId == plugin_id and job.status in {"queued", "running"}
            for job in self._jobs.values()
        ):
            raise ValueError("该插件已有书架导入任务正在运行")
        timestamp = _now()
        job = SitePluginBookshelfImportJob(
            id=f"plugin-import-{uuid4()}",
            pluginId=plugin_id,
            status="queued",
            message="等待读取账号书架",
            createdAt=timestamp,
            updatedAt=timestamp,
        )
        self._jobs[job.id] = job
        self._trim()
        return job.model_copy(deep=True)

    def get(self, job_id: str, plugin_id: str | None = None) -> SitePluginBookshelfImportJob:
        job = self._require(job_id)
        if plugin_id is not None and job.pluginId != plugin_id:
            raise KeyError(f"未找到插件导入任务：{job_id}")
        return job.model_copy(deep=True)

    def start(self, job_id: str, message: str) -> None:
        job = self._require(job_id)
        job.status = "running"
        job.progress = 2
        job.message = message
        job.updatedAt = _now()

    def set_discovered(self, job_id: str, count: int) -> None:
        job = self._require(job_id)
        job.discoveredCount = max(0, count)
        job.progress = 5 if count else 95
        job.message = f"已读取 {count} 本账号书架作品"
        job.updatedAt = _now()

    def append_item(self, job_id: str, item: SitePluginBookshelfImportItem) -> None:
        job = self._require(job_id)
        job.items.append(item.model_copy(deep=True))
        job.processedCount = len(job.items)
        if item.status == "imported":
            job.importedCount += 1
        elif item.status == "skipped":
            job.skippedCount += 1
        elif item.status == "unsupported":
            job.unsupportedCount += 1
        else:
            job.failedCount += 1
        total = max(job.discoveredCount, job.processedCount, 1)
        job.progress = min(98, 5 + (job.processedCount / total) * 90)
        job.message = f"正在处理账号书架：{job.processedCount}/{total}"
        job.updatedAt = _now()

    def complete(self, job_id: str) -> None:
        job = self._require(job_id)
        job.status = "completed"
        job.progress = 100
        job.message = (
            f"书架导入完成：新增 {job.importedCount} 本，跳过 {job.skippedCount} 本，"
            f"暂不支持 {job.unsupportedCount} 本，失败 {job.failedCount} 本"
        )
        job.error = None
        job.updatedAt = _now()

    def fail(self, job_id: str, error: Exception | str) -> None:
        job = self._require(job_id)
        message = str(error).strip() or "账号书架导入失败"
        job.status = "failed"
        job.message = message
        job.error = message
        job.updatedAt = _now()

    def clear(self) -> None:
        self._jobs.clear()

    def _require(self, job_id: str) -> SitePluginBookshelfImportJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"未找到插件导入任务：{job_id}") from exc

    def _trim(self) -> None:
        if len(self._jobs) <= self._maximum_jobs:
            return
        terminal = [
            job for job in self._jobs.values() if job.status in {"completed", "failed"}
        ]
        terminal.sort(key=lambda job: job.updatedAt)
        while len(self._jobs) > self._maximum_jobs and terminal:
            self._jobs.pop(terminal.pop(0).id, None)
