import { useState } from "react";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";

import { ApiError } from "../api";
import { ThemeToggle } from "../theme";
import { BrandLogo } from "./BrandLogo";

type LoginScreenProps = {
  onLogin: (password: string) => Promise<void>;
};

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleFinish = async ({ password }: { password: string }) => {
    setSubmitting(true);
    setError("");
    try {
      await onLogin(password);
    } catch (loginError) {
      setError(loginError instanceof ApiError ? loginError.message : "登录失败，请稍后重试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-page">
      <ThemeToggle className="login-theme-toggle" />

      <section className="login-main" aria-labelledby="product-title">
        <div className="login-frame">
          <div className="login-heading">
            <BrandLogo size="large" className="login-logo" />
            <Typography.Text className="eyebrow">QINGJUAN ADMIN</Typography.Text>
            <Typography.Title id="product-title" level={1}>青卷服务管理</Typography.Title>
            <Typography.Paragraph type="secondary">
              查看服务状态、书库和任务，并维护模型与 OCR 配置。
            </Typography.Paragraph>
          </div>

          <Card className="login-card">
            <div className="login-card-heading">
              <div className="login-lock-icon" aria-hidden="true"><LockOutlined /></div>
              <div>
                <Typography.Title level={2}>登录管理界面</Typography.Title>
                <Typography.Paragraph type="secondary">
                  输入部署完成时终端显示的随机管理密码。
                </Typography.Paragraph>
              </div>
            </div>

            {error && <Alert className="login-error" type="error" showIcon title={error} />}

            <Form layout="vertical" requiredMark={false} onFinish={handleFinish}>
              <Form.Item
                label="管理密码"
                name="password"
                rules={[{ required: true, message: "请输入管理密码" }]}
              >
                <Input.Password
                  autoFocus
                  autoComplete="current-password"
                  size="large"
                  prefix={<LockOutlined aria-hidden="true" />}
                  placeholder="输入管理密码"
                />
              </Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                size="large"
                block
                loading={submitting}
                icon={<ArrowRightOutlined />}
                iconPlacement="end"
                aria-label="进入管理台"
              >
                进入管理台
              </Button>
            </Form>

            <div className="login-help">
              忘记密码？在服务器终端运行 <code>sudo qingjuan-password --generate</code>
            </div>
          </Card>

          <Space wrap size={[18, 8]} className="login-assurances">
            <span><CheckCircleOutlined /> 与 FastAPI 服务同源</span>
            <span><SafetyCertificateOutlined /> 安全 Cookie 会话</span>
          </Space>
        </div>
      </section>

      <footer className="login-footer">单用户管理入口 · 请仅通过私有网络或 HTTPS 访问</footer>
    </main>
  );
}
