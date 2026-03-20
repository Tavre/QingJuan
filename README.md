<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://img.alicdn.com/imgextra/i1/O1CN014EK1rl1kxYRRDVU4c_!!2215879134750-0-fleamarket.jpg" width="256" height="256" />
</p>

<div align="center">
<!-- prettier-ignore-start -->
<!-- markdownlint-disable-next-line MD036 -->
_青卷 QingJuan_
<!-- prettier-ignore-end -->

青卷是一款基于 `Tauri 2 + Vue 3 + Python` 的桌面小说集成工具，面向“抓取、整理、下载、翻译、阅读”一体化使用场景。
</div>

项目当前已经支持：
- 网络小说链接导入
- 本地 TXT 小说导入与自动拆章
- 章节下载、翻译任务队列
- 阅读进度持久化
- 自定义书籍封面
- 本地书籍删除与资源清理

## 预览

- 桌面端书架管理
- 书籍详情与章节列表
- 阅读器与主题切换
- AI 翻译配置与任务日志

如需补充截图，建议发布前在仓库中加入 `docs/` 或 `assets/` 目录后在此处引用。

## 功能特性

- 多来源导入：支持网页链接(哔哩轻小说...)导入，也支持本地 `TXT / TEXT / Markdown` 文本导入
- 本地文库：章节、封面、插图、翻译结果统一写入本地用户数据目录
- AI 翻译：兼容 `OpenAI / New API / Anthropic / Custom` 配置
- 任务队列：支持下载、翻译、失败重试、日志查看
- 阅读体验：支持应用主题、阅读主题、字体大小、自定义正文颜色与背景色
- 封面管理：支持抓取封面与手动上传自定义封面
- 数据持久化：重启应用后书架、设置、阅读进度保留

## 技术栈

- 前端：`Vue 3`、`TypeScript`、`Vite`
- 桌面壳：`Tauri 2`
- 后端：`FastAPI`
- 数据存储：`SQLite`
- 打包：`PyInstaller` + `Tauri bundle`

## 项目结构

```text
.
├─ src/                    # Vue 前端
├─ src-tauri/              # Tauri 壳、Rust 入口与打包配置
├─ python-backend/         # FastAPI 后端、抓取器、SQLite、sidecar 构建脚本
├─ ui示例/                  # UI 参考图
├─ qj_icon.png             # 图标资源
├─ qj_icon_1.png           # 图标资源
└─ README.md
```

## 环境要求

- Node.js 22+
- npm 10+
- Python 3.13+
- Rust / Cargo
- Windows 建议已安装：
  - WebView2 Runtime
  - Visual Studio C++ Build Tools

## 安装依赖

```bash
npm install
python -m pip install -r python-backend/requirements.txt pyinstaller
```

## 本地开发

开发命令会自动先重建 Python sidecar：

```bash
npm run tauri:dev
```

如果只需要单独构建 Python sidecar：

```bash
npm run backend:build
```

## 生产构建

```bash
npm run tauri:build
```

构建完成后，安装包默认位于：

- `src-tauri/target/release/bundle/msi/`
- `src-tauri/target/release/bundle/nsis/`

## 常用命令

```bash
npm run build
python -m py_compile python-backend/app/main.py
cargo check --manifest-path src-tauri/Cargo.toml
npm run backend:build
npm run tauri:build
```

## 数据存储

默认使用本机用户数据目录。

Windows 默认路径：

```text
%LOCALAPPDATA%/QingJuan/data/
```

该目录通常包含：

- `qingjuan.db`
- `library/`
- 章节文本
- 翻译文本
- 插图资源
- 封面资源

如需覆盖数据目录，可设置环境变量：

```bash
QINGJUAN_DATA_DIR
```

## 发布说明

- Tauri sidecar 依赖：`src-tauri/binaries/qingjuan-backend-x86_64-pc-windows-msvc.exe`
- 开发与打包时，脚本会自动重建 sidecar，避免前后端代码不同步
- 当前抓取器已对部分轻小说站点做适配，其余站点可继续按规则扩展

## Roadmap

- 支持更多站点适配器
- 支持 `EPUB / DOCX` 本地导入
- 支持阅读器插图放大与更丰富的排版控制
- 支持导出整书或离线归档

## 许可证

本项目使用 [GNU General Public License v3.0](./LICENSE) 发布。

你可以在遵守 GPL v3 条款的前提下使用、修改和分发本项目及其衍生版本。

## 作者

- Author: `Tavre`

## 致谢

- Tauri
- Vue
- FastAPI
- 开源社区提供的各类基础工具与依赖
