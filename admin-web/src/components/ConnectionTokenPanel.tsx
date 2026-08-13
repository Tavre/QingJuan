import { useEffect, useState } from "react";
import { CopyOutlined, EyeInvisibleOutlined, EyeOutlined, KeyOutlined } from "@ant-design/icons";
import { App, Button, Space, Tag, Typography } from "antd";

import { revealConnectionToken } from "../api";
import type { ConnectionTokenStatus } from "../types";

type ConnectionTokenPanelProps = {
  status: ConnectionTokenStatus;
};

export function ConnectionTokenPanel({ status }: ConnectionTokenPanelProps) {
  const { message } = App.useApp();
  const [token, setToken] = useState("");
  const [revealing, setRevealing] = useState(false);

  useEffect(() => {
    if (!token) return;
    const timer = window.setTimeout(() => setToken(""), 60000);
    return () => window.clearTimeout(timer);
  }, [token]);

  const reveal = async () => {
    setRevealing(true);
    try {
      const result = await revealConnectionToken();
      setToken(result.token);
      message.success("API 密钥已显示，将在 60 秒后自动隐藏");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "API 密钥读取失败");
    } finally {
      setRevealing(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token);
      message.success("API 密钥已复制");
    } catch {
      message.error("无法写入剪贴板，请手动复制");
    }
  };

  const statusTag = !status.configured
    ? <Tag>未启用</Tag>
    : status.revealAvailable
      ? <Tag color="success">可按需显示</Tag>
      : <Tag color="warning">仅保存摘要</Tag>;

  return (
    <div className="connection-token-panel">
      <div className="connection-token-heading">
        <div className="connection-token-title">
          <span className="connection-token-icon" aria-hidden="true"><KeyOutlined /></span>
          <div>
            <Typography.Text strong>后端 API 密钥</Typography.Text>
            <Typography.Text type="secondary">用于 Windows / Android 客户端连接此服务</Typography.Text>
          </div>
        </div>
        {statusTag}
      </div>

      <div className={`connection-token-value${token ? " is-revealed" : ""}`} aria-live="polite">
        <code aria-label={token ? "已显示的后端 API 密钥" : "已遮挡的后端 API 密钥"}>
          {token || status.maskedToken || "当前部署不可显示"}
        </code>
      </div>

      <Space size={8} wrap>
        {token ? (
          <>
            <Button aria-label="复制后端 API 密钥" icon={<CopyOutlined />} onClick={() => void copy()}>复制密钥</Button>
            <Button aria-label="隐藏后端 API 密钥" icon={<EyeInvisibleOutlined />} onClick={() => setToken("")}>立即隐藏</Button>
          </>
        ) : (
          <Button
            icon={<EyeOutlined />}
            aria-label="显示后端 API 密钥"
            disabled={!status.revealAvailable}
            loading={revealing}
            onClick={() => void reveal()}
          >
            显示密钥
          </Button>
        )}
      </Space>

      <Typography.Text type="secondary" className="connection-token-note">
        {status.revealAvailable
          ? `SHA-256 指纹 ${status.fingerprint ?? "–"} · 原文仅在本页短暂显示，不会写入日志。`
          : status.configured
            ? `SHA-256 指纹 ${status.fingerprint ?? "–"} · 请在服务器运行更新脚本后再显示。`
            : "当前服务未启用客户端 Bearer 认证。"}
      </Typography.Text>
    </div>
  );
}
