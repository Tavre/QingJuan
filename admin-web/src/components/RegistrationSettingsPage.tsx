import { useCallback, useEffect, useState } from "react";
import {
  GithubOutlined,
  IdcardOutlined,
  LockOutlined,
  MailOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from "antd";

import * as api from "../api";
import type {
  RegistrationSettings,
  RegistrationSettingsUpdate,
  SmtpSecurity,
} from "../types";

type RegistrationSettingsFormValues = {
  emailVerificationRequired: boolean;
  identityBadgeRequired: boolean;
  githubEnabled: boolean;
  githubClientId: string;
  smtpHost: string;
  smtpPort: number;
  smtpSecurity: SmtpSecurity;
  smtpUsername: string;
  smtpFromAddress: string;
  smtpFromName: string;
  smtpPassword?: string;
  identityBadge?: string;
};

export function RegistrationSettingsPage() {
  const { message } = App.useApp();
  const [form] = Form.useForm<RegistrationSettingsFormValues>();
  const [settings, setSettings] = useState<RegistrationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [clearSmtpPassword, setClearSmtpPassword] = useState(false);
  const [clearIdentityBadge, setClearIdentityBadge] = useState(false);

  const emailVerificationRequired = Form.useWatch("emailVerificationRequired", form) ?? false;
  const identityBadgeRequired = Form.useWatch("identityBadgeRequired", form) ?? false;
  const githubEnabled = Form.useWatch("githubEnabled", form) ?? false;
  const smtpUsername = Form.useWatch("smtpUsername", form) ?? "";
  const smtpSecurity = Form.useWatch("smtpSecurity", form) ?? "starttls";
  const smtpPassword = Form.useWatch("smtpPassword", form) ?? "";
  const identityBadge = Form.useWatch("identityBadge", form) ?? "";

  const applySettings = useCallback((next: RegistrationSettings) => {
    setSettings(next);
    setClearSmtpPassword(false);
    setClearIdentityBadge(false);
    form.setFieldsValue({
      emailVerificationRequired: next.registration.emailVerificationRequired,
      identityBadgeRequired: next.registration.identityBadgeRequired,
      githubEnabled: next.github.enabled,
      githubClientId: next.github.clientId,
      smtpHost: next.smtp.host,
      smtpPort: next.smtp.port,
      smtpSecurity: next.smtp.security,
      smtpUsername: next.smtp.username,
      smtpFromAddress: next.smtp.fromAddress,
      smtpFromName: next.smtp.fromName,
      smtpPassword: "",
      identityBadge: "",
    });
  }, [form]);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      applySettings(await api.getRegistrationSettings());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "注册设置读取失败");
    } finally {
      setLoading(false);
    }
  }, [applySettings]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const handleFinish = async (values: RegistrationSettingsFormValues) => {
    if (settings === null) return;
    const nextSmtpPassword = values.smtpPassword ?? "";
    const nextIdentityBadge = values.identityBadge?.trim() ?? "";
    const payload: RegistrationSettingsUpdate = {
      emailVerificationRequired: values.emailVerificationRequired,
      identityBadgeRequired: values.identityBadgeRequired,
      smtp: {
        host: values.smtpHost.trim(),
        port: values.smtpPort,
        security: values.smtpSecurity,
        username: values.smtpUsername.trim(),
        fromAddress: values.smtpFromAddress.trim(),
        fromName: values.smtpFromName.trim(),
      },
      github: {
        enabled: values.githubEnabled,
        clientId: values.githubClientId.trim(),
      },
      smtpPasswordAction: nextSmtpPassword
        ? "replace"
        : clearSmtpPassword ? "clear" : "keep",
      identityBadgeAction: nextIdentityBadge
        ? "replace"
        : clearIdentityBadge ? "clear" : "keep",
      ...(nextSmtpPassword ? { smtpPassword: nextSmtpPassword } : {}),
      ...(nextIdentityBadge ? { identityBadge: nextIdentityBadge } : {}),
    };

    setSaving(true);
    try {
      applySettings(await api.updateRegistrationSettings(payload));
      message.success("注册设置已保存");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "注册设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading && settings === null) {
    return (
      <div className="content-loading registration-settings-loading">
        <Spin size="large" />
        <span>正在读取注册设置…</span>
      </div>
    );
  }

  if (settings === null) {
    return (
      <Alert
        type="error"
        showIcon
        title="暂时无法读取注册设置"
        description={loadError}
        action={<Button icon={<ReloadOutlined />} onClick={() => void loadSettings()}>重试</Button>}
      />
    );
  }

  const smtpPasswordAvailable = smtpPassword.length > 0
    || (settings.smtp.passwordConfigured && !clearSmtpPassword);
  const identityBadgeAvailable = identityBadge.trim().length > 0
    || (settings.registration.identityBadgeConfigured && !clearIdentityBadge);

  return (
    <Form
      form={form}
      layout="vertical"
      requiredMark={false}
      onFinish={handleFinish}
      className="registration-settings-form"
    >
      <RegistrationRuleSummary
        emailVerificationRequired={emailVerificationRequired}
        identityBadgeRequired={identityBadgeRequired}
      />

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card
            className={`panel-card registration-method-card${emailVerificationRequired ? " is-enabled" : ""}`}
            title={(
              <Space>
                <MailOutlined />
                <span>邮箱验证码注册</span>
              </Space>
            )}
            extra={(
              <Form.Item name="emailVerificationRequired" valuePropName="checked" noStyle>
                <Switch aria-label="启用邮箱验证码注册" />
              </Form.Item>
            )}
          >
            <Typography.Paragraph type="secondary">
              启用后，注册验证码会发送至用户填写的邮箱；验证码通过后方可继续注册。
            </Typography.Paragraph>

            {emailVerificationRequired && !settings.smtp.configured && (
              <Alert
                className="registration-method-alert"
                type="warning"
                showIcon
                title="请先补全 SMTP 服务设置"
                description="保存时会验证发件服务器、端口和发件邮箱；认证账号存在时还必须配置密码。"
              />
            )}

            <Divider titlePlacement="start" plain>SMTP 服务</Divider>
            <Row gutter={16}>
              <Col xs={24} md={16}>
                <Form.Item
                  label="SMTP 服务器"
                  name="smtpHost"
                  rules={[{ required: emailVerificationRequired, whitespace: true, message: "请输入 SMTP 服务器" }]}
                >
                  <Input placeholder="smtp.example.com" autoComplete="off" maxLength={255} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item
                  label="端口"
                  name="smtpPort"
                  rules={[{ required: emailVerificationRequired, message: "请输入 SMTP 端口" }]}
                >
                  <InputNumber
                    min={1}
                    max={65535}
                    precision={0}
                    style={{ width: "100%" }}
                  />
                </Form.Item>
              </Col>
            </Row>

            <Row gutter={16}>
              <Col xs={24} md={10}>
                <Form.Item label="连接安全" name="smtpSecurity">
                  <Select
                    options={[
                      { value: "starttls", label: "STARTTLS（推荐）" },
                      { value: "ssl", label: "SSL / TLS" },
                      { value: "none", label: "无加密" },
                    ]}
                  />
                </Form.Item>
              </Col>
              <Col xs={24} md={14}>
                <Form.Item
                  label="认证账号"
                  name="smtpUsername"
                  extra="SMTP 服务无需认证时可留空。"
                  rules={[{
                    validator: async (_, value: string | undefined) => {
                      if (smtpSecurity === "none" && value?.trim()) {
                        throw new Error("无加密仅用于无需认证的本地 SMTP Relay");
                      }
                    },
                  }]}
                >
                  <Input autoComplete="username" placeholder="mailer@example.com" maxLength={254} />
                </Form.Item>
              </Col>
            </Row>

            {smtpSecurity === "none" && (
              <Alert
                className="registration-method-alert"
                type={smtpUsername.trim() ? "error" : "warning"}
                showIcon
                title="SMTP 连接未加密"
                description="无加密仅用于无需认证的本地 SMTP Relay；请勿通过明文连接发送认证账号或密码。"
              />
            )}

            <Form.Item
              label={(
                <div className="registration-secret-label">
                  <Space size={8}>
                    <span>认证密码</span>
                    <SecretStatusTag
                      configured={settings.smtp.passwordConfigured}
                      clearRequested={clearSmtpPassword}
                    />
                  </Space>
                  <Button
                    type="link"
                    size="small"
                    danger
                    disabled={!settings.smtp.passwordConfigured && smtpPassword.length === 0}
                    onClick={() => {
                      form.setFieldValue("smtpPassword", "");
                      setClearSmtpPassword(true);
                    }}
                  >
                    清除密码
                  </Button>
                </div>
              )}
              name="smtpPassword"
              extra="已保存的密码不会回显；留空保持现有密码。"
              rules={[{
                validator: async (_, value: string | undefined) => {
                  if (!emailVerificationRequired || !smtpUsername.trim()) return;
                  if ((value ?? "").length > 0 || smtpPasswordAvailable) return;
                  throw new Error("认证账号已填写，请输入 SMTP 密码");
                },
              }]}
            >
              <Input.Password
                aria-label="SMTP 认证密码"
                autoComplete="new-password"
                maxLength={1024}
                placeholder={settings.smtp.passwordConfigured ? "留空保持现有密码" : "输入 SMTP 认证密码"}
              />
            </Form.Item>

            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item
                  label="发件邮箱"
                  name="smtpFromAddress"
                  rules={[
                    { required: emailVerificationRequired, whitespace: true, message: "请输入发件邮箱" },
                    { type: "email", message: "请输入有效的发件邮箱" },
                  ]}
                >
                  <Input placeholder="noreply@example.com" maxLength={254} />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item label="发件人名称" name="smtpFromName">
                  <Input placeholder="青卷" maxLength={128} />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <div className="registration-side-stack">
          <Card
            className={`panel-card registration-method-card${identityBadgeRequired ? " is-enabled" : ""}`}
            title={(
              <Space>
                <IdcardOutlined />
                <span>身份牌注册</span>
              </Space>
            )}
            extra={(
              <Form.Item name="identityBadgeRequired" valuePropName="checked" noStyle>
                <Switch aria-label="启用身份牌注册" />
              </Form.Item>
            )}
          >
            <Typography.Paragraph type="secondary">
              启用后，所有新用户必须输入管理员设置的固定身份牌；身份牌仅用于准入验证。
            </Typography.Paragraph>

            {identityBadgeRequired && !identityBadgeAvailable && (
              <Alert
                className="registration-method-alert"
                type="warning"
                showIcon
                title="请先设置固定身份牌"
                description="身份牌不会在保存后回显。未提供有效身份牌时，无法启用此注册判断。"
              />
            )}

            <Divider titlePlacement="start" plain>身份牌凭据</Divider>
            <Form.Item
              label={(
                <div className="registration-secret-label">
                  <Space size={8}>
                    <span>固定身份牌</span>
                    <SecretStatusTag
                      configured={settings.registration.identityBadgeConfigured}
                      clearRequested={clearIdentityBadge}
                    />
                  </Space>
                  <Button
                    type="link"
                    size="small"
                    danger
                    disabled={!settings.registration.identityBadgeConfigured && !identityBadge.trim()}
                    onClick={() => {
                      form.setFieldValue("identityBadge", "");
                      setClearIdentityBadge(true);
                    }}
                  >
                    清除身份牌
                  </Button>
                </div>
              )}
              name="identityBadge"
              extra="已保存的身份牌不会回显；留空保持现有身份牌。"
              rules={[{
                validator: async (_, value: string | undefined) => {
                  const candidate = value?.trim() ?? "";
                  if (candidate.length > 0 && (candidate.length < 8 || candidate.length > 128)) {
                    throw new Error("固定身份牌需要 8–128 个字符");
                  }
                  if (!identityBadgeRequired) return;
                  if (candidate || identityBadgeAvailable) return;
                  throw new Error("启用身份牌注册前必须设置固定身份牌");
                },
              }]}
            >
              <Input.Password
                aria-label="固定身份牌"
                autoComplete="new-password"
                placeholder={settings.registration.identityBadgeConfigured ? "留空保持现有身份牌" : "输入固定身份牌"}
                maxLength={128}
              />
            </Form.Item>

            <Alert
              className="registration-security-note"
              type="info"
              showIcon
              icon={<SafetyCertificateOutlined />}
              title="请通过安全渠道分发身份牌"
              description="更换身份牌只影响之后的注册，不会退出或删除已经注册的用户。"
            />
          </Card>

          <Card
            className={`panel-card registration-method-card registration-github-card${githubEnabled ? " is-enabled" : ""}`}
            title={(
              <Space>
                <GithubOutlined />
                <span>GitHub 登录</span>
              </Space>
            )}
            extra={(
              <Form.Item name="githubEnabled" valuePropName="checked" noStyle>
                <Switch aria-label="启用 GitHub 登录" />
              </Form.Item>
            )}
          >
            <Typography.Paragraph type="secondary">
              使用 GitHub OAuth App Device Flow，让已有青卷账号在登录后自行绑定 GitHub。
            </Typography.Paragraph>

            <Form.Item
              label={(
                <Space size={8}>
                  <span>OAuth App Client ID</span>
                  <Tag color={settings.github.configured ? "success" : "default"}>
                    {settings.github.configured ? "已配置" : "未配置"}
                  </Tag>
                </Space>
              )}
              name="githubClientId"
              rules={[{
                validator: async (_, value: string | undefined) => {
                  const clientId = value?.trim() ?? "";
                  if (form.getFieldValue("githubEnabled") && !clientId) {
                    throw new Error("请输入 GitHub OAuth App Client ID");
                  }
                  if (clientId.length > 128) {
                    throw new Error("Client ID 不能超过 128 个字符");
                  }
                },
              }]}
              extra="只保存公开的 Client ID；青卷不需要配置 Client Secret。"
            >
              <Input
                aria-label="GitHub OAuth App Client ID"
                autoComplete="off"
                maxLength={128}
                placeholder="粘贴 OAuth App 的 Client ID"
              />
            </Form.Item>

            <Alert
              className="registration-method-alert"
              type="info"
              showIcon
              title="请在 GitHub OAuth App 中启用 Device Flow"
              description="青卷不会调用回调 URL；GitHub 创建表单若要求填写，请使用你控制的 HTTPS 地址（可与主页一致）。用户只应在 github.com/login/device 输入设备码。"
            />
            <Alert
              className="registration-method-alert"
              type="warning"
              showIcon
              title="不会自动创建本地账号"
              description="GitHub 登录仅用于已注册并自行绑定的账号；未绑定的 GitHub 用户不能直接注册或进入书架。"
            />
          </Card>

          <Card className="panel-card registration-email-note" title="注册邮箱规则">
            <Space align="start">
              <LockOutlined className="registration-note-icon" />
              <div>
                <Typography.Text strong>邮箱始终是必填项</Typography.Text>
                <Typography.Paragraph type="secondary">
                  无论是否启用验证码，新用户注册都必须填写有效邮箱；后端不会向管理端回显 SMTP 密码或身份牌。
                </Typography.Paragraph>
              </div>
            </Space>
          </Card>
          </div>
        </Col>
      </Row>

      <div className="registration-save-bar">
        <Typography.Text type="secondary">
          保存后立即应用于新的注册请求，已登录用户不受影响。
        </Typography.Text>
        <Button
          type="primary"
          size="large"
          htmlType="submit"
          icon={<SaveOutlined />}
          loading={saving}
        >
          保存注册设置
        </Button>
      </div>
    </Form>
  );
}

