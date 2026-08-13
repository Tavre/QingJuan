import { useMemo, useState } from "react";
import { SearchOutlined } from "@ant-design/icons";
import { Input, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { BookSource } from "../types";
import { formatDate } from "./AdminShell";

const statusLabel: Record<BookSource["status"], string> = {
  unknown: "未检查",
  online: "在线",
  slow: "响应较慢",
  offline: "离线",
  unsupported: "不支持",
};

const statusColor: Record<BookSource["status"], string> = {
  unknown: "default",
  online: "success",
  slow: "warning",
  offline: "error",
  unsupported: "default",
};

export function SourcesPage({ sources }: { sources: BookSource[] }) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return sources;
    return sources.filter((source) =>
      [source.name, source.baseUrl, source.description, ...source.tags]
        .some((value) => value.toLocaleLowerCase().includes(normalized)),
    );
  }, [query, sources]);

  const columns: ColumnsType<BookSource> = [
    {
      title: "书源",
      key: "source",
      width: 300,
      render: (_, source) => (
        <div className="book-title-cell">
          <Space size={6}>
            <Typography.Text strong>{source.name}</Typography.Text>
            {!source.enabled && <Tag>已停用</Tag>}
          </Space>
          <Typography.Text type="secondary" ellipsis={{ tooltip: source.baseUrl }}>{source.baseUrl}</Typography.Text>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (status: BookSource["status"]) => <Tag color={statusColor[status]}>{statusLabel[status]}</Tag>,
    },
    { title: "类型", dataIndex: "bookKind", key: "bookKind", width: 100, render: (value) => value || "通用" },
    { title: "语言", dataIndex: "language", key: "language", width: 90, render: (value) => value || "多语言" },
    {
      title: "标签",
      dataIndex: "tags",
      key: "tags",
      render: (tags: string[]) => tags.length ? tags.slice(0, 4).map((tag) => <Tag key={tag}>{tag}</Tag>) : "–",
    },
    {
      title: "最近检查",
      dataIndex: "lastCheckedAt",
      key: "lastCheckedAt",
      width: 140,
      render: (value: string | null) => formatDate(value),
    },
  ];

  return (
    <div className="table-panel">
      <div className="table-toolbar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索书源名称、地址或标签"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="table-search"
        />
        <Typography.Text type="secondary">{sources.filter((source) => source.enabled).length} 个已启用</Typography.Text>
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        scroll={{ x: 920 }}
        locale={{ emptyText: query ? "没有匹配的书源" : "暂无书源" }}
        pagination={{ pageSize: 12, showSizeChanger: false, hideOnSinglePage: true }}
      />
    </div>
  );
}
