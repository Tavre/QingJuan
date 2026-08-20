# 工作流、发布与迁移

## 1. 分支与提交

- 一个分支和 PR 聚焦一个可描述目标。
- 推荐提交前缀：`feat:`、`fix:`、`refactor:`、`test:`、`docs:`、`build:`、`chore:`。
- 不混入无关格式化、个人设置、下载资源或生成文件。
- 大重构分为可验证阶段，每阶段保持可构建。
- 用户已有未提交改动不得擅自覆盖、重置或清理。

## 2. 功能开发流程

开始前：

1. 阅读相关开发规范和现有测试；
2. 明确用户路径、数据来源、错误与权限边界；
3. 确定 Model、Controller、API 和 Widget 的职责；
4. 为行为写失败测试。

实现顺序：

1. 领域模型和 API 契约；
2. Controller 用例与状态；
3. 最小 Fluent UI；
4. 错误、空状态、触控、系统返回与手机/平板适配；
5. 重构重复代码；
6. 三轮验证；
7. 同步 README 或对应规范。

## 3. Pull Request 要求

PR 描述应包含：

- 要解决的问题和不在范围内的内容；
- 用户可见变化；
- 架构与依赖变化；
- 安全、数据迁移和兼容性影响；
- 测试命令与人工验证；
- UI 变化的亮色/深色截图（如适用）。

评审顺序：

1. 安全、数据丢失和路径边界；
2. 行为正确与错误恢复；
3. 依赖方向与模块职责；
4. 测试质量；
5. Fluent UI、一致性和可访问性；
6. 性能、命名和细节。

## 4. CI 与依赖

Pull Request、`main` / `master` 推送（包括 PR 合并后的推送）和手动运行必须先并行通过 4 个 CI 门禁：

1. Flutter 格式化、分析与测试；
2. Python Ruff 与 Pytest；
3. Bash/systemd 校验，以及 Linux 原生后端的健康、认证和数据目录冒烟测试。
4. React 管理界面的 TypeScript、测试、生产构建，以及提交的静态资源与构建结果一致性校验。

4 个门禁全部成功后，CI 才并行构建 Android Release APK 与包含随包后端的 Windows x64 组合包，并将两端产物上传到
该次 Actions 运行。任一门禁失败时不得启动产物构建。Android 使用固定 JDK 17，两个客户端统一使用
Flutter `3.24.3`；构建不得依赖开发机全局 Gradle、签名文件或已缓存的私有配置。

Dependabot 只维护当前技术栈：

- `pub`：Flutter/Dart；
- `pip`：FastAPI 后端；
- `npm`：React/Ant Design 管理界面；
- `github-actions`：CI Actions。

升级依赖时先阅读变更说明，尤其关注 Dart SDK、Android Gradle Plugin、平台插件和 FastAPI/Pydantic。
不要在一个 PR 中无差别升级所有大版本。

## 5. Windows 与 Android 发布

### 版本规则

- `pubspec.yaml` 是 Windows / Android 客户端与后端的唯一发布版本源，格式为
  `major.minor.patch+build`；对外发布标签使用 `vmajor.minor.patch`。
- 默认情况下，每次准备发布更新都自动递增 patch 和 build。例如
  `1.0.0+5` 的下一次普通更新为 `1.0.1+6`。
- 用户或发布负责人明确指定版本时，以指定的语义版本为准，build 仍必须大于上一版；
  major、minor、预发布版或跳号不得自行推断。
- 日常调试和重复构建不得修改版本号；只有准备形成新的发布更新时才执行递增。
- 修改版本后必须验证 Android `versionName` / `versionCode`、FastAPI 元数据与 Windows 文件属性均来自同一版本源，禁止在
  Dart、Python、Kotlin、C++ 或发布脚本中新增独立硬编码版本。
- 当前已发布基线为 `1.7.3+24`；后续正式发布的 build 必须大于 `24`，不得回退版本或复用已发布 build。
- 本次阅读排版、顶部状态栏、Token 粘贴键与音量键阅读修复使用 `1.7.4+25`，对外标签为 `v1.7.4`。

发布前：

1. 按上述规则更新 `pubspec.yaml` 版本；
2. 执行全部质量门禁；
3. 安装 `python-backend/requirements-dev.txt`，执行 `./tool/build_windows.ps1` 与 `flutter build apk --release`，商店分发时再执行
   `flutter build appbundle --release`；
4. 在没有 Python 环境的 Windows 10 / 11 与 API 26 Android 设备安装；
5. Android 验证首次远程连接；Windows 分别验证本机后端启动与 Linux 远程连接，并覆盖导入、任务、阅读、设置、切换和退出；
6. 扫描产物与构建配置；Windows 只允许预期的随包后端可执行文件，不得包含数据库、缓存、日志、Token、签名材料和密钥；
7. 记录已知站点兼容性与实验功能。

合并并确认 `main` 的 CI 全绿后，推送与 `pubspec.yaml` 语义版本一致的标签即可触发
`.github/workflows/release.yml`：

```powershell
git tag v1.7.4
git push origin v1.7.4
```

