import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

import { getRuntimeLogs, revealConnectionToken } from "../api";
import { ConnectionTokenPanel } from "./ConnectionTokenPanel";
import { LogsPage } from "./LogsPage";

vi.mock("../api", () => ({
  getRuntimeLogs: vi.fn(),
  revealConnectionToken: vi.fn(),
}));

const mockedGetRuntimeLogs = vi.mocked(getRuntimeLogs);
const mockedRevealConnectionToken = vi.mocked(revealConnectionToken);

describe("admin observability", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("reveals the connection token only after an explicit action", async () => {
    const user = userEvent.setup();
    mockedRevealConnectionToken.mockResolvedValue({ token: "full-connection-token-value" });
    render(
      <App>
        <ConnectionTokenPanel
          status={{
            configured: true,
            revealAvailable: true,
            maskedToken: "full-c••••••••-value",
            fingerprint: "0123456789ab",
          }}
        />
      </App>,
    );

    expect(screen.queryByText("full-connection-token-value")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "显示后端 API 密钥" }));
    expect(await screen.findByText("full-connection-token-value")).toBeInTheDocument();
    expect(mockedRevealConnectionToken).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "隐藏后端 API 密钥" }));
    expect(screen.queryByText("full-connection-token-value")).not.toBeInTheDocument();
  });

  it("loads detailed server logs and filters their content", async () => {
    const user = userEvent.setup();
    mockedGetRuntimeLogs.mockResolvedValue({
      total: 2,
      sources: ["qingjuan.scraper", "uvicorn.access"],
      items: [
        {
          timestamp: "2030-01-01T00:00:00Z",
          level: "warning",
          source: "qingjuan.scraper",
          message: "抓取器回退到网页解析",
        },
        {
          timestamp: "2030-01-01T00:01:00Z",
          level: "info",
          source: "uvicorn.access",
          message: "GET /api/v1/meta 200",
        },
      ],
    });
    render(
      <App>
        <LogsPage />
      </App>,
    );

    expect(await screen.findByText("抓取器回退到网页解析")).toBeInTheDocument();
    expect(screen.getByText("GET /api/v1/meta 200")).toBeInTheDocument();
    expect(mockedGetRuntimeLogs).toHaveBeenCalledWith(1000);

    await user.type(screen.getByPlaceholderText("搜索日志内容或来源"), "抓取器");
    await waitFor(() => expect(screen.queryByText("GET /api/v1/meta 200")).not.toBeInTheDocument());
    expect(screen.getByText("抓取器回退到网页解析")).toBeInTheDocument();
  });
});
