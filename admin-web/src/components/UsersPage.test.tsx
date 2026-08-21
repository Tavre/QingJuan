import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "antd";

import * as api from "../api";
import type { UserAdminView } from "../types";
import { UsersPage } from "./UsersPage";

vi.mock("../api", () => ({
  createUser: vi.fn(),
  getUsers: vi.fn(),
  resetUserPassword: vi.fn(),
  revokeUserSessions: vi.fn(),
  updateUser: vi.fn(),
}));

const mockedApi = vi.mocked(api);

const adminUser: UserAdminView = {
  id: "user-admin",
  username: "admin",
  email: null,
  githubLogin: null,
  twoFactorEnabled: true,
  displayName: "系统管理员",
  role: "admin",
  isDefaultAdmin: true,
  status: "active",
  createdAt: "2030-01-01T00:00:00Z",
  lastLoginAt: "2030-01-02T00:00:00Z",
  bookCount: 3,
};

const readerUser: UserAdminView = {
  id: "reader-user",
  username: "reader",
  email: "reader@example.test",
  githubLogin: "reader-octocat",
  twoFactorEnabled: false,
  displayName: "阅读者",
  role: "user",
  isDefaultAdmin: false,
  status: "active",
  createdAt: "2030-02-01T00:00:00Z",
  lastLoginAt: null,
  bookCount: 8,
};