function RegistrationRuleSummary({
  emailVerificationRequired,
  identityBadgeRequired,
}: {
  emailVerificationRequired: boolean;
  identityBadgeRequired: boolean;
}) {
  let title = "当前允许直接注册";
  let description = "用户仍需填写邮箱和密码，但无需额外的注册判断。";
  let type: "info" | "warning" | "success" = "warning";

  if (emailVerificationRequired && identityBadgeRequired) {
    title = "注册必须同时通过两项判断";
    description = "用户需要先通过邮箱验证码，再提交正确的固定身份牌；任一项失败都不能注册。";
    type = "success";
  } else if (emailVerificationRequired) {
    title = "注册需要邮箱验证码";
    description = "系统会向注册邮箱发送一次性验证码，通过后才能创建账号。";
    type = "info";
  } else if (identityBadgeRequired) {
    title = "注册需要固定身份牌";
    description = "用户必须提交与管理端设置完全一致的身份牌，验证通过后才能创建账号。";
    type = "info";
  }

  return (
    <Alert
      className="registration-rule-summary"
      type={type}
      showIcon
      title={title}
      description={description}
    />
  );
}

function SecretStatusTag({
  configured,
  clearRequested,
}: {
  configured: boolean;
  clearRequested: boolean;
}) {
  if (clearRequested) return <Tag color="warning">等待清除</Tag>;
  return configured ? <Tag color="success">已保存</Tag> : <Tag>未设置</Tag>;
}
