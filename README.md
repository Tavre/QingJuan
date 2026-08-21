<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="青卷 LOGO" src="./assets/logo.png" width="160" height="160" />
</p>

<h1 align="center">青卷 QingJuan</h1>

<p align="center">
  Windows 与 Android 小说、漫画下载、翻译和阅读客户端
</p>

青卷使用 Flutter 构建 Windows 与 Android 客户端，并为 FastAPI 后端提供 React 管理界面。Windows 可使用安装包内的
本机后端，也可与 Android 一起连接 Linux 远程后端；书库、下载、翻译和任务由当前选中的后端管理。

Windows 与 Android 共用业务能力，但采用两套独立界面：Windows 保持 v1.3.4 的 Fluent/Windows 仿原生桌面风格，
Android 使用触控优先的移动端风格；窗口宽度变化不会让两种平台界面互相切换。

> 项目仍在持续开发。网站规则变化时，部分下载功能可能暂时失效。请只保存你有权访问的内容。

## 功能

- 从常见小说、漫画网站导入作品
- 导入本地 `TXT`、`DOCX`、`EPUB` 和 `PDF`
- 下载章节并查看任务进度
- 使用 OpenAI 兼容接口翻译小说和漫画
- 导出 `TXT`、`DOCX`、`EPUB`、`PDF` 或图片压缩包
- 阅读原文和译文，保存阅读进度
- 使用设备系统 TTS 听书
- 支持亮色、深色和跟随系统主题

目前支持番茄小说、起点中文网、夸克小说、刺猬猫、SF 轻小说、少年梦、哔哩轻小说、Kakuyomu、Syosetu、Novel18、Pixiv、Yanmaga、Webtoon、拷贝漫画、COMICORES、动漫之家、
18Comic、Bika、E-Hentai 等站点，也支持导入 Legado / 阅读 App JSON 书源。搜索页可选择“书源”“夸克”“番茄”或“起点”；内置解析器会保留目录中的全部章节，并在上游返回可解析内容时默认保存，不因 VIP、订阅或付费标记提前跳过。未实现章节解析或上游未返回可用内容时会明确提示。Windows 本机模式在客户端“插件配置”中启停内置解析器；
Linux 远程模式在服务器管理界面的“插件管理”中统一维护，客户端会自动隐藏该入口。外部规则仍只在“书源管理”中管理。

番茄与起点插件支持扫码登录；番茄扫码受限时也可粘贴已登录浏览器请求的 Cookie。连接成功后可一键添加当前账号书架，
文字作品按“边看边下”方式加入，已有作品会自动跳过。登录凭据只保存在当前后端进程内存中，后端重启后需要重新登录。

## 支持平台

| 平台 | 支持范围 | 安装包 |
| --- | --- | --- |
| Windows | Windows 10 / 11 x64 | `QingJuan-v<版本>-windows-x64.zip` |
| Android | Android 8.0（API 26）或更高版本 | `QingJuan-v<版本>-android.apk` |
| Linux | x86_64、systemd、Python 3.11+ 服务端 | 原生部署脚本 |

Windows ZIP 包含本机后端，可在“本机后端 / Linux 远程后端”之间选择；Android 必须连接 Linux 服务端。

## 使用方法

### 1. 安装客户端

从 [Releases](https://github.com/Tavre/QingJuan/releases/latest) 下载对应平台的安装包：

- Windows：完整解压 Windows x64 ZIP，运行 `qingjuan.exe`。需要单机使用时在设置中选择“本机后端”。
- Android：下载 APK，在手机或平板确认来源后安装。

### 2. 可选：部署 Linux 后端

Android 或 Windows 远程模式需要 Linux 服务端；只使用 Windows 本机模式时可以跳过本节。

先在 Linux 服务器执行：

```bash
sudo mkdir -p /opt/qingjuan
sudo git clone https://github.com/Tavre/QingJuan.git /opt/qingjuan/app
cd /opt/qingjuan/app
sudo bash deploy/linux/install.sh
sudo qingjuan-info
```

安装脚本会自动识别服务器的 Tailscale、WireGuard 或局域网 IP。安装完成后会显示管理界面地址、首次登录的
随机管理密码、FastAPI 地址和连接 Token。管理密码只显示一次；公网服务器请使用
`--url https://你的域名` 指定已配置反向代理的 HTTPS 地址。

浏览器打开终端显示的管理界面地址，即可查看服务概览、连接设备、系统诊断、后端 API 密钥、任务和服务器运行日志，
以及书库、书源、插件和模型设置。系统诊断可下载不含凭据和服务器路径的脱敏报告；API 密钥默认遮挡，只在管理员主动点击后
短暂显示。Linux 后端的翻译模型在管理界面配置并支持自检；Windows / Android 远程连接后会自动检查服务端模型，
不在客户端保存模型密钥或直连模型供应商。忘记管理密码时运行：

```bash
sudo qingjuan-password --generate
```

### 3. 选择后端

打开 **设置 → 后端连接**：

- Windows 本机模式：选择“本机后端”并保存，应用会按需启动安装包内的后端，无需 Token；本机后端不启动浏览器管理界面，
  翻译模型、API 密钥、系统提示词和外部 OCR 直接在客户端“设置 → 翻译服务”中配置。
- Windows 远程模式或 Android：填写服务器显示的“FastAPI 地址”和“连接 Token”，再保存连接。

远程 FastAPI 地址不要添加 `/api/v1`。公网访问必须使用 HTTPS，不要直接暴露公网 HTTP 端口；远程连接失败时不会
自动回退本机。切换模式会切换到另一套后端数据，但会保留安全存储中的远程连接信息。

常用服务器命令：

```bash
# 查看状态
sudo systemctl status qingjuan-backend --no-pager

# 查看日志
sudo journalctl -u qingjuan-backend -f

# 更新后端
sudo bash /opt/qingjuan/app/deploy/linux/update.sh

# 修改管理界面密码
sudo qingjuan-password

# 卸载并保留书库数据
sudo qingjuan-uninstall
```

需要连同书库一起永久删除时，直接运行
`sudo qingjuan-uninstall --purge-data`，不要先执行普通卸载。

## 数据与安全

- Windows 本机数据保存在完整解压目录的 `backend/data/`
- Linux 数据保存在 `/var/lib/qingjuan`
- Android 以及 Windows 远程模式只在设备上保存界面偏好和平台安全存储保护的连接 Token
- Windows 本机数据与 Linux 数据不会自动同步；更新或迁移前请备份当前使用的数据目录
- 不要公开连接 Token、翻译 API 密钥、Cookie、数据库和下载内容
- 不要公开管理密码；终端改密后，原有管理界面会话会自动退出
- 连接建议使用局域网、Tailscale / WireGuard；公网访问必须使用 HTTPS

## 开发、构建与 CI

开发环境、架构、测试、构建、CI 与发布要求统一见[开发文档](./docs/development/README.md)。
欢迎提交 [Issue](https://github.com/Tavre/QingJuan/issues) 或 Pull Request；提交前请遵循开发文档并移除密钥、账号和个人数据。

## 交流

- GitHub：[Tavre/QingJuan](https://github.com/Tavre/QingJuan)
- QQ 群：`1074882763`
- 安全问题请使用 GitHub 的 **Security → Report a vulnerability** 私密报告

## 许可与致谢

本项目使用 [GNU GPL v3](./LICENSE) 许可证。

感谢[所有贡献者](https://github.com/Tavre/QingJuan/graphs/contributors)，以及 Flutter、FastAPI、RapidOCR、
`fluent_ui`、[fanqie-assistant](https://github.com/naiyQAQ/fanqie-assistant) 等开源项目。