describe("UsersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.getUsers.mockResolvedValue([adminUser, readerUser]);
    mockedApi.createUser.mockResolvedValue(readerUser);
    mockedApi.updateUser.mockResolvedValue({ ...readerUser, status: "disabled" });
    mockedApi.resetUserPassword.mockResolvedValue(undefined);
    mockedApi.revokeUserSessions.mockResolvedValue(undefined);
  });

  it("loads independently, searches users, and never offers to disable the administrator", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <UsersPage />
      </App>,
    );

    expect(await screen.findByText("系统管理员")).toBeInTheDocument();
    expect(screen.getByText("阅读者")).toBeInTheDocument();
    expect(screen.getByText("reader@example.test")).toBeInTheDocument();
    expect(screen.getAllByLabelText("GitHub 已绑定 @reader-octocat").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("两步验证已启用").length).toBeGreaterThan(0);
    const mobileSecurity = document.querySelectorAll(".user-mobile-security");
    expect(Array.from(mobileSecurity).some((node) => (
      node.textContent?.includes("GitHub @reader-octocat")
      && node.textContent.includes("2FA 未启用")
    ))).toBe(true);
    expect(mockedApi.getUsers).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "系统管理员 是管理员，不能停用" })).toBeDisabled();
    expect(screen.getByRole("button", {
      name: "系统管理员 是管理员，不能在此重置密码",
    })).toBeDisabled();
    expect(screen.getByRole("button", {
      name: "系统管理员 是内置管理员，不能降权",
    })).toBeDisabled();

    const search = screen.getByPlaceholderText("搜索用户名、邮箱、GitHub 或显示名称");
    await user.type(search, "reader");
    expect(screen.queryByText("系统管理员")).not.toBeInTheDocument();
    expect(screen.getByText("阅读者")).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "reader-octocat");
    expect(screen.getByText("阅读者")).toBeInTheDocument();
  });

  it("edits the built-in administrator display name without exposing protected fields", async () => {
    const user = userEvent.setup();
    mockedApi.updateUser.mockResolvedValueOnce({
      ...adminUser,
      displayName: "青卷管理员",
    });
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("系统管理员");

    await user.click(screen.getByRole("button", { name: "编辑 系统管理员 的账号资料" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("正在修改内置管理员资料")).toBeInTheDocument();
    expect(within(dialog).getByDisplayValue("admin")).toBeDisabled();
    expect(within(dialog).getByPlaceholderText("—")).toBeDisabled();
    const displayName = within(dialog).getByLabelText("显示名称");
    await user.clear(displayName);
    await user.type(displayName, " 青卷管理员 ");
    await user.click(within(dialog).getByRole("button", { name: "保存账号资料" }));

    await waitFor(() => expect(mockedApi.updateUser).toHaveBeenCalledWith("user-admin", {
      displayName: "青卷管理员",
    }));
    expect(await screen.findByText("青卷管理员")).toBeInTheDocument();
  });

  it("promotes a trusted active user after confirmation", async () => {
    mockedApi.updateUser.mockResolvedValueOnce({ ...readerUser, role: "admin" });
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("阅读者");

    fireEvent.click(screen.getByRole("button", { name: "提升 阅读者 的权限" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认提权" }));

    await waitFor(() => expect(mockedApi.updateUser).toHaveBeenCalledWith("reader-user", {
      role: "admin",
    }));
  });

  it("demotes a non-default administrator after confirmation", async () => {
    const delegatedAdmin: UserAdminView = {
      ...readerUser,
      id: "delegated-admin",
      username: "operator",
      displayName: "次级管理员",
      role: "admin",
      isDefaultAdmin: false,
    };
    mockedApi.getUsers.mockResolvedValueOnce([adminUser, delegatedAdmin]);
    mockedApi.updateUser.mockResolvedValueOnce({ ...delegatedAdmin, role: "user" });
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("次级管理员");

    fireEvent.click(screen.getByRole("button", { name: "降低 次级管理员 的权限" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认降权" }));

    await waitFor(() => expect(mockedApi.updateUser).toHaveBeenCalledWith("delegated-admin", {
      role: "user",
    }));
    expect(screen.getByRole("button", { name: "重置 次级管理员 的密码" })).toBeEnabled();
  }, 10_000);

  it("does not offer promotion for a disabled user", async () => {
    mockedApi.getUsers.mockResolvedValueOnce([
      adminUser,
      { ...readerUser, status: "disabled" },
    ]);
    render(
      <App>
        <UsersPage />
      </App>,
    );

    await screen.findByText("阅读者");
    expect(screen.getByRole("button", { name: "阅读者 已停用，不能提权" })).toBeDisabled();
  });

  it("shows the backend reason when a role change is rejected", async () => {
    mockedApi.updateUser.mockRejectedValueOnce(new Error("权限策略拒绝了本次提权"));
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("阅读者");

    fireEvent.click(screen.getByRole("button", { name: "提升 阅读者 的权限" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认提权" }));

    expect(await screen.findByText("权限策略拒绝了本次提权")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提升 阅读者 的权限" })).toBeEnabled();
  }, 10_000);

  it("creates only a normal user and adds the response to the table", async () => {
    const user = userEvent.setup();
    const created: UserAdminView = {
      ...readerUser,
      id: "new-user",
      username: "new-reader",
      displayName: "新读者",
      bookCount: 0,
    };
    mockedApi.createUser.mockResolvedValue(created);
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("系统管理员");

    await user.click(screen.getByRole("button", { name: "创建普通用户" }));
    const dialog = screen.getByRole("dialog");
    const usernameInput = within(dialog).getByLabelText("用户名");
    expect(usernameInput).toHaveAttribute("maxlength", "32");
    fireEvent.change(usernameInput, { target: { value: " new-reader " } });
    fireEvent.change(within(dialog).getByLabelText("显示名称"), { target: { value: " 新读者 " } });
    fireEvent.change(within(dialog).getByLabelText("新密码"), {
      target: { value: "new-reader-password" },
    });
    fireEvent.change(within(dialog).getByLabelText("确认新密码"), {
      target: { value: "new-reader-password" },
    });
    await user.click(within(dialog).getByRole("button", { name: "创建用户" }));

    await waitFor(() => expect(mockedApi.createUser).toHaveBeenCalledWith({
      username: "new-reader",
      displayName: "新读者",
      password: "new-reader-password",
    }));
    expect(await screen.findByText("新读者")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("rejects usernames longer than the backend 32-character limit", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("系统管理员");

    await user.click(screen.getByRole("button", { name: "创建普通用户" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("用户名"), {
      target: { value: "a".repeat(33) },
    });
    fireEvent.change(within(dialog).getByLabelText("显示名称"), { target: { value: "超长用户" } });
    fireEvent.change(within(dialog).getByLabelText("新密码"), {
      target: { value: "new-reader-password" },
    });
    fireEvent.change(within(dialog).getByLabelText("确认新密码"), {
      target: { value: "new-reader-password" },
    });
    await user.click(within(dialog).getByRole("button", { name: "创建用户" }));

    expect(await within(dialog).findByText("用户名需要 3–32 个字符")).toBeInTheDocument();
    expect(mockedApi.createUser).not.toHaveBeenCalled();
  });

  it("supports disabling a normal user", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("阅读者");

    await user.click(screen.getByRole("button", { name: "停用 阅读者" }));
    await user.click(screen.getByRole("button", { name: "确认停用" }));
    await waitFor(() => expect(mockedApi.updateUser).toHaveBeenCalledWith("reader-user", {
      status: "disabled",
    }));
  }, 10_000);

  it("supports password reset", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("阅读者");

    await user.click(screen.getByRole("button", { name: "重置 阅读者 的密码" }));
    const resetDialog = screen.getByRole("dialog");
    fireEvent.change(within(resetDialog).getByLabelText("新密码"), {
      target: { value: "replacement-password" },
    });
    fireEvent.change(within(resetDialog).getByLabelText("确认新密码"), {
      target: { value: "replacement-password" },
    });
    await user.click(within(resetDialog).getByRole("button", { name: "重置密码" }));
    await waitFor(() => expect(mockedApi.resetUserPassword).toHaveBeenCalledWith("reader-user", {
      password: "replacement-password",
    }));
  });

  it("supports session revocation", async () => {
    const user = userEvent.setup();
    render(
      <App>
        <UsersPage />
      </App>,
    );
    await screen.findByText("阅读者");

    await user.click(screen.getByRole("button", { name: "撤销 阅读者 的登录会话" }));
    await user.click(screen.getByRole("button", { name: "确认撤销" }));
    await waitFor(() => expect(mockedApi.revokeUserSessions).toHaveBeenCalledWith("reader-user"));
  }, 10_000);

  it("keeps load failures local and offers a retry", async () => {
    const user = userEvent.setup();
    mockedApi.getUsers
      .mockRejectedValueOnce(new Error("用户服务暂时不可用"))
      .mockResolvedValueOnce([adminUser]);
    render(
      <App>
        <UsersPage />
      </App>,
    );

    expect(await screen.findByText("用户服务暂时不可用")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByText("系统管理员")).toBeInTheDocument();
    expect(mockedApi.getUsers).toHaveBeenCalledTimes(2);
  });
});
