# 青卷开发规范

本目录是青卷的唯一开发规范来源。所有后续编码、重构、评审与发布均应遵循这里的约束。

## 当前发布基线

- 上一发布版本：`1.3.4+16`，对外版本为 `v1.3.4`；仓库开发版本为
  `1.4.0+17`。从该开发版本开始，客户端主线为 Flutter Windows 与 Android。
- Windows 与 Android 客户端只连接既有 Linux FastAPI 服务，不在客户端设备安装、打包或启动 Python。
- Windows 本机伴随后端与 PyInstaller 打包继续保持退役；Windows 发布链路只生成纯 Flutter 远程客户端。
- 既有功能基线包括：本地文件上传导入、单章与多章导出、设备 TTS、链接任务与实时日志、单一
  OpenAI 兼容翻译配置，以及 Linux RapidOCR 漫画翻译链路；v1.3.4 增加 OCR 容器恢复、竖排合并和超长译文安全缩放。
- 后续版本不得破坏现有后端数据、导入导出格式、阅读进度和设置；确需不兼容变更时必须提供迁移说明和测试。

## 产品与平台边界

- 产品形态：Windows 桌面客户端，以及 Android 手机与平板客户端。
- 客户端：Flutter + Dart + `fluent_ui`。
- UI 基线：统一 Fluent 视觉语言，并分别适配 Windows 键鼠与 Android 触控习惯。
- 后端：Python + FastAPI，仅部署为 Linux 单用户远程服务。
- 连接：客户端必须由用户配置服务器；私有网络可使用 HTTP，其他网络必须使用 HTTPS，并启用
  Bearer Token 认证。
- 存储：Linux 后端持有 SQLite、书籍文件、任务与服务凭据；客户端只保存非敏感偏好和平台安全存储
  保护的连接 Token。
- 不支持：Windows 或手机本地 Python 后端、iOS、Web、PWA、Electron、Capacitor、Vue/Vite 客户端。

`fluent_ui` 是 Flutter 社区维护的 Fluent 组件库，不是
`microsoft/fluentui` 仓库中的 React/Web 包。项目在 Flutter 技术栈中使用它实现控件，
并以 Microsoft Fluent 的布局、状态、动效和可访问性原则作为设计依据。

## 文档导航

| 文档 | 内容 | 主要适用范围 |
| --- | --- | --- |
| [原则与架构](./01-principles-and-architecture.md) | 依赖方向、模块边界、目录与拆分阈值 | 全仓库 |
| [UI 与可访问性](./02-ui-and-accessibility.md) | Fluent、Android 触控、响应式布局与语义 | `lib/features/`、`lib/shared/` |
| [Flutter 客户端](./03-frontend.md) | Dart、Widget、Controller、API 与状态管理 | `lib/`、`test/` |
| [后端与客户端集成](./04-backend-and-android.md) | FastAPI、认证、Windows / Android 平台与 Linux 部署 | `python-backend/`、`windows/`、`android/`、`deploy/linux/` |
| [质量与测试](./05-quality-and-testing.md) | TDD、测试分层、门禁、验收与完成定义 | 所有变更 |
| [工作流与迁移](./06-workflow-and-migration.md) | Git、PR、发布、技术债与禁止项 | 贡献流程 |

## 开发环境与依赖基线

### 必需工具

| 工具 | 支持基线 | 用途与要求 |
| --- | --- | --- |
| Windows 10 / 11 x64 | 客户端运行与 Windows 开发主机 | 构建、运行和调试 Windows / Android 客户端；不得作为生产后端替代品 |
| Linux / macOS | Flutter 支持的当前开发主机 | Android 客户端开发与调试 |
| Android | Android 8.0（API 26）或更高版本 | 客户端运行平台；手机上不需要 Python 环境 |
| Linux | x86_64、systemd、CPython 3.11+ | 必需的远程后端运行平台；使用原生虚拟环境，不承载 Flutter 客户端 |
| Flutter | `3.24.3` stable | 必须使用 stable 版本；正式包禁止使用 master、beta 或其他未验证版本 |
| Dart | `3.5.3` | 随 Flutter `3.24.3` 提供，不单独安装或升级 |
| Android SDK | `flutter doctor -v` 当前要求的 SDK、Platform Tools 与 Build Tools | 构建、安装与调试 APK |
| JDK | JDK 17 | Gradle 与 Android 构建；优先使用 Android Studio 随附版本 |
| Python | CPython `3.13.x` x64 | 后端开发、测试与 Linux 部署校验；不使用 Microsoft Store 的重定向别名 |
| PowerShell | Windows PowerShell 5.1 或 PowerShell 7 | Windows 开发主机上的文档命令 |
| Git | 当前受支持版本 | 源码和子模块管理；本项目当前没有 Git 子模块 |

