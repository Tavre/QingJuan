import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";

import { checkTranslationModel } from "../api";
import type { Settings } from "../types";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api", () => ({
  checkTranslationModel: vi.fn(),
}));

const mockedCheckTranslationModel = vi.mocked(checkTranslationModel);

const settings: Settings = {
  systemPrompt: "请准确翻译。",
  autoTranslateNextChapters: 2,
  downloadConcurrency: 3,
  translationModel: {
    enabled: true,
    baseUrl: "https://models.example.test/v1",
    model: "server-model",
    supportsVision: false,
    apiKeyConfigured: true,
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
};

describe("translation model settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedCheckTranslationModel.mockResolvedValue({
      enabled: true,
      configured: true,
      available: true,
      status: "ready",
      model: "server-model",
      supportsVision: false,
      checkedAt: "2030-01-01T00:00:00Z",
      latencyMs: 18,
      message: "Linux 服务端翻译模型自检通过",
      cached: false,
    });
  });

  it("shows the server check and supports an administrator forced check", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <App>
        <SettingsPage settings={settings} onSave={vi.fn()} />
      </App>,
    );

    expect(container.querySelector(".model-credentials-row")).toHaveClass("ant-row-top");
    expect(await screen.findByText("Linux 服务端模型可用")).toBeInTheDocument();
    expect(screen.getByText("server-model · 18 ms · 仅文本")).toBeInTheDocument();
    expect(mockedCheckTranslationModel).toHaveBeenCalledWith(false);

    await user.click(screen.getByRole("button", { name: "模型自检" }));
    await waitFor(() => expect(mockedCheckTranslationModel).toHaveBeenLastCalledWith(true));
  });

  it("forces a fresh model check after saving configuration", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <App>
        <SettingsPage settings={settings} onSave={onSave} />
      </App>,
    );

    await screen.findByText("Linux 服务端模型可用");
    await user.click(screen.getByRole("button", { name: "保存全部设置" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    await waitFor(() => expect(mockedCheckTranslationModel).toHaveBeenLastCalledWith(true));
  });
});