发布工作流重新执行 Flutter 格式化、分析、测试，执行 `python -m ruff check app tests` 与
`python -m pytest`，再并行构建 Windows ZIP 与签名 Android APK。只有标签、`pubspec.yaml`、两个客户端
版本和后端元数据版本完全一致时，工作流才可上传两端产物及 SHA-256 并创建 GitHub Release。
不得手工跳过失败门禁或从未提交的本地工作区制作正式发布包。

GitHub 产物命名为 `QingJuan-v<语义版本>-windows-x64.zip` 与
`QingJuan-v<语义版本>-android.apk`。发布前必须：

- 验证 `versionName`、`versionCode`、包名和签名证书；
- 在最低支持版本与当前 Android 版本安装并连接真实 Linux 后端；
- 在 Windows 10 / 11 x64 安装，分别启动随包本机后端并连接真实 Linux 后端；
- 确认 Windows ZIP 包含且只能包含预期随包后端程序，APK 不包含 Python；两端都不得包含生产数据或凭据；
- 扫描 `.env`、数据库、日志、设置、Token、签名文件和凭据，并记录 SHA-256。

## 6. 技术栈迁移规则

面向读者的唯一客户端技术栈是 Flutter Windows / Android；React + Ant Design 仅用于同源 Linux 管理界面。
以下内容视为遗留或不在范围内并禁止重新引入：

- Vue、Pinia 和面向读者的 Web 客户端；
- Electron 主进程、preload 与 electron-builder；
- Capacitor、iOS、PWA、Service Worker；
- 在 Flutter 客户端中使用 Web 专用 Fluent UI 包，或在管理界面中混入 Flutter/Material 页面组件；
- 独立于共享 FastAPI 代码的 Windows 专用业务后端分支；Windows 伴随后端必须由同一 `python-backend` 可复现构建。

删除旧栈时必须成套清理：

- 源代码；
- 依赖清单和 lockfile；
- 构建与测试配置；
- CI、Dependabot 和脚本；
- 文档、示例和生成目录；
- 未使用的条件分支与资源。

任何恢复 iOS 或面向读者的 Web 客户端的提案都属于新的产品与架构决策，不能把管理界面扩展成第二套阅读客户端。

### Windows 双模式兼容规则

- Android 始终忽略旧 `local` 偏好并要求用户显式填写 Linux 服务地址和 Token；APK 不包含本机后端。
- Windows 保留旧 `qingjuan.backendMode`；V1.4 没有模式字段但已保存远程地址的安装迁移为远程模式，完全没有服务器配置的
  Windows 安装默认本机模式。迁移不得覆盖已保存的远程地址或安全存储 Token。
- Windows 本机模式固定回环地址且不使用 Token；远程模式保存前完成认证和 API 版本握手，失败时保留输入和诊断，
  成功后再切换数据源。远程失败不得隐式回退本机。
- 新版把模式选择保存为 `qingjuan.backendMode`，把 Linux 地址保存到独立的 `qingjuan.backend.remote.url`，Token 继续只存安全
  存储；本机档案由固定回环地址和空 Token 构成，不复用 Linux 字段。首次读取时只把旧 `qingjuan.backendUrl` 迁移为 Linux
  地址，且不得把旧回环地址误当成 Linux 配置。切换到本机时继续安全保留 Linux 配置，切回远程无需重新输入。
- 本机后端数据位于 Windows 发布目录的 `backend/data/`，Linux 数据位于部署数据目录，二者不自动同步。迁移数据时先复制到
  隔离目录并校验清单，不得让两个进程同时打开同一数据库。
- 旧 API 的绝对 `localPath` 只可用于内部数据迁移，不能继续进入公开 DTO。
- 旧导出请求中的 `targetPath` 迁移为服务端产物下载；漫画图片目录迁移为 ZIP，导出内容与顺序保持兼容。
- 现有 Windows 数据迁移到 Linux 时将绝对路径转换为相对存储键；不得直接复用 Windows 路径。
- 设置中的既有密钥保留在后端，升级后的读取接口只返回配置状态；客户端空值不得意外清除已有密钥。
- 回滚必须保留升级前数据库和文件完整备份；新版本写入后不得让旧版本直接打开同一生产数据目录。

## 7. 禁止的反模式

- 所有功能写进 `main.dart`、单个页面或 `main.py`；
- Widget 直接操作 HTTP、SQLite 或进程；
- 为复用一行样式创建无语义抽象；
- 引入第二套 UI 框架；
- 隐藏异常、空 `catch` 或无限重试；
- 硬编码密钥、用户路径、远程地址或魔术端口；
- 默认让无认证后端监听局域网；
- 将连接 Token 写入 `SharedPreferences`、命令行、URL、日志或第三方请求；
- 把 Android URI/目标路径发送给 Linux 后端，或把服务端绝对路径作为 API 结果；
- 使用多个 Uvicorn worker 或多个 systemd 实例共享同一 SQLite 数据目录；
- 删除目录前不验证绝对目标；
- 用公网实时请求作为稳定单元测试；
- 在根目录增加无用 Markdown；
- 提交 `build/`、`release/`、数据库、缓存或个人内容。

## 8. 技术债

- 在改动触及的范围内偿还技术债，不借机重写无关模块。
- 超过建议体积的旧文件，新增功能优先提取明确领域而不是继续堆叠。
- 临时方案必须有可搜索说明、风险、退出条件和跟踪 Issue。
- 不能立即修复的问题应在交付报告中明确，不伪装成已完成。
