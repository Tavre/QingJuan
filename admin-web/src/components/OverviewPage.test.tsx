import { fireEvent, render, screen } from "@testing-library/react";
import { App } from "antd";

import type { DashboardData } from "../types";
import { OverviewPage } from "./OverviewPage";

const dashboard: DashboardData = {
  meta: {
    service: "qingjuan-backend",
    appVersion: "2.0.0",
    apiVersion: "1",
    instanceId: "0123456789abcdef",
    capabilities: {},
  },
  connectionToken: {
    configured: true,
    revealAvailable: false,
    maskedToken: "qing…juan",
    fingerprint: "abcdef12",
  },
  devices: [],
  books: [],
  tasks: [],
  sources: [],
  plugins: [],
  settings: {
    systemPrompt: "",
    autoTranslateNextChapters: 0,
    downloadConcurrency: 2,
    translationModel: {
      enabled: false,
      baseUrl: "",
      model: "",
      supportsVision: false,
      apiKeyConfigured: false,
    },
    mangaOcr: {
      enabled: false,
      baseUrl: "",
      apiKeyConfigured: false,
    },
    bika: {
      emailConfigured: false,
      passwordConfigured: false,
    },
  },
};

describe("OverviewPage", () => {
  it("opens backend upgrade from the service information shortcut", () => {
    const onNavigate = vi.fn();
    render(
      <App>
        <OverviewPage data={dashboard} bookTitles={new Map()} onNavigate={onNavigate} />
      </App>,
    );

    fireEvent.click(screen.getByRole("button", { name: "后端升级" }));
    expect(onNavigate).toHaveBeenCalledWith("upgrade");
  });
});
