import { useCallback, useEffect, useMemo, useState } from "react";
import { FileTextOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import { Alert, Button, Input, Select, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import { getRuntimeLogs } from "../api";
import type { RuntimeLog, RuntimeLogBatch, RuntimeLogLevel } from "../types";

type RuntimeLogRow = RuntimeLog & { key: string };
type LevelFilter = "all" | RuntimeLogLevel;

const emptyBatch: RuntimeLogBatch = { items: [], sources: [], total: 0 };

const levelLabels: Record<RuntimeLogLevel, string> = {
  debug: "调试",
  info: "信息",
  warning: "警告",
  error: "错误",
  critical: "严重",
};

const levelColors: Record<RuntimeLogLevel, string> = {
  debug: "default",
  info: "blue",
  warning: "orange",
  error: "red",
  critical: "magenta",
};

export function LogsPage() {
  const [batch, setBatch] = useState<RuntimeLogBatch>(emptyBatch);
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<LevelFilter>("all");
  const [source, setSource] = useState("all");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const loadLogs = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      setBatch(await getRuntimeLogs(1000));
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "服务器日志加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void loadLogs(true), 5000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadLogs]);

  const filtered = useMemo<RuntimeLogRow[]>(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return batch.items
      .map((item, index) => ({ ...item, key: `${item.timestamp}-${item.source}-${index}` }))
      .filter((item) => {
        if (level !== "all" && item.level !== level) return false;
        if (source !== "all" && item.source !== source) return false;
        if (!normalized) return true;
        return [item.message, item.source, levelLabels[item.level]]
          .some((value) => value.toLocaleLowerCase().includes(normalized));
      })
      .reverse();
  }, [batch.items, level, query, source]);

  const columns: ColumnsType<RuntimeLogRow> = [
    {
      title: "时间",
      dataIndex: "timestamp",
      key: "timestamp",
      width: 168,
      render: (value: string) => <Typography.Text className="runtime-log-time">{formatLogDate(value)}</Typography.Text>,
    },
    {
      title: "级别",
      dataIndex: "level",
      key: "level",
      width: 88,
      render: (value: RuntimeLogLevel) => <Tag color={levelColors[value]}>{levelLabels[value]}</Tag>,
    },
    {
      title: "来源",
      dataIndex: "source",
      key: "source",
      width: 170,
      render: (value: string) => (
        <div className="runtime-log-source">
          <Typography.Text>{sourceLabel(value)}</Typography.Text>
          <Typography.Text type="secondary">{value}</Typography.Text>
        </div>
      ),
    },
    {
      title: "详细日志",
      dataIndex: "message",
      key: "message",
      render: (value: string) => <pre className="runtime-log-message">{value}</pre>,
    },
  ];

  return (
    <div className="page-stack">
      <Alert
        type="info"
        showIcon
        icon={<FileTextOutlined />}
        title="服务器程序运行日志"
        description="展示 Uvicorn 请求、后端任务、抓取器与应用异常；凭据和会话信息会在写入及返回时脱敏。"
      />
      {error && (
        <Alert
          type="error"
          showIcon
          title="服务器日志加载失败"
          description={error}
          action={<Button size="small" onClick={() => void loadLogs()}>重试</Button>}
        />
      )}
      <div className="table-panel runtime-log-panel">
        <div className="runtime-log-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索日志内容或来源"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="table-search"
          />
          <Select<LevelFilter>
            value={level}
            onChange={setLevel}
            aria-label="筛选日志级别"
            options={[
              { value: "all", label: "全部级别" },
              ...Object.entries(levelLabels).map(([value, label]) => ({ value: value as RuntimeLogLevel, label })),
            ]}
            className="runtime-log-filter"
          />
          <Select
            value={source}
            onChange={setSource}
            aria-label="筛选日志来源"
            options={[
              { value: "all", label: "全部来源" },
              ...batch.sources.map((value) => ({ value, label: sourceLabel(value) })),
            ]}
            className="runtime-log-filter runtime-log-source-filter"
          />
          <Space size={8} className="runtime-log-live-control">
            <Switch checked={autoRefresh} onChange={setAutoRefresh} aria-label="自动刷新服务器日志" />
            <Typography.Text type="secondary">每 5 秒刷新</Typography.Text>
          </Space>
          <Button
            icon={<ReloadOutlined spin={refreshing} />}
            onClick={() => void loadLogs(true)}
            loading={refreshing}
          >
            刷新
          </Button>
        </div>
        <div className="runtime-log-summary">
          <Typography.Text type="secondary">
            显示 {filtered.length} 条 · 轮转日志共 {batch.total} 条
          </Typography.Text>
        </div>
        <Table
          rowKey="key"
          columns={columns}
          dataSource={filtered}
          loading={loading}
          scroll={{ x: 960 }}
          locale={{ emptyText: query || level !== "all" || source !== "all" ? "没有匹配的日志" : "暂无服务器运行日志" }}
          pagination={{ pageSize: 50, showSizeChanger: false, hideOnSinglePage: true }}
        />
      </div>
    </div>
  );
}

function sourceLabel(source: string): string {
  if (source === "qingjuan.runtime") return "青卷后端";
  if (source === "qingjuan.task") return "任务程序";
  if (source === "qingjuan.scraper") return "抓取器";
  if (source === "qingjuan.admin") return "管理安全";
  if (source === "uvicorn.access") return "HTTP 访问";
  if (source === "uvicorn.error") return "Uvicorn 服务";
  return source;
}

function formatLogDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}
