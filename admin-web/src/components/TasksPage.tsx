import { useMemo, useState } from "react";
import { FileSearchOutlined, RedoOutlined, SearchOutlined } from "@ant-design/icons";
import { Alert, App, Button, Drawer, Input, Progress, Space, Table, Tag, Timeline, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import { getTaskLogs } from "../api";
import type { Task, TaskLog, TaskStatus } from "../types";
import { formatDate } from "./AdminShell";

export const taskStatusLabel: Record<TaskStatus, string> = {
  queued: "等待中",
  running: "进行中",
  completed: "已完成",
  failed: "失败",
};

export const taskStatusColor: Record<TaskStatus, string> = {
  queued: "default",
  running: "processing",
  completed: "success",
  failed: "error",
};

type TasksPageProps = {
  tasks: Task[];
  bookTitles: Map<string, string>;
  onRetry: (taskId: string) => Promise<void>;
};

export function TasksPage({ tasks, bookTitles, onRetry }: TasksPageProps) {
  const { message } = App.useApp();
  const [query, setQuery] = useState("");
  const [logTask, setLogTask] = useState<Task | null>(null);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logError, setLogError] = useState("");
  const [retrying, setRetrying] = useState("");

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return tasks;
    return tasks.filter((task) =>
      [bookTitles.get(task.bookId) ?? "", task.message, task.error ?? "", taskStatusLabel[task.status]]
        .some((value) => value.toLocaleLowerCase().includes(normalized)),
    );
  }, [bookTitles, query, tasks]);

  const openLogs = async (task: Task) => {
    setLogTask(task);
    setLogs([]);
    setLogError("");
    setLogsLoading(true);
    try {
      setLogs(await getTaskLogs(task.id));
    } catch (error) {
      setLogError(error instanceof Error ? error.message : "日志加载失败");
    } finally {
      setLogsLoading(false);
    }
  };

  const columns: ColumnsType<Task> = [
    {
      title: "任务",
      key: "task",
      width: 260,
      render: (_, task) => (
        <div className="book-title-cell">
          <Typography.Text strong ellipsis={{ tooltip: bookTitles.get(task.bookId) }}>
            {bookTitles.get(task.bookId) ?? "书籍已删除"}
          </Typography.Text>
          <Typography.Text type="secondary">
            {task.taskType === "translate" ? "章节翻译" : "章节下载"} · {task.totalCount} 项
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      filters: Object.entries(taskStatusLabel).map(([value, text]) => ({ value, text })),
      onFilter: (value, task) => task.status === value,
      render: (status: TaskStatus) => <Tag color={taskStatusColor[status]}>{taskStatusLabel[status]}</Tag>,
    },
    {
      title: "进度",
      key: "progress",
      width: 230,
      render: (_, task) => (
        <Progress
          percent={Math.round(task.progress)}
          status={task.status === "failed" ? "exception" : task.status === "completed" ? "success" : undefined}
          size="small"
        />
      ),
    },
    {
      title: "说明",
      key: "message",
      render: (_, task) => (
        <Typography.Text type={task.error ? "danger" : "secondary"} ellipsis={{ tooltip: task.error || task.message }}>
          {task.error || task.message || "等待处理"}
        </Typography.Text>
      ),
    },
    {
      title: "更新",
      dataIndex: "updatedAt",
      key: "updatedAt",
      width: 140,
      render: (value: string) => formatDate(value),
      sorter: (left, right) => left.updatedAt.localeCompare(right.updatedAt),
      defaultSortOrder: "descend",
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 170,
      render: (_, task) => (
        <Space size={2}>
          <Button type="text" icon={<FileSearchOutlined />} onClick={() => void openLogs(task)}>日志</Button>
          {task.status === "failed" && (
            <Button
              type="text"
              icon={<RedoOutlined />}
              loading={retrying === task.id}
              onClick={async () => {
                setRetrying(task.id);
                try {
                  await onRetry(task.id);
                } catch (error) {
                  message.error(error instanceof Error ? error.message : "任务重试失败");
                } finally {
                  setRetrying("");
                }
              }}
            >
              重试
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <div className="table-panel">
        <div className="table-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索书名、状态或任务说明"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="table-search"
          />
          <Typography.Text type="secondary">共 {filtered.length} 个任务</Typography.Text>
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          scroll={{ x: 1080 }}
          locale={{ emptyText: query ? "没有匹配的任务" : "暂无任务记录" }}
          pagination={{ pageSize: 12, showSizeChanger: false, hideOnSinglePage: true }}
        />
      </div>

      <Drawer
        title={logTask ? `${bookTitles.get(logTask.bookId) ?? "任务"} · 运行日志` : "运行日志"}
        width={Math.min(560, window.innerWidth)}
        open={Boolean(logTask)}
        onClose={() => setLogTask(null)}
      >
        {logError && <Alert type="error" showIcon title={logError} />}
        {logsLoading ? (
          <div className="drawer-loading">正在读取日志…</div>
        ) : logs.length === 0 ? (
          <div className="quiet-empty">这个任务还没有运行日志。</div>
        ) : (
          <Timeline
            items={logs.map((log) => ({
              color: log.level === "error" ? "red" : log.level === "warning" ? "orange" : "blue",
              children: (
                <div className="log-entry">
                  <Space size={6} wrap>
                    <Tag color={log.level === "error" ? "red" : log.level === "warning" ? "orange" : "blue"}>
                      {log.level === "error" ? "错误" : log.level === "warning" ? "警告" : "信息"}
                    </Tag>
                    <Typography.Text type="secondary">#{log.sequence}</Typography.Text>
                    <Typography.Text type="secondary">{formatDate(log.createdAt)}</Typography.Text>
                  </Space>
                  <Typography.Text>{log.message}</Typography.Text>
                </div>
              ),
            }))}
          />
        )}
      </Drawer>
    </>
  );
}
