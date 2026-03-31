<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://img.alicdn.com/imgextra/i1/O1CN014EK1rl1kxYRRDVU4c_!!2215879134750-0-fleamarket.jpg" width="256" height="256" />
</p>

<div align="center">
<!-- prettier-ignore-start -->
<!-- markdownlint-disable-next-line MD036 -->
青卷 QingJuan
<!-- prettier-ignore-end -->

青卷是一款基于 `Tauri 2 + Vue 3 + Python` 的桌面内容集成工具，面向“抓取、整理、下载、翻译、阅读”一体化使用场景，当前同时覆盖小说与漫画工作流。
</div>

项目当前已经支持：
- 网络小说链接导入
- 网络漫画链接导入
- 本地 TXT 小说导入与自动拆章
- 章节下载、翻译任务队列
- 阅读进度持久化与继续阅读
- 自定义书籍封面
- 本地书籍删除与资源清理
- 多站点小说 / 漫画目录与章节解析

## 预览

- 桌面端书架管理
- 书籍详情与章节列表
- 阅读器与主题切换
- AI 翻译配置与任务日志


## 功能特性

- 多来源导入：支持网页小说 / 漫画链接导入，也支持本地 `TXT / TEXT / Markdown` 文本导入
- 本地文库：章节、封面、插图、翻译结果统一写入本地 `data/` 目录
- AI 翻译：兼容 `OpenAI / New API / Anthropic / Grok2API / Custom` 配置
- 漫画翻译：后端内置调用 OpenAI 兼容图片编辑接口，直接输出翻译后图片与逐页译文。
- 任务队列：支持下载、翻译、失败重试、日志查看
- 漫画支持：支持 18comic / Bika 章节抓取、逐页下载、图片阅读、逐页译文与翻译后图片资源
- 阅读体验：支持应用主题、阅读主题、字体大小、自定义正文颜色与背景色、章节选择、继续阅读、切章回顶
- 封面管理：支持抓取封面与手动上传自定义封面
- 数据持久化：重启应用后书架、设置、阅读进度保留；安装版默认保存在程序同级目录

## 已适配站点

### 已实装并验证通过

- 哔哩轻小说 / Linovelib
  - `https://www.linovelib.com/`
  - `https://www.bilinovel.com/`
- Kakuyomu
  - `https://kakuyomu.jp/works/16817139555217983105`
- 成为小说家吧 / 小説家になろう
  - `https://ncode.syosetu.com/n0833hi`
- Novel18 / ノクターンノベルズ
  - `https://novel18.syosetu.com/n3192gh`
- Pixiv 小说单篇 / 系列
  - `https://www.pixiv.net/novel/show.php?id=18304868`
  - `https://www.pixiv.net/novel/series/9406879`
- Hameln / ハーメルン
  - 已加入目录与正文解析适配
  - 示例链接是否可抓取取决于作品当前是否公开可访问
- Alphapolis / アルファポリス
  - `https://www.alphapolis.co.jp/novel/638978238/525733370`
  - Windows 下会调用系统 `Microsoft Edge` 的最小化浏览器会话通过 WAF 后再抓取目录与正文
- 18Comic / 禁漫天堂
  - `https://18comic.vip/`
  - 支持漫画预览、章节页抓取、图片下载与阅读阶段的图片修复
- Bika Web App / 哔咔
  - `https://bikawebapp.com/`
  - 支持漫画目录、章节与分页图片抓取；首次抓取时可自动创建并保存本地账户凭证

> 说明：Alphapolis 则通过本机 Edge 浏览器会话完成绕过与抓取，因此在首次请求时会比普通站点更慢。

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
说明：
- 当前漫画翻译链路不再依赖本地 `LaMa / torch / numpy` 擦字组件
- 漫画页翻译已改为后端内置流程，不再调用外部命令模板

## 漫画译图

- 不再开放“漫画 AI 命令 / 工作目录 / 超时”设置项
- 漫画译图直接复用当前默认翻译提供商的 `baseUrl`、`apiKey` 和 `model`
- 当前仅支持 OpenAI 兼容图片编辑接口：`openai`、`newapi`、`grok2api`、`custom`
- 漫画译图会严格使用你当前设置的模型，不做自动模型回退
- 若默认提供商为 `anthropic`，漫画译图不会执行，并会在任务日志中给出明确提示

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

安装版默认使用主程序同级 `data/` 目录。

Windows 安装版示例：

```text
D:/QingJuan/data/
```

开发环境默认路径：

```text
python-backend/data/
```

该目录通常包含：

- `qingjuan.db`
- `library/`
- 章节文本
- 翻译文本
- 插图资源
- 封面资源

如果安装目录下的 `data/` 为空，程序会尝试从旧版本用户目录迁移历史数据：

```text
%LOCALAPPDATA%/QingJuan/data/
```

如需覆盖数据目录，可设置环境变量：

```bash
QINGJUAN_DATA_DIR
```

## 发布说明

- Tauri sidecar 依赖：`src-tauri/binaries/qingjuan-backend-x86_64-pc-windows-msvc.exe`
- 开发与打包时，脚本会自动重建 sidecar，避免前后端代码不同步
- sidecar 会打包后端运行所需依赖与漫画抓取能力；漫画图片翻译由后端内置图片编辑流程处理。
- 当前抓取器已支持 Linovelib、Kakuyomu、Syosetu、Novel18、Pixiv、Hameln、Alphapolis、18Comic、Bika Web App 等站点
- Novelup 当前仍受 CloudFront 限制，后续可继续尝试 Cookie 复用 / 代理 / 浏览器登录态方案

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
