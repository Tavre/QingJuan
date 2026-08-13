import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiOutlined,
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  DatabaseOutlined,
  DownloadOutlined,
  ExclamationCircleFilled,
  FileTextOutlined,
  HddOutlined,
  ReloadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  List,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";

import { getServiceDiagnostics } from "../api";
import type { DiagnosticStatus, ServiceDiagnostics } from "../types";

type DiagnosticsPageProps = {
  onOpenLogs: () => void;
};

type DiagnosticIssueRow = ServiceDiagnostics["recentIssues"][number] & { key: string };

const statusMeta: Record<DiagnosticStatus, { label: string; color: string; icon: React.ReactNode }> = {
  healthy: { label: "运行正常", color: "success", icon: <CheckCircleFilled /> },
  warning: { label: "需要关注", color: "warning", icon: <ExclamationCircleFilled /> },
  error: { label: "发现异常", color: "error", icon: <CloseCircleFilled /> },
};

export function DiagnosticsPage({ onOpenLogs }: DiagnosticsPageProps) {
  const { message } = App.useApp();
  const [diagnostics, setDiagnostics] = useState<ServiceDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [error, setError] = useState("");

  const loadDiagnostics = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      setDiagnostics(await getServiceDiagnostics());
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "系统诊断加载失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDiagnostics();
  }, [loadDiagnostics]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => void loadDiagnostics(true), 15_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadDiagnostics]);

  const issueRows = useMemo<DiagnosticIssueRow[]>(
    () => diagnostics?.recentIssues.map((issue, index) => ({
      ...issue,
      key: `${issue.timestamp}-${issue.source}-${index}`,
    })) ?? [],
    [diagnostics?.recentIssues],
  );

  const issueColumns: ColumnsType<DiagnosticIssueRow> = [
    {
      title: "时间",
      dataIndex: "timestamp",
      width: 170,
      render: (value: string) => <Typography.Text>{formatDetailedDate(value)}</Typography.Text>,
    },
    {
      title: "级别",
      dataIndex: "level",
      width: 88,
      render: (value: DiagnosticIssueRow["level"]) => (
        <Tag color={value === "warning" ? "orange" : value === "critical" ? "magenta" : "red"}>
          {value === "warning" ? "警告" : value === "critical" ? "严重" : "错误"}
        </Tag>
      ),
    },
    {
      title: "来源",
      dataIndex: "source",
      width: 170,
      render: (value: string) => <Typography.Text code>{sourceLabel(value)}</Typography.Text>,
    },
    {
      title: "异常摘要",
      dataIndex: "message",
      render: (value: string) => <Typography.Text className="diagnostic-issue-message">{value}</Typography.Text>,
    },
  ];

  if (loading && !diagnostics) {
    return <div className="content-loading"><Spin size="large" /><span>正在检查服务状态…</span></div>;
  }

  if (!diagnostics) {
    return (
      <Alert
        type="error"
        showIcon
        title="系统诊断暂时不可用"
        description={error || "请稍后重试"}
        action={<Button size="small" onClick={() => void loadDiagnostics()}>重试</Button>}
      />
    );
  }

  const meta = statusMeta[diagnostics.status];
  const diskUsedPercent = diagnostics.storage.totalBytes > 0
    ? Math.round(diagnostics.storage.usedBytes / diagnostics.storage.totalBytes * 100)
    : 0;

  const downloadReport = () => {
    try {
      const report = createDiagnosticsReport(diagnostics);
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `qingjuan-diagnostics-${diagnostics.generatedAt.slice(0, 10)}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      message.success("脱敏诊断报告已下载");
    } catch {
      message.error("诊断报告下载失败");
    }
  };

  return (
    <div className="page-stack">
      {error && (
        <Alert
          type="error"
          showIcon
          title="自动刷新失败，仍显示上次诊断结果"
          description={error}
        />
      )}

      <div className={`diagnostic-command-bar status-${diagnostics.status}`}>
        <div className="diagnostic-status-main">
          <span className="diagnostic-status-icon" aria-hidden="true">{meta.icon}</span>
          <div>
            <Space size={8} wrap>
              <Typography.Title level={4}>服务{meta.label}</Typography.Title>
              <Tag color={meta.color}>{meta.label}</Tag>
            </Space>
            <Typography.Text type="secondary">
              最近检查 {formatDetailedDate(diagnostics.generatedAt)} · 诊断结果每 15 秒更新
            </Typography.Text>
          </div>
        </div>
        <Space wrap className="diagnostic-actions">
          <Space size={8}>
            <Switch
              size="small"
              checked={autoRefresh}
              onChange={setAutoRefresh}
              aria-label="自动刷新系统诊断"
            />
            <Typography.Text type="secondary">自动刷新</Typography.Text>
          </Space>
          <Button
            icon={<ReloadOutlined spin={refreshing} />}
            loading={refreshing}
            aria-label="刷新诊断"
            onClick={() => void loadDiagnostics(true)}
          >
            刷新
          </Button>
          <Button type="primary" icon={<DownloadOutlined />} onClick={downloadReport}>
            下载脱敏报告
          </Button>
        </Space>
      </div>

      <Alert
        type="info"
        showIcon
        title="报告可安全用于问题反馈"
        description="只包含运行指标、资源用量、健康检查和已脱敏异常摘要，不包含 API 密钥、管理密码、Cookie、正文或服务器路径。"
      />

      <Row gutter={[16, 16]} className="diagnostic-summary-row">
        <Col xs={24} sm={12} xl={6}>
          <DiagnosticSummary
            icon={<ClockCircleOutlined />}
            title="连续运行"
            value={formatUptime(diagnostics.uptimeSeconds)}
            hint={`启动于 ${formatDetailedDate(diagnostics.startedAt)}`}
          />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <DiagnosticSummary
            icon={<ApiOutlined />}
            title="已处理请求"
            value={diagnostics.requests.total}
            hint={`P95 ${formatMilliseconds(diagnostics.requests.p95DurationMs)}`}
          />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <DiagnosticSummary
            icon={<WarningOutlined />}
            title="服务端错误"
            value={diagnostics.requests.serverErrors}
            hint={`客户端错误 ${diagnostics.requests.clientErrors}`}
            tone={diagnostics.requests.serverErrors > 0 ? "error" : "green"}
          />
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <DiagnosticSummary
            icon={<HddOutlined />}
            title="磁盘剩余"
            value={formatBytes(diagnostics.storage.freeBytes)}
            hint={`已使用 ${diskUsedPercent}%`}
            tone={diskUsedPercent >= 95 ? "error" : diskUsedPercent >= 80 ? "amber" : "blue"}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={14}>
          <Card className="panel-card diagnostic-check-card" title="健康检查">
            <List
              dataSource={diagnostics.checks}
              renderItem={(check) => {
                const checkMeta = statusMeta[check.status];
                return (
                  <List.Item>
                    <div className={`diagnostic-check-icon status-${check.status}`} aria-hidden="true">
                      {checkMeta.icon}
                    </div>
                    <div className="diagnostic-check-main">
                      <Typography.Text strong>{check.label}</Typography.Text>
                      <Typography.Text type="secondary">{check.detail}</Typography.Text>
                    </div>
                    <Tag color={checkMeta.color}>{checkMeta.label}</Tag>
                  </List.Item>
                );
              }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={10}>
          <Card className="panel-card diagnostic-storage-card" title="运行环境与存储">
            <div className="diagnostic-storage-progress">
              <div>
                <Typography.Text strong>数据卷使用情况</Typography.Text>
                <Typography.Text type="secondary">
                  {formatBytes(diagnostics.storage.usedBytes)} / {formatBytes(diagnostics.storage.totalBytes)}
                </Typography.Text>
              </div>
              <Progress
                percent={diskUsedPercent}
                status={diskUsedPercent >= 95 ? "exception" : "normal"}
                showInfo
              />
            </div>
            <Descriptions
              size="small"
              column={1}
              items={[
                { key: "os", label: "操作系统", children: `${diagnostics.runtime.operatingSystem} · ${diagnostics.runtime.architecture}` },
                { key: "python", label: "Python", children: diagnostics.runtime.pythonVersion },
                { key: "database", label: "数据库占用", children: formatBytes(diagnostics.storage.databaseBytes) },
                { key: "logs", label: "轮转日志占用", children: formatBytes(diagnostics.storage.runtimeLogsBytes) },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="panel-card" title="请求指标">
            <Descriptions
              size="small"
              column={1}
              items={[
                { key: "success", label: "成功响应", children: diagnostics.requests.successful },
                { key: "client", label: "客户端错误 (4xx)", children: diagnostics.requests.clientErrors },
                { key: "server", label: "服务端错误 (5xx)", children: diagnostics.requests.serverErrors },
                { key: "average", label: "平均耗时", children: formatMilliseconds(diagnostics.requests.averageDurationMs) },
                { key: "p95", label: "P95 耗时", children: `${formatMilliseconds(diagnostics.requests.p95DurationMs)}（最近 ${diagnostics.requests.sampleSize} 次）` },
              ]}
            />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="panel-card" title="业务负载">
            <Descriptions
              size="small"
              column={1}
              items={[
                { key: "books", label: "书库作品", children: diagnostics.workload.books },
                { key: "tasks", label: "任务总数", children: diagnostics.workload.tasks },
                { key: "active", label: "排队 / 运行", children: `${diagnostics.workload.queuedTasks} / ${diagnostics.workload.runningTasks}` },
                { key: "failed", label: "失败任务", children: diagnostics.workload.failedTasks },
                { key: "queue", label: "内存队列待处理", children: diagnostics.workload.pendingQueueItems },
                { key: "devices", label: "在线 / 已登记设备", children: `${diagnostics.workload.onlineDevices} / ${diagnostics.workload.devices}` },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card
        className="panel-card diagnostic-issues-card"
        title="最近异常摘要"
        extra={<Button type="link" icon={<FileTextOutlined />} onClick={onOpenLogs}>查看完整运行日志</Button>}
      >
        {issueRows.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="近期没有警告或错误日志" />
        ) : (
          <Table
            rowKey="key"
            columns={issueColumns}
            dataSource={issueRows}
            pagination={false}
            size="small"
            scroll={{ x: 820 }}
          />
        )}
      </Card>
    </div>
  );
}

function DiagnosticSummary({
  icon,
  title,
  value,
  hint,
  tone = "blue",
}: {
  icon: React.ReactNode;
  title: string;
  value: string | number;
  hint: string;
  tone?: "blue" | "green" | "amber" | "error";
}) {
  return (
    <Card className={`summary-card diagnostic-summary tone-${tone}`} variant="borderless">
      <div className="summary-icon">{icon}</div>
      <Statistic title={title} value={value} />
      <Typography.Text type="secondary" ellipsis>{hint}</Typography.Text>
    </Card>
  );
}

export function createDiagnosticsReport(diagnostics: ServiceDiagnostics) {
  return {
    reportVersion: 1,
    product: "QingJuan",
    exportedAt: new Date().toISOString(),
    diagnostics,
  };
}

function formatUptime(totalSeconds: number): string {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const days = Math.floor(safeSeconds / 86_400);
  const hours = Math.floor(safeSeconds % 86_400 / 3_600);
  const minutes = Math.floor(safeSeconds % 3_600 / 60);
  if (days > 0) return `${days} 天 ${hours} 小时`;
  if (hours > 0) return `${hours} 小时 ${minutes} 分`;
  if (minutes > 0) return `${minutes} 分钟`;
  return `${safeSeconds} 秒`;
}

function formatBytes(value: number): string {
  let size = Math.max(0, value);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const digits = unitIndex === 0 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(digits)} ${units[unitIndex]}`;
}

function formatMilliseconds(value: number): string {
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 100) return `${value.toFixed(1)} ms`;
  return `${Math.round(value)} ms`;
}

function formatDetailedDate(value: string): string {
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

function sourceLabel(source: string): string {
  if (source === "qingjuan.runtime") return "青卷后端";
  if (source === "qingjuan.task") return "任务程序";
  if (source === "qingjuan.scraper") return "抓取器";
  if (source === "qingjuan.admin") return "管理安全";
  if (source === "uvicorn.access") return "HTTP 访问";
  if (source === "uvicorn.error") return "Uvicorn 服务";
  return source;
}
