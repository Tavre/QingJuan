import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";

import { getRegistrationSettings, updateRegistrationSettings } from "../api";
import type { RegistrationSettings } from "../types";
import { RegistrationSettingsPage } from "./RegistrationSettingsPage";

vi.mock("../api", () => ({
  getRegistrationSettings: vi.fn(),
  updateRegistrationSettings: vi.fn(),
}));

const mockedGetRegistrationSettings = vi.mocked(getRegistrationSettings);
const mockedUpdateRegistrationSettings = vi.mocked(updateRegistrationSettings);

const emptySettings: RegistrationSettings = {
  registration: {
    emailRequired: true,
    emailVerificationRequired: false,
    identityBadgeRequired: false,
    identityBadgeConfigured: false,
  },
  smtp: {
    host: "",
    port: 587,
    security: "starttls",
    username: "",
    fromAddress: "",
    fromName: "青卷",
    passwordConfigured: false,
    configured: false,
  },
  github: {
    enabled: false,
    clientId: "",
    configured: false,
  },
};

function renderPage() {
  return render(
    <App>
      <RegistrationSettingsPage />
    </App>,
  );
}

describe("registration settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetRegistrationSettings.mockResolvedValue(emptySettings);
    mockedUpdateRegistrationSettings.mockResolvedValue({
      registration: {
        emailRequired: true,
        emailVerificationRequired: true,
        identityBadgeRequired: true,
        identityBadgeConfigured: true,
      },
      smtp: {
        host: "smtp.example.test",
        port: 587,
        security: "starttls",
        username: "",
        fromAddress: "noreply@example.test",
        fromName: "青卷",
        passwordConfigured: false,
        configured: true,
      },
      github: {
        enabled: false,
        clientId: "",
        configured: false,
      },
    });
  });

  it("supports both registration checks and submits the nested SMTP contract", async () => {
    renderPage();

    expect(await screen.findByText("当前允许直接注册")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "启用邮箱验证码注册" }));
    expect(await screen.findByText("注册需要邮箱验证码")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "启用身份牌注册" }));

    expect(await screen.findByText("注册必须同时通过两项判断")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("SMTP 服务器"), { target: { value: "smtp.example.test" } });
    fireEvent.change(screen.getByLabelText("发件邮箱"), { target: { value: "noreply@example.test" } });
    fireEvent.change(screen.getByLabelText("固定身份牌"), { target: { value: "invite-badge-2026" } });
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    await waitFor(() => expect(mockedUpdateRegistrationSettings).toHaveBeenCalledOnce());
    expect(mockedUpdateRegistrationSettings).toHaveBeenCalledWith({
      emailVerificationRequired: true,
      identityBadgeRequired: true,
      smtp: {
        host: "smtp.example.test",
        port: 587,
        security: "starttls",
        username: "",
        fromAddress: "noreply@example.test",
        fromName: "青卷",
      },
      github: {
        enabled: false,
        clientId: "",
      },
      smtpPasswordAction: "keep",
      identityBadgeAction: "replace",
      identityBadge: "invite-badge-2026",
    });
  });

  it("blocks enabled checks until their required configuration is provided", async () => {
    renderPage();

    await screen.findByText("当前允许直接注册");
    fireEvent.click(screen.getByRole("switch", { name: "启用邮箱验证码注册" }));
    expect(await screen.findByText("注册需要邮箱验证码")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "启用身份牌注册" }));
    expect(await screen.findByText("注册必须同时通过两项判断")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    expect(await screen.findByText("请输入 SMTP 服务器")).toBeInTheDocument();
    expect(screen.getByText("请输入发件邮箱")).toBeInTheDocument();
    expect(screen.getByText("启用身份牌注册前必须设置固定身份牌")).toBeInTheDocument();
    expect(mockedUpdateRegistrationSettings).not.toHaveBeenCalled();
  });

  it("never echoes saved secrets and keeps them when secret inputs stay empty", async () => {
    const configuredSettings: RegistrationSettings = {
      registration: {
        emailRequired: true,
        emailVerificationRequired: true,
        identityBadgeRequired: true,
        identityBadgeConfigured: true,
      },
      smtp: {
        host: "smtp.example.test",
        port: 465,
        security: "ssl",
        username: "mailer@example.test",
        fromAddress: "mailer@example.test",
        fromName: "青卷",
        passwordConfigured: true,
        configured: true,
      },
      github: {
        enabled: true,
        clientId: "Iv1.configured-client",
        configured: true,
      },
    };
    mockedGetRegistrationSettings.mockResolvedValue(configuredSettings);
    mockedUpdateRegistrationSettings.mockResolvedValue(configuredSettings);
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const { container } = renderPage();

    expect(await screen.findByText("注册必须同时通过两项判断")).toBeInTheDocument();
    expect(screen.getAllByText("已保存")).toHaveLength(2);
    expect(container.textContent).not.toContain("saved-smtp-secret");
    expect(container.textContent).not.toContain("saved-identity-badge");
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    await waitFor(() => expect(mockedUpdateRegistrationSettings).toHaveBeenCalledOnce());
    expect(mockedUpdateRegistrationSettings).toHaveBeenCalledWith(expect.objectContaining({
      smtpPasswordAction: "keep",
      identityBadgeAction: "keep",
    }));
    const payload = mockedUpdateRegistrationSettings.mock.calls[0][0];
    expect(payload).not.toHaveProperty("smtpPassword");
    expect(payload).not.toHaveProperty("identityBadge");
    expect(storageSpy).not.toHaveBeenCalled();
  });

  it("blocks authenticated SMTP over an unencrypted connection", async () => {
    mockedGetRegistrationSettings.mockResolvedValue({
      ...emptySettings,
      smtp: {
        ...emptySettings.smtp,
        security: "none",
        username: "mailer@example.test",
      },
    });
    renderPage();

    expect(await screen.findByText("SMTP 连接未加密")).toBeInTheDocument();
    expect(screen.getByText(/请勿通过明文连接发送认证账号或密码/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    expect(await screen.findByText("无加密仅用于无需认证的本地 SMTP Relay")).toBeInTheDocument();
    expect(mockedUpdateRegistrationSettings).not.toHaveBeenCalled();
  });

  it("requires and trims the GitHub OAuth App Client ID before enabling Device Flow", async () => {
    renderPage();

    await screen.findByText("当前允许直接注册");
    expect(screen.getByText("不会自动创建本地账号")).toBeInTheDocument();
    expect(screen.getByText(/GitHub 创建表单若要求填写/)).toHaveTextContent(
      "用户只应在 github.com/login/device 输入设备码",
    );
    fireEvent.click(screen.getByRole("switch", { name: "启用 GitHub 登录" }));
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));
    expect(await screen.findByText("请输入 GitHub OAuth App Client ID")).toBeInTheDocument();
    expect(mockedUpdateRegistrationSettings).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("GitHub OAuth App Client ID"), {
      target: { value: "  Iv1.device-flow-client  " },
    });
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    await waitFor(() => expect(mockedUpdateRegistrationSettings).toHaveBeenCalledOnce());
    expect(mockedUpdateRegistrationSettings).toHaveBeenCalledWith(expect.objectContaining({
      github: {
        enabled: true,
        clientId: "Iv1.device-flow-client",
      },
    }));
  });

  it("validates a staged identity badge before its registration check is enabled", async () => {
    renderPage();

    await screen.findByText("当前允许直接注册");
    fireEvent.change(screen.getByLabelText("固定身份牌"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: /保存注册设置/ }));

    expect(await screen.findByText("固定身份牌需要 8–128 个字符")).toBeInTheDocument();
    expect(mockedUpdateRegistrationSettings).not.toHaveBeenCalled();
  });
});
