import { useEffect, useState } from "react";
import { CheckCircleFilled, CloseCircleFilled, KeyOutlined, ReloadOutlined, SafetyCertificateOutlined, SaveOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Col, Divider, Form, Input, InputNumber, Row, Space, Switch, Tag, Typography } from "antd";

import { checkTranslationModel } from "../api";
import type { Settings, SettingsUpdate, TranslationModelCheck } from "../types";

type SettingsFormValues = {
  downloadConcurrency: number;
  autoTranslateNextChapters: number;
  systemPrompt: string;
  translationModelEnabled: boolean;
  translationBaseUrl: string;
  translationModel: string;
  translationSupportsVision: boolean;
  translationApiKey?: string;
  mangaOcrEnabled: boolean;
  mangaOcrBaseUrl: string;
  mangaOcrApiKey?: string;
};

type SettingsPageProps = {
  settings: Settings;
  onSave: (payload: SettingsUpdate) => Promise<void>;
};

export function SettingsPage({ settings, onSave }: SettingsPageProps) {
  const { message } = App.useApp();
  const [form] = Form.useForm<SettingsFormValues>();
  const [saving, setSaving] = useState(false);
  const [modelChecking, setModelChecking] = useState(false);
  const [modelCheck, setModelCheck] = useState<TranslationModelCheck | null>(null);
  const translationEnabled = Form.useWatch("translationModelEnabled", form);
  const mangaOcrEnabled = Form.useWatch("mangaOcrEnabled", form);

  useEffect(() => {
    form.setFieldsValue({
      downloadConcurrency: settings.downloadConcurrency,
      autoTranslateNextChapters: settings.autoTranslateNextChapters,
      systemPrompt: settings.systemPrompt,
      translationModelEnabled: settings.translationModel.enabled,
      translationBaseUrl: settings.translationModel.baseUrl,
      translationModel: settings.translationModel.model,
      translationSupportsVision: settings.translationModel.supportsVision,
      translationApiKey: "",
      mangaOcrEnabled: settings.mangaOcr.enabled,
      mangaOcrBaseUrl: settings.mangaOcr.baseUrl,
      mangaOcrApiKey: "",
    });
  }, [form, settings]);

  const runModelCheck = async (force = false) => {
    setModelChecking(true);
    try {
      const result = await checkTranslationModel(force);
      setModelCheck(result);
      if (force) {
        if (result.available) message.success("翻译模型自检通过");
        else message.warning(result.message);
      }
      return result;
    } catch (error) {
      if (force) message.error(error instanceof Error ? error.message : "模型自检失败");
      return null;
    } finally {
      setModelChecking(false);
    }
  };

  useEffect(() => {
    void runModelCheck();
    // 设置页挂载时读取后端缓存的检查结果，避免表单输入触发重复探针。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFinish = async (values: SettingsFormValues) => {
    setSaving(true);
    try {
      const translationApiKey = values.translationApiKey?.trim() ?? "";
      const mangaOcrApiKey = values.mangaOcrApiKey?.trim() ?? "";
      await onSave({
        systemPrompt: values.systemPrompt,
        autoTranslateNextChapters: values.autoTranslateNextChapters,
        downloadConcurrency: values.downloadConcurrency,
        translationModel: {
          enabled: values.translationModelEnabled,
          baseUrl: values.translationBaseUrl.trim(),
          apiKey: translationApiKey,
          model: values.translationModel.trim(),
          supportsVision: values.translationSupportsVision,
          apiKeyAction: translationApiKey ? "replace" : "keep",
        },
        mangaOcr: {
          enabled: values.mangaOcrEnabled,
          baseUrl: values.mangaOcrBaseUrl.trim(),
          apiKey: mangaOcrApiKey,
          apiKeyAction: mangaOcrApiKey ? "replace" : "keep",
        },
        bika: {
          email: "",
          password: "",
          passwordAction: "keep",
        },
      });
      form.setFieldsValue({ translationApiKey: "", mangaOcrApiKey: "" });
      await runModelCheck(true);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "设置保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Form form={form} layout="vertical" requiredMark={false} onFinish={handleFinish}>
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card
            className="panel-card settings-card"
            title="翻译模型"
            extra={(
              <Button
                aria-label="模型自检"
                icon={<ReloadOutlined spin={modelChecking} />}
                loading={modelChecking}
                onClick={() => void runModelCheck(true)}
              >
                模型自检
              </Button>
            )}
          >
            <div className="setting-switch-row">
              <div>
                <Typography.Text strong>启用 OpenAI 兼容翻译</Typography.Text>
                <Typography.Paragraph type="secondary">所有小说和漫画翻译共用这套模型配置。</Typography.Paragraph>
              </div>
              <Form.Item name="translationModelEnabled" valuePropName="checked" noStyle>
                <Switch aria-label="启用 OpenAI 兼容翻译" />
              </Form.Item>
            </div>
            <ModelCheckAlert value={modelCheck} loading={modelChecking} />
            <Divider />
            <Row gutter={16}>
              <Col xs={24} md={14}>
                <Form.Item
                  label="API 根地址"
                  name="translationBaseUrl"
                  rules={[{ required: translationEnabled, message: "请输入 API 根地址" }, { type: "url", message: "请输入有效的 URL" }]}
                >
                  <Input disabled={!translationEnabled} placeholder="https://api.openai.com/v1" />
                </Form.Item>
              </Col>
              <Col xs={24} md={10}>
                <Form.Item label="模型" name="translationModel" rules={[{ required: translationEnabled, message: "请输入模型名称" }]}>
                  <Input disabled={!translationEnabled} placeholder="gpt-5.4" />
                </Form.Item>
              </Col>
            </Row>
            <Row className="model-credentials-row" gutter={16} align="top">
              <Col xs={24} md={18}>
                <Form.Item
                  label="API 密钥"
                  name="translationApiKey"
                  extra={settings.translationModel.apiKeyConfigured ? "已保存密钥；留空可保持不变。" : "尚未保存密钥。"}
                >
                  <Input.Password disabled={!translationEnabled} autoComplete="new-password" placeholder="留空保持现有密钥" />
                </Form.Item>
              </Col>
              <Col xs={24} md={6}>
                <Form.Item name="translationSupportsVision" valuePropName="checked" label="模型能力">
                  <Switch disabled={!translationEnabled} checkedChildren="支持视觉" unCheckedChildren="仅文本" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="系统提示词" name="systemPrompt" rules={[{ required: true, message: "系统提示词不能为空" }]}>
              <Input.TextArea autoSize={{ minRows: 7, maxRows: 14 }} showCount maxLength={12000} />
            </Form.Item>
          </Card>

          <Card className="panel-card settings-card" title="漫画 OCR">
            <div className="setting-switch-row">
              <div>
                <Typography.Text strong>启用外部 OCR 服务</Typography.Text>
                <Typography.Paragraph type="secondary">未启用时继续使用 Linux RapidOCR 本地识别。</Typography.Paragraph>
              </div>
              <Form.Item name="mangaOcrEnabled" valuePropName="checked" noStyle>
                <Switch aria-label="启用外部 OCR 服务" />
              </Form.Item>
            </div>
            <Divider />
            <Row gutter={16}>
              <Col xs={24} md={14}>
                <Form.Item
                  label="OCR API 地址"
                  name="mangaOcrBaseUrl"
                  rules={[{ required: mangaOcrEnabled, message: "请输入 OCR API 地址" }, { type: "url", message: "请输入有效的 URL" }]}
                >
                  <Input disabled={!mangaOcrEnabled} placeholder="https://example.com/ocr" />
                </Form.Item>
              </Col>
              <Col xs={24} md={10}>
                <Form.Item
                  label="OCR API 密钥"
                  name="mangaOcrApiKey"
                  extra={settings.mangaOcr.apiKeyConfigured ? "已保存；留空保持不变。" : "可选。"}
                >
                  <Input.Password disabled={!mangaOcrEnabled} autoComplete="new-password" placeholder="留空保持现有密钥" />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card className="panel-card settings-card" title="任务参数">
            <Form.Item label="下载并发数" name="downloadConcurrency" rules={[{ required: true }]}>
              <InputNumber min={1} max={8} precision={0} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item
              label="自动翻译后续章节数"
              name="autoTranslateNextChapters"
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={100} precision={0} style={{ width: "100%" }} />
            </Form.Item>
            <Alert
              type="info"
              showIcon
              title="并发越高并不一定越快"
              description="请同时考虑目标站点限制、模型速率与服务器资源。"
            />
          </Card>

          <Card className="panel-card security-note" variant="borderless">
            <Space align="start">
              <SafetyCertificateOutlined className="security-note-icon" />
              <div>
                <Typography.Text strong>管理凭据由服务器维护</Typography.Text>
                <Typography.Paragraph type="secondary">
                  此页面不会读取客户端连接 Token，也不会回显已保存的 API 密钥。
                </Typography.Paragraph>
              </div>
            </Space>
            <div className="command-note"><KeyOutlined /> 改密：<code>sudo qingjuan-password</code></div>
          </Card>

          <Button aria-label="保存全部设置" type="primary" size="large" block htmlType="submit" icon={<SaveOutlined />} loading={saving}>
            保存全部设置
          </Button>
        </Col>
      </Row>
    </Form>
  );
}

function ModelCheckAlert({
  value,
  loading,
}: {
  value: TranslationModelCheck | null;
  loading: boolean;
}) {
  if (loading && value === null) {
    return <Alert className="model-check-alert" type="info" showIcon title="正在检测 Linux 服务端翻译模型" />;
  }
  if (value === null) {
    return <Alert className="model-check-alert" type="warning" showIcon title="尚未取得模型自检结果" />;
  }
  const detail = [
    value.model,
    value.latencyMs === null ? null : `${value.latencyMs} ms`,
    value.available ? (value.supportsVision ? "支持视觉" : "仅文本") : null,
    value.cached ? "近期缓存" : null,
  ].filter(Boolean).join(" · ");
  return (
    <Alert
      className="model-check-alert"
      type={value.available ? "success" : value.status === "failed" ? "error" : "warning"}
      showIcon
      icon={value.available ? <CheckCircleFilled /> : <CloseCircleFilled />}
      title={value.available ? "Linux 服务端模型可用" : value.message}
      description={value.available ? detail : "请在此页面完善配置后保存，系统会立即重新检测。"}
      action={<Tag color={value.available ? "success" : "error"}>{value.available ? "可翻译" : "不可翻译"}</Tag>}
    />
  );
}
