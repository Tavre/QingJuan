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
4. 错误、空状态、键盘与窗口适配；
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

GitHub Actions 必须验证：

- Windows 上 Flutter 格式化、分析、测试和 Release 构建；
- Python 上 Ruff 与 Pytest。

Dependabot 只维护当前技术栈：

- `pub`：Flutter/Dart；
- `pip`：FastAPI 后端；
- `github-actions`：CI Actions。

升级依赖时先阅读变更说明，尤其关注 Dart SDK、Windows 插件、FastAPI/Pydantic 和 PyInstaller。
不要在一个 PR 中无差别升级所有大版本。

## 5. Windows 发布

发布前：

1. 更新 `pubspec.yaml` 版本；
2. 执行全部质量门禁；
3. 执行 `tool/build_windows.ps1`；
4. 在无 Python 开发环境的 Windows 机器启动；
5. 验证自动后端、导入、任务、阅读、设置和退出；
6. 扫描发布目录，不得包含数据库、缓存、日志和密钥；
7. 记录已知站点兼容性与实验功能。

分发时打包整个 `release/qingjuan-windows/`，不能只提供单个 EXE。

## 6. 技术栈迁移规则

当前唯一客户端技术栈是 Flutter Windows。以下内容视为遗留并禁止重新引入：

- Vue、Vite、Pinia、Vitest、npm 前端依赖；
- Electron 主进程、preload 与 electron-builder；
- Capacitor、Android、iOS、PWA、Service Worker；
- Web 专用 Fluent UI 包；
- 手机端底部导航和移动端断点。

删除旧栈时必须成套清理：

- 源代码；
- 依赖清单和 lockfile；
- 构建与测试配置；
- CI、Dependabot 和脚本；
- 文档、示例和生成目录；
- 未使用的条件分支与资源。

任何恢复多平台支持的提案都属于新的产品与架构决策，不能作为普通功能顺手加入。

## 7. 禁止的反模式

- 所有功能写进 `main.dart`、单个页面或 `main.py`；
- Widget 直接操作 HTTP、SQLite 或进程；
- 为复用一行样式创建无语义抽象；
- 引入第二套 UI 框架；
- 隐藏异常、空 `catch` 或无限重试；
- 硬编码密钥、用户路径、远程地址或魔术端口；
- 默认让无认证后端监听局域网；
- 删除目录前不验证绝对目标；
- 用公网实时请求作为稳定单元测试；
- 在根目录增加无用 Markdown；
- 提交 `build/`、`release/`、数据库、缓存或个人内容。

## 8. 技术债

- 在改动触及的范围内偿还技术债，不借机重写无关模块。
- 超过建议体积的旧文件，新增功能优先提取明确领域而不是继续堆叠。
- 临时方案必须有可搜索说明、风险、退出条件和跟踪 Issue。
- 不能立即修复的问题应在交付报告中明确，不伪装成已完成。
