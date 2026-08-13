import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@ant-design/icons", () => ({
  MoonOutlined: () => null,
  SunOutlined: () => null,
}));

vi.mock("antd", async () => {
  const React = await import("react");
  return {
    App: ({ children }: any) => React.createElement("div", null, children),
    Button: ({ icon: _icon, ...props }: any) => React.createElement("button", props),
    ConfigProvider: ({ children }: any) => React.createElement("div", null, children),
    Tooltip: ({ children }: any) => children,
    theme: { defaultAlgorithm: "light", darkAlgorithm: "dark" },
  };
});

import { AdminThemeProvider, initializeThemeMode, ThemeToggle } from "./theme";

describe("admin theme", () => {
  it("defaults to light and persists an explicit dark-mode switch", async () => {
    window.localStorage.clear();
    const initialMode = initializeThemeMode();
    expect(initialMode).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");

    const user = userEvent.setup();
    render(
      <AdminThemeProvider initialMode={initialMode}>
        <ThemeToggle />
      </AdminThemeProvider>,
    );

    await user.click(screen.getByRole("button", { name: "切换为深色模式" }));

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("dark"));
    expect(window.localStorage.getItem("qingjuan-admin-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "切换为浅色模式" })).toBeInTheDocument();
  });
});
