import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  ReloadOutlined,
  SyncOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Descriptions,
  Popconfirm,
  Row,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
} from "antd";

import * as api from "../api";
import { ApiError } from "../api";
import type { BackendUpdateState, BackendUpdateStatus } from "../types";

const POLL_INTERVAL_MS = 2_000;
const UPDATE_REQUEST_STORAGE_KEY = "qingjuan-backend-update-request-id";
const UPDATE_JOB_STORAGE_KEY = "qingjuan-backend-update-job-id";

const activeStates = new Set<BackendUpdateState>([
  "checking",
  "queued",
  "updating",
  "restarting",
  "verifying",
]);

const statePresentation: Record<BackendUpdateState, { label: string; color: string }> = {
  idle: { label: "尚未检查", color: "default" },
  checking: { label: "正在检查", color: "processing" },
  up_to_date: { label: "已是最新", color: "success" },
  available: { label: "发现新版本", color: "warning" },
  queued: { label: "等待升级", color: "processing" },
  updating: { label: "正在升级", color: "processing" },
  restarting: { label: "正在重启", color: "warning" },
  verifying: { label: "正在验证", color: "processing" },
  completed: { label: "升级完成", color: "success" },
  failed: { label: "升级失败", color: "error" },
  unsupported: { label: "不支持在线升级", color: "default" },
};

type BackendUpgradePageProps = {
  activeTaskCount?: number;
  onReload?: () => void;
};