Flutter 与 Dart 视为同一套工具链。升级 Flutter 时必须在同一个变更中同步 Windows、Android Gradle 配置、
`.github/workflows/ci.yml`、本文档和两个客户端的真实构建结果。
本机安装了多个 Flutter 或 Python 时，先用 `Get-Command flutter` 和 `Get-Command python`
确认当前 PowerShell 会话解析到的可执行文件，不以 IDE 状态栏显示为准。

Android 构建依赖由 Gradle Wrapper、Flutter 和 Android SDK 管理。不要提交本机 SDK 路径、签名密钥、
`key.properties` 或生成产物；正式签名通过受保护的 CI Secret 或发布负责人本机安全配置提供。

### 项目依赖来源

| 范围 | 权威文件 | 安装命令 |
| --- | --- | --- |
| Flutter 运行与插件依赖 | `pubspec.yaml`、`pubspec.lock` | `flutter pub get` |
| Python 运行依赖 | `python-backend/requirements.txt` | `python -m pip install -r python-backend/requirements.txt` |
| Python 开发与发布依赖 | `python-backend/requirements-dev.txt` | `python -m pip install -r python-backend/requirements-dev.txt` |

`requirements-dev.txt` 已包含后端运行和测试依赖。客户端日常开发不需要在开发机启动 Python；
只有修改后端时才安装该文件。不要在文档中复制完整三方包版本，版本升级以依赖文件和 lockfile 为准。
项目不需要 Node.js、npm、WebView 前端工具链或手机端 Python 环境。

### 首次配置

在仓库根目录执行：

```powershell
flutter config --enable-android
flutter config --enable-windows-desktop
flutter doctor -v
flutter pub get
flutter devices
```

`flutter doctor -v` 必须确认 Flutter 为 `3.24.3`，Android toolchain 无错误，并能识别模拟器或已开启
USB 调试的真机。修改后端时再创建 `python-backend/.venv` 并安装 `requirements-dev.txt`；客户端启动
不读取系统 Python，也不向手机复制 Python 运行时。

### 可选运行能力

- 设备 TTS 使用操作系统已安装的语音引擎与语音包；客户端不得把正文上传到未明确配置的朗读服务。
- Linux 后端使用 RapidOCR，并通过已配置的 Chromium 可执行文件提供浏览器会话回退。
- 翻译和可选视觉识别需要用户自行配置 OpenAI 兼容 API，不是本地开发、测试或启动的前置条件。
- `QINGJUAN_DATA_DIR` 只用于覆盖开发数据目录，不应写入全局环境或指向仓库外未确认的生产数据。

启动 Android 调试：

```powershell
flutter run -d <设备 ID>
```

启动 Windows 调试：

```powershell
flutter run -d windows
```

首次启动显示服务器配置入口。用户填写 Linux FastAPI 根地址与连接 Token 并通过服务标识/API 版本握手后，
应用才加载书架、书源、任务与设置；连接失败时保留配置表单和诊断，不启动任何本地后端。切换服务器后
必须清空旧页面状态并从新服务器重新加载。Linux 部署入口、认证和数据目录约束见
[后端与 Android 集成](./04-backend-and-android.md)。

静态检查、测试命令和三轮验证要求见[质量与测试](./05-quality-and-testing.md)，
Windows 与 Android 构建、发布流程见[工作流与迁移](./06-workflow-and-migration.md)。

## 最低强制要求

1. UI 使用 `fluent_ui` 和项目共享 Widget，不引入第二套 UI 框架。
2. 新功能按 Feature 拆分；页面不直接处理原始 HTTP、数据库或进程。
3. 网络 DTO、领域模型、状态控制与展示组件分离。
4. 任何异步界面都有加载、空、成功、失败和重试状态。
5. 所有用户可见错误使用中文且可执行，不暴露堆栈或密钥。
6. 改动同步补充测试，提交前完成格式化、静态分析、测试和 Windows / Android 构建。
7. 根目录只保留 `README.md`；其他 Markdown 必须进入 `docs/development/` 的对应区块。
8. 不提交密钥、数据库、缓存、下载内容、日志、构建产物和个人数据。
9. 无认证服务不得监听非回环地址；客户端不得向非青卷同源地址发送连接 Token。

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
- 客户端开发命令必须能在 Windows PowerShell 执行；Linux 部署命令使用明确标注的 Bash 代码块。
