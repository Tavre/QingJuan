# 青卷开发规范

本目录是青卷的唯一开发规范来源。所有后续编码、重构、评审与发布均应遵循这里的约束。

## 当前发布基线

- 当前已发布版本：`1.7.2+23`，对外版本为 `v1.7.2`；仓库发布候选版本为
  `1.7.3+24`。V1.7.3 保留并滑动展示手机端完整书籍简介，关闭文本输入放大镜但保留复制粘贴，并增强番茄网页正文缺失时的重试与回退。
- Windows 客户端支持“本机后端”和“Linux 远程后端”两种显式连接模式；Android 仍只连接既有 Linux FastAPI 服务。
- Windows 发布包必须包含由 PyInstaller 构建的本机伴随后端。本机模式只监听回环地址，不使用连接 Token；远程模式
  必须配置地址与 Token，连接失败时不得自动回退本机。
- 既有功能基线包括：本地文件上传导入、单章与多章导出、设备 TTS、链接任务与实时日志、单一
  OpenAI 兼容翻译配置，以及 Linux RapidOCR 漫画翻译链路；v1.3.4 增加 OCR 容器恢复、竖排合并和超长译文安全缩放。
- 后续版本不得破坏现有后端数据、导入导出格式、阅读进度和设置；确需不兼容变更时必须提供迁移说明和测试。

## 产品与平台边界

- 产品形态：带可选本机后端的 Windows 桌面客户端、Android 手机与平板远程客户端，以及随后端同源提供的管理员界面。
- 客户端：Flutter + Dart + `fluent_ui`。
- 管理界面：React + TypeScript + Ant Design，用于管理当前 FastAPI 后端，不作为阅读客户端或 PWA。
- UI 基线：Flutter 客户端使用 Fluent 视觉语言并适配 Windows 键鼠与 Android 触控；管理界面遵循 Ant Design。
- 后端：Python + FastAPI；Windows 可使用随包回环进程，Linux 使用单用户远程服务。
- 连接：Windows 本机模式固定使用 `http://127.0.0.1:19453`；Windows 远程模式与 Android 必须由用户配置服务器，
  私有网络可使用 HTTP，其他网络必须使用 HTTPS，并启用 Bearer Token 认证。
- 存储：当前选中的后端持有 SQLite、书籍文件、任务与服务凭据；客户端只保存非敏感偏好和平台安全存储
  保护的远程连接 Token。本机与 Linux 数据目录互不自动同步。
- 不支持：Android 本地 Python 后端、iOS、面向读者的 Web/PWA 客户端、Electron、Capacitor、Vue 客户端。

`fluent_ui` 是 Flutter 社区维护的 Fluent 组件库，不是
`microsoft/fluentui` 仓库中的 React/Web 包。项目在 Flutter 技术栈中使用它实现控件，
并以 Microsoft Fluent 的布局、状态、动效和可访问性原则作为设计依据。

## 文档导航

| 文档 | 内容 | 主要适用范围 |
| --- | --- | --- |
| [原则与架构](./01-principles-and-architecture.md) | 依赖方向、模块边界、目录与拆分阈值 | 全仓库 |
| [UI 与可访问性](./02-ui-and-accessibility.md) | Fluent、Android 触控、响应式布局与语义 | `lib/features/`、`lib/shared/` |
| [Flutter 客户端](./03-frontend.md) | Dart、Widget、Controller、API 与状态管理 | `lib/`、`test/` |
| [后端、管理界面与客户端集成](./04-backend-and-android.md) | FastAPI、认证、React 管理界面、Windows / Android 与 Linux 部署 | `python-backend/`、`admin-web/`、`windows/`、`android/`、`deploy/linux/` |
| [质量与测试](./05-quality-and-testing.md) | TDD、测试分层、门禁、验收与完成定义 | 所有变更 |
| [工作流与迁移](./06-workflow-and-migration.md) | Git、PR、发布、技术债与禁止项 | 贡献流程 |

## 开发环境与依赖基线

### 必需工具

