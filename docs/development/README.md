# 青卷开发规范

本目录是青卷的唯一开发规范来源。所有后续编码、重构、评审与发布均应遵循这里的约束。

## 产品与平台边界

- 产品形态：仅 Windows 电脑端。
- 客户端：Flutter + Dart + `fluent_ui`。
- UI 基线：Microsoft Fluent UI 与 Windows 11，简约、清晰、可访问。
- 后端：Python + FastAPI；仅监听本机回环地址。
- 存储：SQLite 与本地文件。
- 不支持：Android、iOS、Web、PWA、Electron、Capacitor、Vue/Vite 客户端。

`fluent_ui` 是 Flutter 社区维护的 Fluent 组件库，不是
`microsoft/fluentui` 仓库中的 React/Web 包。项目在 Flutter 技术栈中使用它实现控件，
并以 Microsoft Fluent 的布局、状态、动效和可访问性原则作为设计依据。

## 文档导航

| 文档 | 内容 | 主要适用范围 |
| --- | --- | --- |
| [原则与架构](./01-principles-and-architecture.md) | 依赖方向、模块边界、目录与拆分阈值 | 全仓库 |
| [UI 与可访问性](./02-ui-and-accessibility.md) | Fluent、Windows 视觉、交互、键盘与语义 | `lib/features/`、`lib/shared/` |
| [Flutter 客户端](./03-frontend.md) | Dart、Widget、Controller、API 与状态管理 | `lib/`、`test/` |
| [后端与桌面集成](./04-backend-and-desktop.md) | FastAPI、数据、进程、Windows Runner 与打包 | `python-backend/`、`windows/`、`tool/` |
| [质量与测试](./05-quality-and-testing.md) | TDD、测试分层、门禁、验收与完成定义 | 所有变更 |
| [工作流与迁移](./06-workflow-and-migration.md) | Git、PR、发布、技术债与禁止项 | 贡献流程 |

## 开发环境与首次配置

环境要求：

- Windows 10 1809 或更高版本，推荐 Windows 11；
- Flutter `3.24.3` 与 Dart `3.5.3`；
- Visual Studio 2022，并安装“使用 C++ 的桌面开发”工作负载；
- Python `3.13`；
- Git。

在仓库根目录完成首次配置：

```powershell
flutter doctor -v
flutter pub get
python -m venv python-backend/.venv
python-backend/.venv/Scripts/python -m pip install -r python-backend/requirements-dev.txt
```

启动 Windows 调试：

```powershell
flutter run -d windows
```

客户端会自动检查 `http://127.0.0.1:19453`。如果该端口没有健康的青卷后端，
开发模式会从仓库中启动 `python -m app.main serve`；若服务原本已由用户启动，客户端只复用服务，
退出时不会终止外部进程。

静态检查、测试命令和三轮验证要求见[质量与测试](./05-quality-and-testing.md)，
完整 Windows 发布流程见[后端与桌面集成](./04-backend-and-desktop.md)。

## 最低强制要求

1. UI 使用 `fluent_ui` 和项目共享 Widget，不引入第二套 UI 框架。
2. 新功能按 Feature 拆分；页面不直接处理原始 HTTP、数据库或进程。
3. 网络 DTO、领域模型、状态控制与展示组件分离。
4. 任何异步界面都有加载、空、成功、失败和重试状态。
5. 所有用户可见错误使用中文且可执行，不暴露堆栈或密钥。
6. 改动同步补充测试，提交前完成格式化、静态分析、测试和 Windows 构建。
7. 根目录只保留 `README.md`；其他 Markdown 必须进入 `docs/development/` 的对应区块。
8. 不提交密钥、数据库、缓存、下载内容、日志、构建产物和个人数据。

## 规范优先级

发生冲突时依次采用：

1. 安全、隐私、许可证和用户明确要求；
2. 本开发规范；
3. Flutter、Dart、FastAPI 官方约定；
4. 现有代码模式。

现有实现与规范不一致时，不复制旧问题。局部修改应在可控范围内向规范靠拢，并用测试保护行为。

## 维护方式

- 架构、依赖、构建或 UI 基线改变时，必须在同一个 PR 更新对应文档。
- 不为一次性讨论创建新的 Markdown；将结论合并到现有章节。
- 重复规则只保留一个权威位置，其他地方使用链接。
- 文档中的命令必须能在 Windows PowerShell 执行。
