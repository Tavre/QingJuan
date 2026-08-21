import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

import * as api from "../api";
import { ApiError } from "../api";
import type { BackendUpdateStatus } from "../types";
import { BackendUpgradePage } from "./BackendUpgradePage";

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    checkBackendUpdate: vi.fn(),
    getBackendUpdateStatus: vi.fn(),
    startBackendUpdate: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

const availableStatus: BackendUpdateStatus = {
  schemaVersion: 1,
  state: "available",
  supported: true,
  canUpdate: true,
  currentVersion: "2.0.0",
  targetVersion: "2.1.0",
  candidateId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  jobId: null,
  checkedAt: "2030-01-01T00:00:00Z",
  startedAt: null,
  finishedAt: null,
  message: "发现稳定版本 2.1.0",
  blockedReason: null,
  error: null,
};

describe("BackendUpgradePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    mockedApi.getBackendUpdateStatus.mockResolvedValue(availableStatus);
    mockedApi.checkBackendUpdate.mockResolvedValue(availableStatus);
    mockedApi.startBackendUpdate.mockResolvedValue({
      accepted: true,
      jobId: "update-job-1",
      fromVersion: "2.0.0",
      targetVersion: "2.1.0",
      disconnectExpected: true,
    });
  });

  it("shows an available update and starts it only after confirmation", async () => {
    render(
      <App>
        <BackendUpgradePage activeTaskCount={2} />
      </App>,
    );

    expect(await screen.findByText("发现稳定版本 2.1.0")).toBeInTheDocument();
    expect(screen.getByText("当前有 2 个任务正在排队或运行")).toBeInTheDocument();
    expect(screen.getAllByText("v2.0.0").length).toBeGreaterThan(0);
    expect(screen.getAllByText("v2.1.0").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "执行后端升级" }));
    expect(mockedApi.startBackendUpdate).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: "确认升级" }));

    await waitFor(() => expect(mockedApi.startBackendUpdate).toHaveBeenCalledWith({
      candidateId: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      requestId: expect.any(String),
    }));
    expect(window.sessionStorage.getItem("qingjuan-backend-update-request-id")).toBeTruthy();
    expect(window.sessionStorage.getItem("qingjuan-backend-update-job-id")).toBe("update-job-1");
    expect((await screen.findAllByText("等待升级")).length).toBeGreaterThan(0);
  });

  it("treats a disconnected start response as pending confirmation and resumes polling", async () => {
    let poll: (() => void) | undefined;
    const setIntervalSpy = vi.spyOn(window, "setInterval").mockImplementation((handler, delay) => {
      if (delay === 2_000) poll = handler as () => void;
      return 1 as unknown as ReturnType<typeof window.setInterval>;
    });
    mockedApi.startBackendUpdate.mockRejectedValueOnce(new ApiError("无法连接", 0));
    const onReload = vi.fn();
    render(
      <App>
        <BackendUpgradePage onReload={onReload} />
      </App>,
    );
    await screen.findByText("发现稳定版本 2.1.0");

    fireEvent.click(screen.getByRole("button", { name: "执行后端升级" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认升级" }));

    expect(await screen.findByText("连接已中断，正在确认升级状态")).toBeInTheDocument();
    await waitFor(() => expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), 2_000));
    expect(poll).toBeDefined();

    mockedApi.getBackendUpdateStatus.mockResolvedValueOnce({
      ...availableStatus,
      state: "completed",
      currentVersion: "2.1.0",
      jobId: "update-job-1",
      startedAt: "2030-01-01T00:01:00Z",
      finishedAt: "2030-01-01T00:02:00Z",
      message: "服务已升级并恢复运行",
    });
    await act(async () => {
      poll?.();
      await Promise.resolve();
    });

    expect(await screen.findByText("后端升级完成")).toBeInTheDocument();
    expect(screen.queryByText("连接已中断，正在确认升级状态")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新管理台" }));
    expect(onReload).toHaveBeenCalledOnce();
    expect(window.sessionStorage.getItem("qingjuan-backend-update-request-id")).toBeNull();
    expect(window.sessionStorage.getItem("qingjuan-backend-update-job-id")).toBeNull();
  });

  it("keeps polling active server states and tolerates a temporary outage", async () => {
    let poll: (() => void) | undefined;
    vi.spyOn(window, "setInterval").mockImplementation((handler, delay) => {
      if (delay === 2_000) poll = handler as () => void;
      return 1 as unknown as ReturnType<typeof window.setInterval>;
    });
    mockedApi.getBackendUpdateStatus.mockResolvedValueOnce({
      ...availableStatus,
      state: "restarting",
      jobId: "update-job-2",
      startedAt: "2030-01-01T00:01:00Z",
      message: "正在重启后端服务",
    });
    render(
      <App>
        <BackendUpgradePage />
      </App>,
    );

    expect(await screen.findByText("正在重启后端服务")).toBeInTheDocument();
    await waitFor(() => expect(poll).toBeDefined());
    mockedApi.getBackendUpdateStatus.mockRejectedValueOnce(new ApiError("无法连接", 0));
    await act(async () => {
      poll?.();
      await Promise.resolve();
    });

    expect(await screen.findByText("后端服务暂时无法连接")).toBeInTheDocument();
    expect(screen.getByText("正在重启后端服务")).toBeInTheDocument();
  });

  it("restores an interrupted confirmation from session storage after a page reload", async () => {
    let poll: (() => void) | undefined;
    vi.spyOn(window, "setInterval").mockImplementation((handler, delay) => {
      if (delay === 2_000) poll = handler as () => void;
      return 1 as unknown as ReturnType<typeof window.setInterval>;
    });
    window.sessionStorage.setItem("qingjuan-backend-update-request-id", "request-before-reload");
    mockedApi.getBackendUpdateStatus.mockRejectedValueOnce(new ApiError("服务正在重启", 0));
    render(
      <App>
        <BackendUpgradePage />
      </App>,
    );

    expect(await screen.findByText("正在等待后端服务恢复…")).toBeInTheDocument();
    await waitFor(() => expect(poll).toBeDefined());
    mockedApi.getBackendUpdateStatus.mockResolvedValueOnce({
      ...availableStatus,
      state: "completed",
      currentVersion: "2.1.0",
      targetVersion: "2.1.0",
      jobId: "update-job-after-reload",
      message: "服务已升级并恢复运行",
    });
    await act(async () => {
      poll?.();
      await Promise.resolve();
    });

    expect(await screen.findByRole("button", { name: "刷新管理台" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem("qingjuan-backend-update-request-id")).toBeNull();
  });

  it("shows a safe failure reason and allows checking again", async () => {
    mockedApi.getBackendUpdateStatus.mockResolvedValueOnce({
      ...availableStatus,
      state: "failed",
      canUpdate: false,
      jobId: "update-job-3",
      error: "UPDATE_INSTALL_FAILED",
      message: "安装依赖失败，请查看运行日志",
    });
    render(
      <App>
        <BackendUpgradePage />
      </App>,
    );

    expect(await screen.findByText("安装依赖失败，请查看运行日志")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "检查后端更新" }));
    await waitFor(() => expect(mockedApi.checkBackendUpdate).toHaveBeenCalledOnce());
    expect(await screen.findByText("发现稳定版本 2.1.0")).toBeInTheDocument();
  });
});
