<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="LOGO" src="https://img.alicdn.com/imgextra/i1/O1CN014EK1rl1kxYRRDVU4c_!!2215879134750-0-fleamarket.jpg" width="256" height="256" />
</p>

<div align="center">
<!-- prettier-ignore-start -->
<!-- markdownlint-disable-next-line MD036 -->
青卷 QingJuan
<!-- prettier-ignore-end -->

青卷是一款基于 `Vue 3 + Fluent Web Components + Python / FastAPI` 的内容集成工具，面向“抓取、整理、下载、翻译、阅读”一体化使用场景，当前同时覆盖小说与漫画工作流。

当前版本已改为普通 Web 前端 + 本地 FastAPI 后端的运行方式，不再依赖 Tauri 桌面壳。左侧为 Fluent 风格导航栏，右侧为书架、Legado 书源管理、日志、设置、详情与阅读器功能区。
</div>

项目当前已经支持：
- 网络小说链接导入
- 网络漫画链接导入
- Legado / 阅读 App 书源 JSON 规则导入与管理
- 本地 TXT 小说导入与自动拆章
- 章节下载、翻译任务队列
- 阅读进度持久化与继续阅读
- 自定义书籍封面
- 本地书籍删除与资源清理
- 多站点小说 / 漫画目录与章节解析

