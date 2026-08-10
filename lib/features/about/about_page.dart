import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';

import '../../shared/app_surface.dart';
import '../../shared/page_frame.dart';

class AboutPage extends StatefulWidget {
  const AboutPage({super.key});

  @override
  State<AboutPage> createState() => _AboutPageState();
}

class _AboutPageState extends State<AboutPage> {
  static const _repositoryUrl = 'https://github.com/Tavre/QingJuan';
  static const _discussionGroup = '1074882763';

  String? _copiedLabel;

  Future<void> _copy(String label, String value) async {
    await Clipboard.setData(ClipboardData(text: value));
    if (mounted) setState(() => _copiedLabel = label);
  }

  @override
  Widget build(BuildContext context) {
    return PageFrame(
      title: '关于青卷',
      subtitle: '开源的 Windows 小说与漫画阅读、下载和翻译工具。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          if (_copiedLabel != null) ...<Widget>[
            InfoBar(
              title: Text('${_copiedLabel!}已复制'),
              severity: InfoBarSeverity.success,
              onClose: () => setState(() => _copiedLabel = null),
            ),
            const SizedBox(height: 24),
          ],
          const SectionTitle('项目'),
          AppSurface(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: <Widget>[
                _InformationRow(
                  icon: FluentIcons.open_source,
                  label: 'GitHub 仓库',
                  value: _repositoryUrl,
                  copyTooltip: '复制 GitHub 地址',
                  onCopy: () => _copy('GitHub 地址', _repositoryUrl),
                ),
                const Divider(),
                _InformationRow(
                  icon: FluentIcons.group,
                  label: '讨论群',
                  value: _discussionGroup,
                  description: 'QQ 讨论群',
                  copyTooltip: '复制讨论群号',
                  onCopy: () => _copy('讨论群号', _discussionGroup),
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),
          const SectionTitle('开源许可'),
          const AppSurface(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              children: <Widget>[
                _InformationRow(
                  icon: FluentIcons.pc1,
                  label: '支持平台',
                  value: 'Windows 10 / Windows 11',
                  description: '青卷目前仅提供 Windows 桌面客户端。',
                ),
                Divider(),
                _InformationRow(
                  icon: FluentIcons.certificate,
                  label: '许可证',
                  value: 'GNU General Public License v3.0',
                  description: '使用、修改和分发时须遵守 GPL v3 条款。',
                ),
                Divider(),
                _InformationRow(
                  icon: FluentIcons.favorite_star,
                  label: '维护者',
                  value: 'Tavre 与青卷开源社区',
                  description: '感谢每一位贡献代码、文档、测试和反馈的参与者。',
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _InformationRow extends StatelessWidget {
  const _InformationRow({
    required this.icon,
    required this.label,
    required this.value,
    this.description,
    this.copyTooltip,
    this.onCopy,
  });

  final IconData icon;
  final String label;
  final String value;
  final String? description;
  final String? copyTooltip;
  final VoidCallback? onCopy;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          AccentIcon(icon),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(label, style: theme.typography.bodyLarge),
                const SizedBox(height: 6),
                SelectableText(value),
                if (description != null) ...<Widget>[
                  const SizedBox(height: 4),
                  Text(description!, style: theme.typography.caption),
                ],
              ],
            ),
          ),
          if (onCopy != null) ...<Widget>[
            const SizedBox(width: 12),
            Tooltip(
              message: copyTooltip!,
              child: IconButton(
                key: ValueKey<String>('copy-$value'),
                icon: const Icon(FluentIcons.copy, size: 16),
                onPressed: onCopy,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
