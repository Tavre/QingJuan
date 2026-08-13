import userEvent from "@testing-library/user-event";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@ant-design/icons", () => ({
  ArrowRightOutlined: () => null,
  BookOutlined: () => null,
  CheckCircleOutlined: () => null,
  LockOutlined: () => null,
  MoonOutlined: () => null,
  SafetyCertificateOutlined: () => null,
  SunOutlined: () => null,
}));

vi.mock("antd", async () => {
  const React = await import("react");
  const Form = (({ children, onFinish }: any) => React.createElement(
    "form",
    {
      onSubmit: (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        void onFinish({ password: values.get("password") });
      },
    },
    children,
  )) as any;
  Form.Item = ({ children, label, name }: any) => React.createElement(
    "label",
    null,
    label,
    React.isValidElement(children)
      ? React.cloneElement(children as React.ReactElement<any>, { name, "aria-label": label })
      : children,
  );

  const Input = {
    Password: ({ prefix: _prefix, size: _size, ...props }: any) => React.createElement(
      "input",
      { ...props, type: "password" },
    ),
  };
  const Typography = {
    Text: ({ children, ...props }: any) => React.createElement("span", props, children),
    Title: ({ children, level = 2, ...props }: any) => React.createElement(`h${level}`, props, children),
    Paragraph: ({ children, ...props }: any) => React.createElement("p", props, children),
  };

  return {
    Alert: ({ title }: any) => React.createElement("div", { role: "alert" }, title),
    Button: ({ children, htmlType, loading, icon: _icon, ...props }: any) => React.createElement(
      "button",
      { ...props, type: htmlType, disabled: loading },
      children,
    ),
    Card: ({ children }: any) => React.createElement("div", null, children),
    Form,
    Input,
    Space: ({ children }: any) => React.createElement("div", null, children),
    Tooltip: ({ children }: any) => children,
    Typography,
  };
});

import { ApiError } from "../api";
import { LoginScreen } from "./LoginScreen";

describe("LoginScreen", () => {
  it("submits the management password without storing it", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    render(<LoginScreen onLogin={onLogin} />);

    await user.type(screen.getByLabelText("管理密码"), "random-admin-password");
    await user.click(screen.getByRole("button", { name: "进入管理台" }));

    await waitFor(() => expect(onLogin).toHaveBeenCalledWith("random-admin-password"));
  });

  it("shows a useful backend authentication error", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockRejectedValue(new ApiError("管理密码错误", 401));
    render(<LoginScreen onLogin={onLogin} />);

    await user.type(screen.getByLabelText("管理密码"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "进入管理台" }));

    expect(await screen.findByText("管理密码错误")).toBeInTheDocument();
  });
});
