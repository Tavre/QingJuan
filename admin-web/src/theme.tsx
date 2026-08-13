import { MoonOutlined, SunOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { App as AntApp, Button, ConfigProvider, Tooltip, theme as antdTheme } from "antd";
import zhCN from "antd/locale/zh_CN";

export type ThemeMode = "light" | "dark";

const THEME_STORAGE_KEY = "qingjuan-admin-theme";

type ThemeModeContextValue = {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
};

const ThemeModeContext = createContext<ThemeModeContextValue>({
  mode: "light",
  setMode: () => undefined,
});

export function initializeThemeMode(): ThemeMode {
  let mode: ThemeMode = "light";
  try {
    if (window.localStorage.getItem(THEME_STORAGE_KEY) === "dark") mode = "dark";
  } catch {
    // Theme persistence is optional; authentication never depends on browser storage.
  }
  document.documentElement.dataset.theme = mode;
  return mode;
}

export function AdminThemeProvider({
  children,
  initialMode,
}: {
  children: ReactNode;
  initialMode: ThemeMode;
}) {
  const [mode, setMode] = useState<ThemeMode>(initialMode);

  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch {
      // The UI remains fully usable when storage is blocked.
    }
  }, [mode]);

  const themeConfig = useMemo(
    () => ({
      algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      token: {
        colorPrimary: "#1677ff",
        colorInfo: "#1677ff",
        colorSuccess: "#52c41a",
        colorWarning: "#faad14",
        colorError: "#ff4d4f",
        colorBgLayout: mode === "dark" ? "#0f0f0f" : "#f5f5f5",
        colorBgContainer: mode === "dark" ? "#141414" : "#ffffff",
        colorBorderSecondary: mode === "dark" ? "#303030" : "#f0f0f0",
        borderRadius: 8,
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif',
      },
      components: {
        Layout: {
          bodyBg: mode === "dark" ? "#0f0f0f" : "#f5f5f5",
          headerBg: mode === "dark" ? "#141414" : "#ffffff",
          siderBg: mode === "dark" ? "#141414" : "#ffffff",
        },
        Menu: {
          itemBg: "transparent",
          itemSelectedBg: mode === "dark" ? "#111a2c" : "#e6f4ff",
          itemSelectedColor: mode === "dark" ? "#69b1ff" : "#1677ff",
          itemHoverBg: mode === "dark" ? "#1f1f1f" : "#f5f5f5",
        },
        Card: {
          headerBg: "transparent",
        },
        Table: {
          headerBg: mode === "dark" ? "#1f1f1f" : "#fafafa",
          rowHoverBg: mode === "dark" ? "#1f1f1f" : "#fafafa",
          borderColor: mode === "dark" ? "#303030" : "#f0f0f0",
        },
        Button: {
          primaryShadow: "none",
        },
      },
    }),
    [mode],
  );

  return (
    <ThemeModeContext.Provider value={{ mode, setMode }}>
      <ConfigProvider locale={zhCN} theme={themeConfig}>
        <AntApp>{children}</AntApp>
      </ConfigProvider>
    </ThemeModeContext.Provider>
  );
}

export function ThemeToggle({ className }: { className?: string }) {
  const { mode, setMode } = useContext(ThemeModeContext);
  const nextMode = mode === "light" ? "dark" : "light";
  const label = `切换为${nextMode === "dark" ? "深色" : "浅色"}模式`;

  return (
    <Tooltip title={label}>
      <Button
        className={className}
        type="text"
        shape="circle"
        icon={mode === "light" ? <MoonOutlined /> : <SunOutlined />}
        aria-label={label}
        onClick={() => setMode(nextMode)}
      />
    </Tooltip>
  );
}