## 友情链接
[LINUX DO](https://linux.do/)

## 预览

- Web 端书架管理
- 书籍详情与章节列表
- 阅读器与主题切换
- AI 翻译配置与任务日志


## 功能特性

- 多来源导入：支持网页小说 / 漫画链接导入，也支持本地 `TXT / TEXT` 文本导入
- 本地文库：章节、封面、插图、翻译结果统一写入本地 `data/` 目录
- AI 翻译：兼容 `OpenAI / New API / Anthropic / Grok2API / Custom` 配置
- 漫画翻译：后端内置调用 OpenAI 兼容图片编辑接口，直接输出翻译后图片与逐页译文。
- 任务队列：支持下载、翻译、失败重试、日志查看
- 漫画支持：支持 18comic / Bika 章节抓取、逐页下载、图片阅读、逐页译文与翻译后图片资源（仅为测试阶段 目前效果不可投入生产使用）
- 阅读体验：支持应用主题、阅读主题、字体大小、自定义正文颜色与背景色、章节选择、继续阅读、切章回顶
- 封面管理：支持抓取封面与手动上传自定义封面
- 数据持久化：重启服务后书架、设置、阅读进度保留；开发环境默认保存在 `python-backend/data/`

## 已适配站点

以下为青卷内置抓取站点适配，用于书架页按作品链接导入内容；它们不等同于 Legado / 阅读 App 可导入的自定义书源规则。书源管理页仅显示从 Legado / 阅读 JSON 导入的规则。

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

- 前端：`Vue 3`、`TypeScript`、`Vite`、`Fluent Web Components`
- 后端：`Python`、`FastAPI`
- 数据存储：`SQLite`
- 构建：`vue-tsc`、`Vite build`

## 项目结构

```text
.
├─ src/                    # Vue 前端
│  ├─ entry/main.ts         # 前端入口与 Fluent 组件注册
│  ├─ services/             # HTTP API 与后端连接
│  └─ ui/                   # 应用主界面与样式
├─ python-backend/         # FastAPI 后端、抓取器、SQLite 数据层
│  ├─ app/                  # 后端应用代码
│  └─ data/                 # 开发环境默认数据目录
└─ README.md
```

## 环境要求

- Node.js 22+
- npm 10+
- Python 3.13+

## 安装依赖

```bash
npm install
python -m pip install -r python-backend/requirements.txt
```
说明：
- 当前漫画翻译链路不再依赖本地 `LaMa / torch / numpy` 擦字组件
- 漫画页翻译已改为后端内置流程，不再调用外部命令模板

## 漫画译图

- 不再开放“漫画 AI 命令 / 工作目录 / 超时”设置项
- 漫画译图直接复用当前默认翻译提供商的 `baseUrl`、`apiKey` 和 `model`
- 当前仅支持 OpenAI 兼容图片编辑接口：`openai`、`newapi`、`grok2api`、`custom`
- 漫画译图会严格使用你当前设置的模型，不做自动模型回退
- 软件中选择的“语言”会作为翻译目标语言使用；例如选择 `中文` 时，漫画页与章节文本都会翻译为中文，原始语言由模型自动识别
- 若历史章节曾生成错误目标语言的译图或译文，重新执行一次翻译即可按当前所选语言重新生成
- 若默认提供商为 `anthropic`，漫画译图不会执行，并会在任务日志中给出明确提示

## 本地开发

默认同时启动 FastAPI 后端和 Vite 前端：

```bash
npm run test
```

也可以通过参数只启动其中一端：

```bash
npm run test -- frontend
npm run test -- backend
```

前端访问地址：`http://127.0.0.1:1420`

后端默认地址：`http://127.0.0.1:19453`

`frontend` 只会启动前端；如果没有后端服务，书架、设置、任务等功能无法连接。`backend` 只会启动 FastAPI 服务，适合单独调试接口。

如需让前端连接其他后端地址，可在启动前设置。

macOS / Linux / Git Bash 示例：

```bash
export VITE_QINGJUAN_BACKEND_URL=http://127.0.0.1:19453
npm run test -- frontend
```

Windows PowerShell 示例：

```powershell
$env:VITE_QINGJUAN_BACKEND_URL = "http://127.0.0.1:19453"
npm run test -- frontend
```

## 生产构建

```bash
npm run build
```

构建完成后，前端产物位于 `dist/`。

如需本地预览构建产物：

```bash
npm run preview
```

生产环境可以单独部署 `dist/` 静态前端并启动 FastAPI 后端；也可以直接使用 `npm run build:desktop` 生成的桌面端程序，由 FastAPI 后端托管前端静态资源。

## 桌面端与移动端打包

一次性生成桌面端和移动端产物：

```bash
npm run build:release
```

也可以只生成其中一端：

```bash
npm run build:desktop
npm run build:mobile
```

打包产物：

- 桌面端：`release/desktop/`
- 移动端 Web / PWA：`release/mobile/`

桌面端说明：

- `release/desktop/qingjuan-desktop.exe` 是集成前端静态资源的 FastAPI 后端程序
- 双击 `release/desktop/启动青卷.bat` 会启动服务并打开 `http://127.0.0.1:19453`
- 如需让手机访问电脑上的服务，双击 `release/desktop/启动青卷-局域网.bat`，然后在手机浏览器打开 `http://电脑局域网IP:19453`

移动端说明：

- `release/mobile/` 是可部署到静态服务器的移动 Web / PWA 产物，不包含 Python 后端
- 手机端需要连接一台已启动的青卷后端；默认会连接当前访问主机的 `19453` 端口
- 手机浏览器打开后，可通过浏览器菜单添加到主屏幕作为 PWA 使用
- 当前没有引入 Android / iOS 原生壳工程，因此不会生成 APK / IPA

## 常用命令

```bash
npm run test
npm run test -- frontend
npm run test -- backend
npm run build
npm run build:release
npm run build:desktop
npm run build:mobile
python -m py_compile python-backend/app/main.py python-backend/app/db.py python-backend/app/models.py python-backend/app/scraper.py
```

## 数据存储

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

如需覆盖数据目录，可设置环境变量：

```bash
export QINGJUAN_DATA_DIR=/path/to/qingjuan-data
npm run test -- backend
```

## 后端说明

- 前端通过 HTTP 调用本地或远程 FastAPI 服务，默认地址为 `http://127.0.0.1:19453`
- 后端服务负责抓取、翻译、任务队列、导出和本地数据持久化。
- 当前抓取器已支持 Linovelib、Kakuyomu、Syosetu、Novel18、Pixiv、Hameln、Alphapolis、18Comic、Bika Web App 等站点
- Novelup 当前仍受 CloudFront 限制，后续可继续尝试 Cookie 复用 / 代理 / 浏览器登录态方案

## 当前运行架构

- 前端是普通浏览器应用，由 Vite 开发服务器或 `dist/` 静态产物提供
- 后端是独立 FastAPI 服务，默认监听 `127.0.0.1:19453`，生产包中也可直接托管前端静态资源
- 前端启动时会等待后端 `/health` 接口可用，再初始化书架与设置
- 桌面端打包基于 PyInstaller，将 FastAPI 后端与前端静态资源合并为本地服务程序
- 移动端打包为 Web / PWA 静态产物，仍需要连接可访问的青卷后端

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

- Vue
- Fluent UI Web Components
- FastAPI
- 开源社区提供的各类基础工具与依赖
