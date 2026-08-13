import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

import type { Device } from "../types";
import { DevicesPage } from "./DevicesPage";

const devices: Device[] = [
  {
    id: "0123456789abcdef0123456789abcdef",
    name: "客厅电脑",
    platform: "windows",
    ipAddress: "192.168.1.20",
    firstSeenAt: "2030-01-01T08:00:00Z",
    lastSeenAt: "2030-01-01T09:00:00Z",
    banned: false,
    bannedAt: null,
    online: true,
  },
  {
    id: "abcdef0123456789abcdef0123456789",
    name: "旧手机",
    platform: "android",
    ipAddress: "192.168.1.21",
    firstSeenAt: "2030-01-01T07:00:00Z",
    lastSeenAt: "2030-01-01T07:30:00Z",
    banned: true,
    bannedAt: "2030-01-01T07:31:00Z",
    online: false,
  },
];

describe("DevicesPage", () => {
  it("shows registered and online device counts", () => {
    render(
      <App>
        <DevicesPage devices={devices} onSetBanned={vi.fn()} />
      </App>,
    );

    expect(screen.getByText("在线 1 / 共 2 台")).toBeInTheDocument();
    expect(screen.getByText("客厅电脑")).toBeInTheDocument();
    expect(screen.getByText("旧手机")).toBeInTheDocument();
    expect(screen.getByText("已封禁")).toBeInTheDocument();
  });

  it("confirms a device ban before applying it", async () => {
    const user = userEvent.setup();
    const onSetBanned = vi.fn().mockResolvedValue(undefined);
    render(
      <App>
        <DevicesPage devices={devices} onSetBanned={onSetBanned} />
      </App>,
    );

    await user.click(screen.getByRole("button", { name: "封禁 客厅电脑" }));
    await user.click(await screen.findByRole("button", { name: "确认封禁" }));

    await waitFor(() => expect(onSetBanned).toHaveBeenCalledWith(devices[0].id, true));
  });
});
