import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";

import * as api from "../api";
import type { SitePlugin } from "../types";
import { PluginsPage } from "./PluginsPage";

const plugins: SitePlugin[] = [
  {
    id: "fanqie",
    name: "番茄小说",
    description: "解析作品目录与章节正文。",
    category: "novel",
    domains: ["fanqienovel.com"],
    bookKinds: ["长小说"],
    tags: ["中文", "连载"],
    capabilities: ["preview", "chapter", "search", "account_login", "cookie_login", "bookshelf_import"],
    version: "1.1.0",
    enabled: true,
    defaultEnabled: true,
    accountLoggedIn: false,
  },
  {
    id: "bika",
    name: "哔咔漫画",
    description: "解析漫画作品与图片章节。",
    category: "manga",
    domains: ["bika.example"],
    bookKinds: ["漫画"],
    tags: ["中文", "漫画"],
    capabilities: ["preview", "chapter"],
    version: "1.1.0",
    enabled: false,
    defaultEnabled: true,
    accountLoggedIn: false,
  },
];

describe("PluginsPage", () => {
  it("searches plugin metadata and saves an enable change", async () => {
    const user = userEvent.setup();
    const onSetEnabled = vi.fn().mockResolvedValue(undefined);
    render(
      <App>
        <PluginsPage plugins={plugins} onSetEnabled={onSetEnabled} />
      </App>,
    );

    expect(screen.getByText("番茄小说")).toBeInTheDocument();
    expect(screen.getByText("哔咔漫画")).toBeInTheDocument();
    expect(screen.getByText("fanqienovel.com")).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("搜索插件名称、ID、域名或标签"),
      "bika.example",
    );
    expect(screen.queryByText("番茄小说")).not.toBeInTheDocument();
    expect(screen.getByText("哔咔漫画")).toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "哔咔漫画插件" }));
    await waitFor(() => expect(onSetEnabled).toHaveBeenCalledWith("bika", true));
  });

  it("filters disabled plugins and reports save failures", async () => {
    const user = userEvent.setup();
    const onSetEnabled = vi.fn().mockRejectedValue(new Error("插件状态保存失败"));
    render(
      <App>
        <PluginsPage plugins={plugins} onSetEnabled={onSetEnabled} />
      </App>,
    );

    await user.click(screen.getByText("已停用 1"));
    expect(screen.queryByText("番茄小说")).not.toBeInTheDocument();
    expect(screen.getByText("哔咔漫画")).toBeInTheDocument();

    await user.click(screen.getByRole("switch", { name: "哔咔漫画插件" }));
    expect(await screen.findByText("插件状态保存失败")).toBeInTheDocument();
  });

  it("submits a Cookie login without retaining the credential in the UI", async () => {
    const user = userEvent.setup();
    const onDataChanged = vi.fn().mockResolvedValue(undefined);
    const login = vi.spyOn(api, "loginSitePluginWithCookies").mockResolvedValue({
      loggedIn: true,
      expiresAt: null,
    });
    render(
      <App>
        <PluginsPage
          plugins={plugins}
          onSetEnabled={vi.fn().mockResolvedValue(undefined)}
          onDataChanged={onDataChanged}
        />
      </App>,
    );

    await user.click(screen.getByRole("button", { name: "Cookie 登录" }));
    const input = screen.getByLabelText("番茄小说 Cookie 请求头");
    await user.type(input, "sessionid=private-value");
    await user.click(screen.getByRole("button", { name: "验证并登录" }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("fanqie", "sessionid=private-value"));
    await waitFor(() => expect(onDataChanged).toHaveBeenCalledTimes(1));
    expect(screen.queryByDisplayValue("sessionid=private-value")).not.toBeInTheDocument();
  });

  it("enables Qidian one-click bookshelf import only after account login", () => {
    const qidian: SitePlugin = {
      id: "qidian",
      name: "起点读书",
      description: "解析起点作品并添加当前账号书架。",
      category: "novel",
      domains: ["qidian.com"],
      bookKinds: ["长小说", "轻小说"],
      tags: ["中文", "账号书架"],
      capabilities: ["preview", "chapter", "on_demand", "account_login", "bookshelf_import"],
      version: "1.0.0",
      enabled: true,
      defaultEnabled: true,
      accountLoggedIn: false,
    };
    const view = render(
      <App>
        <PluginsPage plugins={[qidian]} onSetEnabled={vi.fn().mockResolvedValue(undefined)} />
      </App>,
    );

    expect(screen.getByRole("button", { name: /扫码登录$/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /添加账号书架$/ })).toBeDisabled();

    view.rerender(
      <App>
        <PluginsPage
          plugins={[{ ...qidian, accountLoggedIn: true }]}
          onSetEnabled={vi.fn().mockResolvedValue(undefined)}
        />
      </App>,
    );

    expect(screen.queryByRole("button", { name: /扫码登录$/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /退出账号$/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /添加账号书架$/ })).toBeEnabled();
  });
});