export function BackendUpgradePage({
  activeTaskCount = 0,
  onReload = () => window.location.reload(),
}: BackendUpgradePageProps) {
  const { message } = App.useApp();
  const [status, setStatus] = useState<BackendUpdateStatus | null>(null);
  const statusRef = useRef<BackendUpdateStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [connectionInterrupted, setConnectionInterrupted] = useState(false);
  const [confirmingStart, setConfirmingStart] = useState(() => Boolean(readStoredValue(
    UPDATE_REQUEST_STORAGE_KEY,
  )));
  const confirmingStartRef = useRef(confirmingStart);

  const applyStatus = useCallback((next: BackendUpdateStatus) => {
    statusRef.current = next;
    setStatus(next);
    setLoadError("");
    setConnectionInterrupted(false);

    if (activeStates.has(next.state)) {
      confirmingStartRef.current = false;
      setConfirmingStart(false);
      if (next.jobId) writeStoredValue(UPDATE_JOB_STORAGE_KEY, next.jobId);
      return;
    }

    confirmingStartRef.current = false;
    setConfirmingStart(false);
    if (["completed", "failed", "idle", "up_to_date", "available", "unsupported"].includes(
      next.state,
    )) {
      clearStoredUpdate();
    }
  }, []);

  const loadStatus = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      applyStatus(await api.getBackendUpdateStatus());
    } catch (error) {
      const expectingDisconnect = confirmingStartRef.current
        || (statusRef.current !== null && activeStates.has(statusRef.current.state));
      if (expectingDisconnect) {
        setConnectionInterrupted(true);
      } else if (!silent) {
        setLoadError(error instanceof Error ? error.message : "升级状态读取失败");
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [applyStatus]);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const shouldPoll = confirmingStart || (status !== null && activeStates.has(status.state));
  useEffect(() => {
    if (!shouldPoll) return;
    const timer = window.setInterval(() => void loadStatus(true), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loadStatus, shouldPoll]);

  const checkForUpdate = async () => {
    const previous = statusRef.current;
    setRefreshing(true);
    setLoadError("");
    if (previous !== null) {
      const checkingStatus = {
        ...previous,
        state: "checking" as const,
        message: "正在检查可用的后端版本…",
        error: null,
      };
      statusRef.current = checkingStatus;
      setStatus(checkingStatus);
    }
    try {
      applyStatus(await api.checkBackendUpdate());
    } catch (error) {
      if (previous !== null) {
        statusRef.current = previous;
        setStatus(previous);
      }
      message.error(error instanceof Error ? error.message : "检查后端更新失败");
    } finally {
      setRefreshing(false);
    }
  };

  const startUpdate = async () => {
    const current = statusRef.current;
    if (current?.state !== "available" || !current.candidateId || !current.canUpdate) return;

    const requestId = createRequestId();
    writeStoredValue(UPDATE_REQUEST_STORAGE_KEY, requestId);
    setStarting(true);
    setLoadError("");
    try {
      const accepted = await api.startBackendUpdate({
        candidateId: current.candidateId,
        requestId,
      });
      if (!accepted.accepted) throw new Error("后端未接受升级任务");
      writeStoredValue(UPDATE_JOB_STORAGE_KEY, accepted.jobId);
      applyStatus({
        ...current,
        state: "queued",
        currentVersion: accepted.fromVersion,
        targetVersion: accepted.targetVersion ?? current.targetVersion,
        jobId: accepted.jobId,
        startedAt: new Date().toISOString(),
        finishedAt: null,
        message: accepted.disconnectExpected
          ? "升级任务已提交，服务即将暂时断开。"
          : "升级任务已提交。",
        blockedReason: null,
        error: null,
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 0) {
        confirmingStartRef.current = true;
        setConfirmingStart(true);
        setConnectionInterrupted(true);
      } else {
        clearStoredUpdate();
        message.error(error instanceof Error ? error.message : "启动后端升级失败");
      }
    } finally {
      setStarting(false);
    }
  };

  if (loading && status === null) {
    return (
      <div className="content-loading backend-upgrade-loading">
        <Spin size="large" />
        <span>正在读取后端升级状态…</span>
      </div>
    );
  }

  if (status === null && confirmingStart) {
    return (
      <div className="page-stack backend-upgrade-page">
        <Alert
          className="backend-upgrade-connection-alert"
          type="warning"
          showIcon
          title="连接已中断，正在确认升级状态"
          description="管理台会每 2 秒重新连接后端。服务恢复后将继续显示升级结果，请勿重复提交。"
        />
        <div className="content-loading backend-upgrade-loading">
          <Spin size="large" />
          <span>正在等待后端服务恢复…</span>
        </div>
      </div>
    );
  }

  if (status === null) {
    return (
      <Alert
        type="error"
        showIcon
        title="无法读取后端升级状态"
        description={loadError || "请确认后端服务正在运行。"}
        action={<Button onClick={() => void loadStatus()}>重试</Button>}
      />
    );
  }

  const presentation = statePresentation[status.state];
  const busy = starting || confirmingStart || activeStates.has(status.state);
  const canStart = status.state === "available"
    && status.canUpdate
    && Boolean(status.candidateId)
    && !busy;
  const targetLabel = status.targetVersion
    ? `v${status.targetVersion}`
    : status.candidateId
      ? `提交 ${status.candidateId.slice(0, 12)}`
      : "待检查";

  return (
    <div className="page-stack backend-upgrade-page">
      {confirmingStart ? (
        <Alert
          className="backend-upgrade-connection-alert"
          type="warning"
          showIcon
          title="连接已中断，正在确认升级状态"
          description="启动请求可能已由服务器接收。管理台会每 2 秒重新连接，请勿重复提交升级。"
        />
      ) : connectionInterrupted ? (
        <Alert
          className="backend-upgrade-connection-alert"
          type="warning"
          showIcon
          title="后端服务暂时无法连接"
          description="升级期间服务会短暂离线；管理台正在等待服务恢复并继续验证结果。"
        />
      ) : null}

      {activeTaskCount > 0 && status.state === "available" && (
        <Alert
          type="warning"
          showIcon
          title={`当前有 ${activeTaskCount} 个任务正在排队或运行`}
          description="升级会重启后端服务。建议等待当前下载与翻译任务结束后再继续。"
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            className="panel-card backend-upgrade-card"
            title={(
              <Space>
                <CloudDownloadOutlined />
                <span>Linux 后端版本</span>
              </Space>
            )}
            extra={<Tag color={presentation.color}>{presentation.label}</Tag>}
          >
            <div className="backend-upgrade-version-row">
              <div>
                <Typography.Text type="secondary">当前版本</Typography.Text>
                <Typography.Title level={3}>v{status.currentVersion}</Typography.Title>
              </div>
              <div className="backend-upgrade-version-arrow" aria-hidden="true">→</div>
              <div>
                <Typography.Text type="secondary">目标版本</Typography.Text>
                <Typography.Title
                  level={3}
                  type={status.targetVersion || status.candidateId ? undefined : "secondary"}
                >
                  {targetLabel}
                </Typography.Title>
              </div>
            </div>

            <Steps
              className="backend-upgrade-steps"
              size="small"
              current={upgradeStep(status.state)}
              status={status.state === "failed" ? "error" : status.state === "completed" ? "finish" : "process"}
              items={[
                { title: "检查更新" },
                { title: "下载并安装" },
                { title: "重启服务" },
                { title: "验证版本" },
              ]}
            />

            <UpdateStateAlert status={status} />

            <Space className="backend-upgrade-actions" wrap>
              {!busy && status.state !== "completed" && status.state !== "unsupported" && (
                <Button
                  icon={<SyncOutlined />}
                  loading={refreshing}
                  onClick={() => void checkForUpdate()}
                  aria-label="检查后端更新"
                >
                  {status.state === "failed" ? "重新检查" : "检查更新"}
                </Button>
              )}
              {status.state === "available" && (
                <Popconfirm
                  title={status.targetVersion
                    ? `升级到 v${status.targetVersion}？`
                    : "安装已检查到的后端更新？"}
                  description="升级会暂时中断管理界面和客户端连接，服务恢复后管理台将自动验证结果。"
                  okText="确认升级"
                  cancelText="取消"
                  okButtonProps={{ loading: starting }}
                  onConfirm={() => startUpdate()}
                >
                  <Button
                    type="primary"
                    icon={<CloudDownloadOutlined />}
                    loading={starting}
                    disabled={!canStart}
                    aria-label="执行后端升级"
                  >
                    立即升级
                  </Button>
                </Popconfirm>
              )}
              {status.state === "completed" && (
                <Button
                  type="primary"
                  icon={<ReloadOutlined />}
                  onClick={onReload}
                  aria-label="刷新管理台"
                >
                  刷新管理台
                </Button>
              )}
            </Space>
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card className="panel-card backend-upgrade-detail-card" title="升级信息">
            <Descriptions column={1} size="small" colon={false}>
              <Descriptions.Item label="当前版本">v{status.currentVersion}</Descriptions.Item>
              <Descriptions.Item label="目标版本">
                {targetLabel}
              </Descriptions.Item>
              <Descriptions.Item label="最近检查">{formatUpdateDate(status.checkedAt)}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatUpdateDate(status.startedAt)}</Descriptions.Item>
              <Descriptions.Item label="完成时间">{formatUpdateDate(status.finishedAt)}</Descriptions.Item>
              <Descriptions.Item label="任务 ID">
                <Typography.Text copyable={Boolean(status.jobId)} ellipsis>
                  {status.jobId ?? readStoredValue(UPDATE_JOB_STORAGE_KEY) ?? "–"}
                </Typography.Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card className="panel-card backend-upgrade-note-card" variant="borderless">
            <Space align="start">
              <WarningOutlined className="backend-upgrade-note-icon" />
              <div>
                <Typography.Text strong>升级期间请保持页面打开</Typography.Text>
                <Typography.Paragraph type="secondary">
                  服务重启时出现短暂断线属于正常现象。请勿刷新、重复点击升级或手动重启服务。
                </Typography.Paragraph>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}

function UpdateStateAlert({ status }: { status: BackendUpdateStatus }) {
  if (status.state === "unsupported" || !status.supported) {
    return (
      <Alert
        type="warning"
        showIcon
        title="当前安装方式不支持网页升级"
        description={status.blockedReason || status.message || "请按照部署文档在服务器终端手动升级。"}
      />
    );
  }
  if (status.state === "failed") {
    return (
      <Alert
        type="error"
        showIcon
        title="后端升级失败"
        description={status.message || status.error || "请查看运行日志并重新检查更新。"}
      />
    );
  }
  if (status.state === "completed") {
    return (
      <Alert
        type="success"
        showIcon
        icon={<CheckCircleOutlined />}
        title="后端升级完成"
        description={status.message || "服务已恢复，请刷新管理台加载最新资源。"}
      />
    );
  }
  if (status.blockedReason) {
    return <Alert type="warning" showIcon title="暂时不能升级" description={status.blockedReason} />;
  }
  if (status.state === "available") {
    return (
      <Alert
        type="info"
        showIcon
        title={status.targetVersion
          ? `可以升级到 v${status.targetVersion}`
          : "检测到可用的后端更新"}
        description={status.message || "确认后将下载更新并重启后端服务。"}
      />
    );
  }
  if (status.state === "up_to_date") {
    return <Alert type="success" showIcon title="当前后端已是最新版本" description={status.message} />;
  }
  if (activeStates.has(status.state)) {
    return (
      <Alert
        type={status.state === "restarting" ? "warning" : "info"}
        showIcon
        title={statePresentation[status.state].label}
        description={status.message || "升级正在进行，请勿重复操作。"}
      />
    );
  }
  return (
    <Alert
      type="info"
      showIcon
      title="检查后端更新"
      description={status.message || "检查服务器当前分支是否有可用的新版本。"}
    />
  );
}

function upgradeStep(state: BackendUpdateState): number {
  if (state === "queued" || state === "updating" || state === "failed") return 1;
  if (state === "restarting") return 2;
  if (state === "verifying" || state === "completed") return 3;
  return 0;
}

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `update-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function readStoredValue(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStoredValue(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // The update can still proceed when browser storage is unavailable.
  }
}

function clearStoredUpdate(): void {
  try {
    window.sessionStorage.removeItem(UPDATE_REQUEST_STORAGE_KEY);
    window.sessionStorage.removeItem(UPDATE_JOB_STORAGE_KEY);
  } catch {
    // Ignore unavailable browser storage.
  }
}

function formatUpdateDate(value: string | null): string {
  if (!value) return "–";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "–";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}
