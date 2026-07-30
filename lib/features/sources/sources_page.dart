import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/source.dart';
import '../../core/state/load_state.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';

class SourcesPage extends StatelessWidget {
  const SourcesPage({super.key});

  Future<void> _showImportDialog(BuildContext context,
      {required bool fromUrl}) async {
    final controller = TextEditingController();
    String? error;
    bool loading = false;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setState) => ContentDialog(
          title: Text(fromUrl ? '从网址导入书源' : '粘贴书源配置'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              TextBox(
                controller: controller,
                maxLines: fromUrl ? 1 : 10,
                placeholder: fromUrl ? 'https://...' : '粘贴 JSON 或 Legado 书源文本',
                enabled: !loading,
              ),
              if (error != null) ...<Widget>[
                const SizedBox(height: 12),
                InfoBar(
                  title: const Text('导入失败'),
                  content: Text(error!),
                  severity: InfoBarSeverity.error,
                ),
              ],
            ],
          ),
          actions: <Widget>[
            Button(
              onPressed: loading ? null : () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: loading
                  ? null
                  : () async {
                      setState(() {
                        loading = true;
                        error = null;
                      });
                      try {
                        final sources = AppScope.of(context).sources;
                        if (fromUrl) {
                          await sources.importUrl(controller.text);
                        } else {
                          await sources.importText(controller.text);
                        }
                        if (dialogContext.mounted) Navigator.pop(dialogContext);
                      } catch (exception) {
                        setState(() {
                          loading = false;
                          error = '$exception';
                        });
                      }
                    },
              child: const Text('导入'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context).sources;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => PageFrame(
        title: '书源',
        subtitle: '维护内置、手动和 Legado 兼容书源。',
        scrollable: false,
        command: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Button(
              onPressed: () => _showImportDialog(context, fromUrl: false),
              child: const Text('粘贴配置'),
            ),
            const SizedBox(width: 8),
            FilledButton(
              onPressed: () => _showImportDialog(context, fromUrl: true),
              child: const Text('导入网址'),
            ),
          ],
        ),
        child: Expanded(
          child: switch (controller.state) {
            LoadState.idle ||
            LoadState.loading =>
              const LoadingView(label: '正在加载书源'),
            LoadState.error => ErrorView(
                message: controller.error ?? '未知错误',
                onRetry: controller.load,
              ),
            LoadState.empty => const EmptyView(
                icon: FluentIcons.database,
                title: '暂无书源',
                message: '导入书源配置后即可使用全网搜索。',
              ),
            _ => ListView.builder(
                cacheExtent: 360,
                itemCount: controller.sources.length,
                itemBuilder: (context, index) =>
                    _SourceTile(source: controller.sources[index]),
              ),
          },
        ),
      ),
    );
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.source});

  final BookSource source;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.cardColor,
        border: Border.all(color: theme.resources.cardStrokeColorDefault),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: <Widget>[
          Icon(
            source.enabled
                ? FluentIcons.radio_btn_on
                : FluentIcons.radio_btn_off,
            color: source.enabled ? theme.accentColor : null,
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  source.name,
                  style: theme.typography.bodyLarge
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 4),
                Text(
                  source.description.isEmpty
                      ? source.baseUrl
                      : source.description,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.typography.caption,
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Text(
            source.statusMessage.isEmpty ? source.status : source.statusMessage,
          ),
        ],
      ),
    );
  }
}
