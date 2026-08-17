import 'package:fluent_ui/fluent_ui.dart';

import '../../../core/backend/backend_connection_manager.dart';
import '../../../core/models/settings.dart';
import 'settings_section_card.dart';

class TranslationModelCard extends StatelessWidget {
  const TranslationModelCard({
    required this.backend,
    required this.checking,
    required this.onCheck,
    super.key,
  });

  final BackendConnectionManager backend;
  final bool checking;
  final VoidCallback onCheck;

  @override
  Widget build(BuildContext context) {
    return SettingsSectionCard(
      icon: FluentIcons.locale_language,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const InfoBar(
            title: Text('由后端管理界面统一配置'),
            content: Text(
              '客户端只创建服务端翻译任务，不保存模型密钥或直连模型供应商；每次连接都会执行模型自检。',
            ),
            severity: InfoBarSeverity.info,
          ),
          const SizedBox(height: 14),
          _translationModelStatusBar(),
          const SizedBox(height: 12),
          Button(
            onPressed: backend.status == BackendStatus.ready && !checking
                ? onCheck
                : null,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (checking) ...<Widget>[
                  const SizedBox(
                    width: 14,
                    height: 14,
                    child: ProgressRing(strokeWidth: 2),
                  ),
                  const SizedBox(width: 8),
                ] else ...<Widget>[
                  const Icon(FluentIcons.refresh, size: 14),
                  const SizedBox(width: 8),
                ],
                Text(checking ? '正在检测' : '重新检测模型'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _translationModelStatusBar() {
    final check = backend.translationModelCheck;
    if (check == null) {
      return const InfoBar(
        title: Text('等待服务端模型自检'),
        content: Text('连接后端后会自动检查管理界面保存的翻译模型。'),
        severity: InfoBarSeverity.info,
      );
    }
    final title = switch (check.status) {
      TranslationModelCheckStatus.ready => '服务端翻译模型可用',
      TranslationModelCheckStatus.disabled => '服务端翻译模型未启用',
      TranslationModelCheckStatus.unconfigured => '服务端翻译模型未配置完整',
      TranslationModelCheckStatus.failed => '服务端翻译模型自检失败',
    };
    final details = <String>[
      if (check.model != null && check.model!.isNotEmpty) check.model!,
      if (check.latencyMs != null) '${check.latencyMs} ms',
      if (check.available) check.supportsVision ? '支持视觉' : '仅文本',
      if (check.cached) '近期检查结果',
    ];
    return InfoBar(
      title: Text(title),
      content: Text(
        check.available && details.isNotEmpty
            ? details.join(' · ')
            : check.message,
      ),
      severity: switch (check.status) {
        TranslationModelCheckStatus.ready => InfoBarSeverity.success,
        TranslationModelCheckStatus.failed => InfoBarSeverity.error,
        _ => InfoBarSeverity.warning,
      },
    );
  }
}
