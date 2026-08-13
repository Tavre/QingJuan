import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";

import { getServiceDiagnostics } from "../api";
import type { ServiceDiagnostics } from "../types";
import { createDiagnosticsReport, DiagnosticsPage } from "./DiagnosticsPage";

vi.mock("../api", () => ({
  getServiceDiagnostics: vi.fn(),
}));

const mockedGetServiceDiagnostics = vi.mocked(getServiceDiagnostics);

const diagnostics: ServiceDiagnostics = {
  schemaVersion: 1,
  status: "healthy",
  generatedAt: "2030-01-01T01:02:03Z",
  startedAt: "2030-01-01T00:00:00Z",
  uptimeSeconds: 3723,
  runtime: {
    pythonVersion: "3.13.4",
    operatingSystem: "Linux",
    architecture: "x86_64",
  },
  requests: {
    total: 120,
    successful: 116,
    clientErrors: 4,
    serverErrors: 0,
    averageDurationMs: 18.2,
    p95DurationMs: 42.8,
    sampleSize: 120,
  },
  storage: {
    totalBytes: 100 * 1024 ** 3,
    usedBytes: 40 * 1024 ** 3,
    freeBytes: 60 * 1024 ** 3,
    databaseBytes: 2 * 1024 ** 2,
    runtimeLogsBytes: 512 * 1024,
  },
  workload: {
    books: 8,
    tasks: 20,
    queuedTasks: 1,
    runningTasks: 1,
    failedTasks: 2,
    pendingQueueItems: 1,
    devices: 3,
    onlineDevices: 2,
  },
  checks: [
    {
      key: "database",
      label: "SQLite 数据库",
      status: "healthy",
      detail: "数据库连接与业务统计读取正常",
    },
    {
      key: "disk-space",
      label: "数据卷空间",
      status: "healthy",
      detail: "数据卷剩余 60.0 GB",
    },
  ],
  recentIssues: [
    {
      timestamp: "2030-01-01T00:58:00Z",
      level: "warning",
      source: "qingjuan.scraper",
      message: "抓取器回退到网页解析",
    },
  ],
};

describe("system diagnostics", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetServiceDiagnostics.mockResolvedValue(diagnostics);
  });

  it("shows health, resource and issue details and supports manual refresh", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <DiagnosticsPage onOpenLogs={vi.fn()} />
      </App>,
    );

    expect(await screen.findByText("数据库连接与业务统计读取正常")).toBeInTheDocument();
    expect(screen.getByText("抓取器回退到网页解析")).toBeInTheDocument();
    expect(screen.getByText("60.0 GB")).toBeInTheDocument();
    expect(screen.getAllByText("运行正常").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "刷新诊断" }));
    await waitFor(() => expect(mockedGetServiceDiagnostics).toHaveBeenCalledTimes(2));
  });

  it("builds a report from the safe diagnostics DTO only", () => {
    const report = createDiagnosticsReport(diagnostics);
    const serialized = JSON.stringify(report).toLocaleLowerCase();

    expect(Object.keys(report)).toEqual(["reportVersion", "product", "exportedAt", "diagnostics"]);
    expect(report.reportVersion).toBe(1);
    expect(report.product).toBe("QingJuan");
    expect(report.diagnostics).toBe(diagnostics);
    expect(serialized).not.toContain("password");
    expect(serialized).not.toContain("token");
    expect(serialized).not.toContain("path");
  });
});
