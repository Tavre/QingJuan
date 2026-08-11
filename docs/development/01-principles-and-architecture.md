# 原则与架构

## 1. 工程目标

青卷将抓取、下载、翻译和阅读能力组合为 Windows / Android Flutter 客户端，以及运行在 Linux 服务器上的
单用户后端。工程设计优先级为：

1. 数据与凭据安全；
2. 功能正确、故障可恢复；
3. 代码边界清楚、可测试；
4. Windows 键鼠与 Android 触控体验一致；
5. 性能与可扩展性。

避免为了“以后可能用到”提前抽象。只有出现稳定边界、重复实现或明确测试需求时才提取接口。

## 2. 总体架构

```text
Flutter View / Widget
        ↓ 用户意图与展示状态
Feature Controller
        ↓ 领域模型
ApiClient / BackendConnectionManager
        ↓ HTTPS / private-network HTTP
FastAPI Router / Auth
        ↓
Service / Scraper / Repository
        ↓
SQLite / Files / Third-party sites
```

依赖只能向下：

- Widget 不调用 `http`、`Process`、SQLite 或文件抓取。
- Controller 不依赖具体页面实例，不持有 `BuildContext`。
- `core/models` 不依赖 Feature 和 UI。
- API 层负责序列化、状态码与错误归一化，不包含页面跳转。
- 客户端只有远程连接；未配置、认证失败或版本不兼容时不得启动任何本地后端。
- 连接 Token 只由 API 基础设施层读取，不进入领域模型、页面日志或第三方请求。
- FastAPI Router 校验输入、调用业务函数并映射响应，不编写大段抓取或 SQL。
- 数据层不导入 FastAPI、Flutter 或 HTTP 请求对象。

后端是书籍、任务、阅读进度、模型设置和文件的唯一权威来源。客户端文件选择器产生的 URI 或临时路径
只属于对应客户端设备：导入时上传文件，导出时下载服务端产物，任何 API 都不得要求 Linux 后端写入
客户端路径。设备 TTS 始终在客户端运行；OCR、抓取与翻译能力属于后端，并通过能力握手暴露。

## 3. 目录职责

```text
lib/
├─ app/                 # 组合根、主题、AppScope、全局偏好
├─ core/
│  ├─ api/              # HTTP 客户端与统一异常
│  ├─ backend/          # 远程后端连接状态与安全凭据
│  ├─ models/           # 跨功能领域模型
│  └─ state/            # 通用加载状态
├─ features/<feature>/  # 页面、控制器与本功能 Widget
└─ shared/              # 至少两个 Feature 使用的轻量共享能力

python-backend/
├─ app/api/             # 路由声明
├─ app/application.py   # FastAPI 组装
├─ app/models.py        # 请求、响应与领域数据模型
├─ app/db.py            # SQLite 与持久化
├─ app/scraper.py       # 外部站点、下载、OCR、翻译适配
└─ tests/               # 后端测试

deploy/linux/           # Linux 原生安装、systemd 服务、更新与连接信息脚本

android/                # Android Manifest、Gradle 与原生资源
windows/                # Windows Runner、插件注册与原生资源
assets/                 # 品牌图片、文档截图与应用图标
```

文件放置原则：

- 只服务一个功能的组件放进该 Feature，不提前放入 `shared`。
- `shared` 不导入具体 Feature。
- 应用启动只负责依赖组装，不实现业务。
- Android / Windows Runner 只承载 Flutter、权限与平台资源，不放业务逻辑。

## 4. 单一职责与拆分

出现任一情况就应拆分：

- 同一文件同时包含 UI、网络、持久化或进程管理中的两个以上职责；
- 一个 Widget 有多个独立可测试区域；
- 同一段解析、状态转换或错误处理出现两次；
- 修改一个功能需要理解大量无关代码；
- 测试必须依赖整个应用才能验证一个小行为。

建议阈值不是机械上限，但超出时必须在评审中说明：

| 文件类型 | 建议上限 | 首选拆分方向 |
| --- | ---: | --- |
| Flutter 页面 | 300 行 | 局部 Widget、Controller、对话框 |
| 通用 Widget | 220 行 | 子控件、样式模型 |
| Controller / Service | 260 行 | 按用例或资源拆分 |
| Dart Model | 220 行 | 按领域拆分 |
| Python Router | 300 行 | 按资源拆分 |
| Python Service / Adapter | 400 行 | 按站点、用例或协议拆分 |
| 测试文件 | 400 行 | 按行为组拆分 |

函数通常不超过 50 行，嵌套不超过 3 层。优先使用早返回、语义化私有函数和不可变值。

## 5. 命名与配置

- Dart 文件、Python 模块：`snake_case`。
- Dart 类型、Widget、Python 类：`PascalCase`。
- 变量、函数、字段：Dart 使用 `lowerCamelCase`，Python 使用 `snake_case`。
- 布尔值以 `is`、`has`、`can`、`should` 开头。
- 禁止含糊的 `data`、`item`、`manager`；必须表达业务含义。
- 端口、超时、并发数、路径和服务地址集中为常量或配置，禁止散落魔术值。

## 6. 文档与仓库卫生

- 根目录只允许 `README.md`；许可证文件不属于 Markdown，可保留。
- 开发规范只写入本目录已有主题，避免新增重复文档。
- 临时分析、调试记录和生成报告不得提交。
- `build/`、`release/`、缓存、数据库与 IDE 状态必须被忽略。
- 删除技术栈时同时删除依赖、配置、脚本、CI、文档和测试遗留。

## 7. 架构变更

以下变更应在实现前形成明确决策，并在 PR 中说明替代方案：

- 新增顶层目录或第三方框架；
- 改变 Flutter 与后端通信协议；
- 改变数据目录、Schema 或迁移策略；
- 改变远程后端连接、认证与服务器切换方式；
- 引入认证、远程监听或外部服务；
- 改变单用户数据归属、远程文件传输或 Linux 部署方式；
- 大规模移动文件或破坏兼容性。
