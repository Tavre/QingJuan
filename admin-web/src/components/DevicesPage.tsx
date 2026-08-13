import { useMemo, useState } from "react";
import {
  AndroidOutlined,
  AppleOutlined,
  DesktopOutlined,
  GlobalOutlined,
  SearchOutlined,
  StopOutlined,
  UnlockOutlined,
  WindowsOutlined,
} from "@ant-design/icons";
import { Alert, App, Button, Input, Popconfirm, Segmented, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ReactNode } from "react";

import type { Device, DevicePlatform } from "../types";
import { formatDate } from "./AdminShell";

type DeviceFilter = "all" | "online" | "offline" | "banned";

type DevicesPageProps = {
  devices: Device[];
  onSetBanned: (deviceId: string, banned: boolean) => Promise<void>;
};

const platformLabels: Record<DevicePlatform, string> = {
  android: "Android",
  windows: "Windows",
  linux: "Linux",
  macos: "macOS",
  ios: "iOS",
  other: "其他",
};

export function DevicesPage({ devices, onSetBanned }: DevicesPageProps) {
  const { message } = App.useApp();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<DeviceFilter>("all");
  const [updating, setUpdating] = useState("");

  const counts = useMemo(() => ({
    online: devices.filter((device) => device.online).length,
    offline: devices.filter((device) => !device.online && !device.banned).length,
    banned: devices.filter((device) => device.banned).length,
  }), [devices]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return [...devices]
      .filter((device) => {
        if (filter === "online" && !device.online) return false;
        if (filter === "offline" && (device.online || device.banned)) return false;
        if (filter === "banned" && !device.banned) return false;
        if (!normalized) return true;
        return [device.name, device.id, device.platform, device.ipAddress]
          .some((value) => value.toLocaleLowerCase().includes(normalized));
      })
      .sort((left, right) => {
        const leftPriority = left.banned ? 2 : left.online ? 0 : 1;
        const rightPriority = right.banned ? 2 : right.online ? 0 : 1;
        return leftPriority - rightPriority || right.lastSeenAt.localeCompare(left.lastSeenAt);
      });
  }, [devices, filter, query]);

  const updateBan = async (device: Device, banned: boolean) => {
    setUpdating(device.id);
    try {
      await onSetBanned(device.id, banned);
    } catch (error) {
      message.error(error instanceof Error ? error.message : banned ? "设备封禁失败" : "解除封禁失败");
    } finally {
      setUpdating("");
    }
  };

  const columns: ColumnsType<Device> = [
    {
      title: "设备",
      dataIndex: "name",
      key: "name",
      width: 230,
      render: (_, device) => (
        <div className="device-title-cell">
          <Space size={8}>
            <span className="device-platform-icon" aria-hidden="true">{platformIcon(device.platform)}</span>
            <Typography.Text strong ellipsis={{ tooltip: device.name }}>{device.name}</Typography.Text>
          </Space>
          <Typography.Text type="secondary" className="device-id" title={device.id}>
            ID {device.id.slice(0, 8)}…{device.id.slice(-4)}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "平台",
      dataIndex: "platform",
      key: "platform",
      width: 90,
      render: (platform: DevicePlatform) => platformLabels[platform],
    },
    {
      title: "状态",
      key: "status",
      width: 88,
      render: (_, device) => device.banned
        ? <Tag color="error">已封禁</Tag>
        : device.online
          ? <Tag color="success">在线</Tag>
          : <Tag>离线</Tag>,
    },
    {
      title: "连接地址",
      dataIndex: "ipAddress",
      key: "ipAddress",
      width: 125,
      render: (value: string) => <Typography.Text className="device-address">{value || "–"}</Typography.Text>,
    },
    {
      title: "首次连接",
      dataIndex: "firstSeenAt",
      key: "firstSeenAt",
      width: 120,
      render: (value: string) => formatDate(value),
    },
    {
      title: "最后活跃",
      dataIndex: "lastSeenAt",
      key: "lastSeenAt",
      width: 120,
      render: (value: string) => formatDate(value),
    },
    {
      title: "操作",
      key: "actions",
      width: 106,
      fixed: "right",
      render: (_, device) => device.banned ? (
        <Popconfirm
          title={`解除 ${device.name} 的封禁？`}
          description="解除后，设备可再次使用有效的后端访问令牌连接。"
          okText="确认解除"
          cancelText="取消"
          okButtonProps={{ loading: updating === device.id }}
          onConfirm={() => updateBan(device, false)}
        >
          <Button type="text" icon={<UnlockOutlined />} aria-label={`解除封禁 ${device.name}`}>
            解除封禁
          </Button>
        </Popconfirm>
      ) : (
        <Popconfirm
          title={`封禁 ${device.name}？`}
          description="该设备后续请求会被拒绝，直到管理员解除封禁。"
          okText="确认封禁"
          cancelText="取消"
          okButtonProps={{ danger: true, loading: updating === device.id }}
          onConfirm={() => updateBan(device, true)}
        >
          <Button danger type="text" icon={<StopOutlined />} aria-label={`封禁 ${device.name}`}>
            封禁
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <Alert
        className="device-security-alert"
        type="info"
        showIcon
        title="设备封禁按客户端生成的稳定设备 ID 生效"
        description="旧版本客户端不会出现在列表中；若共享访问令牌泄露，请同时在终端修改令牌。"
      />
      <div className="table-panel">
        <div className="table-toolbar device-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索设备名称、ID 或地址"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="table-search"
          />
          <Typography.Text type="secondary">在线 {counts.online} / 共 {devices.length} 台</Typography.Text>
        </div>
        <div className="device-filter-row">
          <Segmented<DeviceFilter>
            value={filter}
            onChange={setFilter}
            options={[
              { label: `全部 ${devices.length}`, value: "all" },
              { label: `在线 ${counts.online}`, value: "online" },
              { label: `离线 ${counts.offline}`, value: "offline" },
              { label: `已封禁 ${counts.banned}`, value: "banned" },
            ]}
          />
        </div>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          rowClassName={(device) => device.banned ? "device-row-banned" : ""}
          scroll={{ x: 880 }}
          locale={{ emptyText: query || filter !== "all" ? "没有匹配的设备" : "尚未有新版客户端连接此后端" }}
          pagination={{ pageSize: 12, showSizeChanger: false, hideOnSinglePage: true }}
        />
      </div>
    </div>
  );
}

function platformIcon(platform: DevicePlatform): ReactNode {
  switch (platform) {
    case "android":
      return <AndroidOutlined />;
    case "windows":
      return <WindowsOutlined />;
    case "macos":
    case "ios":
      return <AppleOutlined />;
    case "linux":
      return <DesktopOutlined />;
    default:
      return <GlobalOutlined />;
  }
}
