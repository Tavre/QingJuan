import { useMemo, useState } from "react";
import { DeleteOutlined, SearchOutlined } from "@ant-design/icons";
import { App, Button, Input, Popconfirm, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { Book } from "../types";
import { formatDate } from "./AdminShell";

type LibraryPageProps = {
  books: Book[];
  onDelete: (bookId: string) => Promise<void>;
};

export function LibraryPage({ books, onDelete }: LibraryPageProps) {
  const { message } = App.useApp();
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState("");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return books;
    return books.filter((book) =>
      [book.title, book.bookKind, book.language, book.status]
        .some((value) => value.toLocaleLowerCase().includes(normalized)),
    );
  }, [books, query]);

  const columns: ColumnsType<Book> = [
    {
      title: "作品",
      dataIndex: "title",
      key: "title",
      width: 280,
      render: (_, book) => (
        <div className="book-title-cell">
          <Typography.Text strong ellipsis={{ tooltip: book.title }}>{book.title}</Typography.Text>
          <Typography.Text type="secondary" ellipsis>{book.sourceUrl || "本地导入"}</Typography.Text>
        </div>
      ),
    },
    { title: "类型", dataIndex: "bookKind", key: "bookKind", width: 100 },
    { title: "语言", dataIndex: "language", key: "language", width: 90 },
    {
      title: "章节",
      dataIndex: "chapterCount",
      key: "chapterCount",
      width: 90,
      align: "right",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (status: Book["status"], book) => (
        <Space size={4} wrap>
          <Tag color={status === "已完成" ? "success" : status === "解析中" ? "processing" : "default"}>{status}</Tag>
          {book.translated && <Tag color="purple">有译文</Tag>}
        </Space>
      ),
    },
    {
      title: "最近更新",
      dataIndex: "updatedAt",
      key: "updatedAt",
      width: 140,
      render: (value: string) => formatDate(value),
      sorter: (left, right) => left.updatedAt.localeCompare(right.updatedAt),
      defaultSortOrder: "descend",
    },
    {
      title: "操作",
      key: "actions",
      width: 90,
      fixed: "right",
      render: (_, book) => (
        <Popconfirm
          title="删除这本书？"
          description="服务端章节、译文和相关任务记录会一并删除，此操作无法撤销。"
          okText="确认删除"
          cancelText="取消"
          okButtonProps={{ danger: true, loading: deleting === book.id }}
          onConfirm={async () => {
            setDeleting(book.id);
            try {
              await onDelete(book.id);
            } catch (error) {
              message.error(error instanceof Error ? error.message : "书籍删除失败");
            } finally {
              setDeleting("");
            }
          }}
        >
          <Button danger type="text" icon={<DeleteOutlined />} aria-label={`删除 ${book.title}`}>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ];

  return (
    <div className="table-panel">
      <div className="table-toolbar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索书名、类型或状态"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="table-search"
        />
        <Typography.Text type="secondary">共 {filtered.length} 本</Typography.Text>
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={filtered}
        scroll={{ x: 980 }}
        locale={{ emptyText: query ? "没有匹配的书籍" : "书库还是空的" }}
        pagination={{ pageSize: 12, showSizeChanger: false, hideOnSinglePage: true }}
      />
    </div>
  );
}