| 工具 | 支持基线 | 用途与要求 |
| --- | --- | --- |
| Windows 10 / 11 x64 | 客户端运行与 Windows 开发主机 | 构建、运行和调试 Windows / Android 客户端；Windows 可运行随包本机后端 |
| Linux / macOS | Flutter 支持的当前开发主机 | Android 客户端开发与调试 |
| Android | Android 8.0（API 26）或更高版本 | 客户端运行平台；手机上不需要 Python 环境 |
| Linux | x86_64、systemd、CPython 3.11+ | 远程后端运行平台；使用原生虚拟环境，不承载 Flutter 客户端 |
| Flutter | `3.24.3` stable | 必须使用 stable 版本；正式包禁止使用 master、beta 或其他未验证版本 |
| Dart | `3.5.3` | 随 Flutter `3.24.3` 提供，不单独安装或升级 |
| Android SDK | `flutter doctor -v` 当前要求的 SDK、Platform Tools 与 Build Tools | 构建、安装与调试 APK |
| JDK | JDK 17 | Gradle 与 Android 构建；优先使用 Android Studio 随附版本 |
| Python | CPython `3.13.x` x64 | 后端开发、测试与 Linux 部署校验；不使用 Microsoft Store 的重定向别名 |
| Node.js | `20.19.x` 或 `22.12+` | 只用于构建和测试 `admin-web/`；Linux 运行时直接提供仓库内已构建静态资源 |
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
| 管理界面依赖 | `admin-web/package.json`、`admin-web/package-lock.json` | `npm ci --prefix admin-web` |

`requirements-dev.txt` 已包含后端运行、测试和 Windows PyInstaller 发布依赖。只调试远程客户端时不需要在开发机
启动 Python；修改后端、调试 Windows 本机模式或构建完整 Windows 包时必须安装该文件。不要在文档中复制完整三方包版本，
版本升级以依赖文件和 lockfile 为准。
仅修改 Flutter 客户端时不需要 Node.js。管理界面开发需要 Node.js/npm，但已部署 Linux 服务不在运行时安装或启动
Node.js，也不使用 WebView；手机端仍不需要 Python 环境。

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
USB 调试的真机。修改后端、调试 Windows 本机模式或构建完整 Windows 包时创建 `python-backend/.venv` 并安装
`requirements-dev.txt`；开发态 Windows 本机模式可从仓库启动该 Python，正式 Windows 包只启动随包可执行文件，
Android 不读取或复制 Python 运行时。

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

Windows 首次启动在没有既有远程配置时默认本机模式，按需启动随包后端；已有远程配置继续保持远程模式。
Android 首次启动显示服务器配置入口。远程模式填写 Linux FastAPI 根地址与连接 Token 并通过服务标识/API 版本握手后，
应用才加载书架、插件与书源规则、任务及设置；连接失败时保留配置表单和诊断，且不回退本机。切换模式或服务器后
必须停止旧轮询、清空旧页面状态并从新后端重新加载。Linux 部署入口、认证和数据目录约束见
[后端、管理界面与客户端集成](./04-backend-and-android.md)。

静态检查、测试命令和三轮验证要求见[质量与测试](./05-quality-and-testing.md)，
Windows 与 Android 构建、发布流程见[工作流与迁移](./06-workflow-and-migration.md)。

## 最低强制要求

1. Flutter UI 使用 `fluent_ui` 和项目共享 Widget；`admin-web/` 只使用 Ant Design，不在任一界面混用两套组件体系。
2. 新功能按 Feature 拆分；页面不直接处理原始 HTTP、数据库或进程。
3. 网络 DTO、领域模型、状态控制与展示组件分离。
4. 任何异步界面都有加载、空、成功、失败和重试状态。
5. 所有用户可见错误使用中文且可执行，不暴露堆栈或密钥。
6. 改动同步补充测试，提交前完成格式化、静态分析、测试和 Windows / Android 构建。
7. 根目录只保留 `README.md`；其他 Markdown 必须进入 `docs/development/` 的对应区块。
8. 不提交密钥、数据库、缓存、下载内容、日志、临时构建产物和个人数据；
   `python-backend/app/admin_static/` 是 Linux 运行时所需、由 CI 校验的唯一管理界面构建产物例外。
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
