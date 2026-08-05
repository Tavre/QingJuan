<!-- markdownlint-disable MD033 MD041 -->
<p align="center">
  <img alt="青卷 LOGO" src="./assets/qj_icon2.png" width="160" height="160" />
</p>

<h1 align="center">青卷 QingJuan</h1>

<p align="center">
  面向 Windows 的小说与漫画导入、下载、翻译和阅读工具
</p>

青卷是一个仅适配 Windows 电脑端的开源应用。客户端使用 Flutter 与
[`fluent_ui`](https://pub.dev/packages/fluent_ui)，遵循
[Microsoft Fluent UI](https://github.com/microsoft/fluentui) 和 Windows 11 的简约设计语言；
本地服务使用 Python、FastAPI 与 SQLite。桌面应用会自动探测并启动本地后端，退出时关闭由自己创建的后端进程。
![青卷应用截图](./assets/应用截图.png)
> 当前处于持续开发阶段。漫画译图、部分站点适配与第三方书源可能受目标站点变化影响，请勿将实验功能用于不可恢复的重要数据。

## 功能

- 从受支持的小说或漫画网址预览并导入作品
- 链接解析与导入支持后台运行、弹窗收起恢复和实时进度日志
- 导入 Legado / 阅读 App JSON 书源，搜索并管理启用状态
- 导入本地 `TXT` / `TEXT`、Word `DOCX`、`EPUB` 小说并自动拆章，也可将 `PDF` 导入为漫画
- 下载章节、创建翻译任务、查看进度与失败重试
- 单章、所选章节或全部章节可导出为 `TXT` / `TEXT` / `DOCX` / `EPUB`；漫画可导出为 `PDF` 或按章节、`001`、`002`……编号的图片文件夹
- 阅读原文或译文，支持章节跳转、字号调整和阅读进度保存
- 在小说详情页使用 Windows TTS 听书，支持连续播章、暂停、语速和音量调节
- 配置单一 OpenAI 兼容翻译模型，启用状态会被下载与翻译任务严格遵守
- 默认使用本地 RapidOCR 与 Windows OCR 检测漫画文字，纯文本模型也可翻译；支持图片输入的模型可作为可选增强
- 亮色、深色和跟随系统主题

内置站点适配包括 Linovelib / 哔哩轻小说、Kakuyomu、Syosetu、Novel18、Pixiv 小说与插画漫画、
Pixiv Comic、Hameln、Alphapolis、18Comic、Bika，以及 Webtoon、漫画柜、漫画呗、拷贝漫画、动漫之家等常见网页阅读器。
网页阅读器使用通用规则尽力解析，站点结构、登录要求或访问策略变化都可能导致暂时不可用；请仅下载你有权访问和保存的内容。

## 开发文档

环境配置、源码调试、项目架构、UI 规范、测试门禁和 Windows 发布流程统一维护在
[青卷开发规范](./docs/development/README.md) 中，README 不再重复开发细节。

## 数据与隐私

- 开发模式默认数据目录：`python-backend/data/`
- 打包后端默认数据目录：`backend/data/`
- 可在启动前设置 `QINGJUAN_DATA_DIR` 覆盖位置
- API 密钥保存在本地 SQLite 设置中，不应提交、截图或分享
- 不要提交数据库、下载内容、账号、Cookie、密钥、日志或受版权保护的正文
- 仅导入可信书源；网络内容和第三方脚本均应视为不可信输入

## 参与贡献

欢迎通过 [Issue](https://github.com/Tavre/QingJuan/issues) 报告问题或提出建议，
也欢迎阅读[开发规范](./docs/development/README.md)后提交 Pull Request。
提交前请搜索重复问题，并移除密钥、数据库、账号和个人内容。

## 交流与支持

- GitHub 仓库：[Tavre/QingJuan](https://github.com/Tavre/QingJuan)
- QQ 讨论群：`1074882763`

应用内可从左侧菜单进入“关于”页面查看并复制以上信息。

安全问题不要在公开 Issue 中披露利用细节或用户数据。请使用 GitHub 仓库的
**Security → Report a vulnerability** 私密报告入口，并附受影响版本、最小复现、影响范围和建议方案。

## 感谢贡献者

感谢每一位参与代码、文档、测试、问题反馈和评审的贡献者。

<p>
  <a href="https://github.com/Tavre" title="@Tavre">
    <img src="https://avatars.githubusercontent.com/u/137062985?s=96&amp;v=4" width="72" height="72" alt="@Tavre 的 GitHub 头像" />
  </a>
</p>

<sub><b><a href="https://github.com/Tavre">@Tavre</a></b> · 项目发起者与维护者</sub>

查看 GitHub 统计的[全部贡献者](https://github.com/Tavre/QingJuan/graphs/contributors)。

## 许可证

本项目由 `Tavre` 发起，使用 [GNU General Public License v3.0](./LICENSE) 发布。
使用、修改和分发时须遵守 GPL v3 条款。

## 致谢

- Flutter 与 Dart
- `fluent_ui`
- FastAPI
- [LINUX DO](https://linux.do/)
- [RapidOCR](https://github.com/RapidAI/RapidOCR)
- 为抓取、解析、图片处理和测试提供基础能力的开源项目
