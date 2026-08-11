import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/source.dart';
import '../../core/state/load_state.dart';
import '../../shared/app_surface.dart';
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
        compactHeader: ReadingPageHeader(
          title: '书源',
          subtitle: controller.sources.isEmpty
              ? '连接内容来源'
              : '${controller.sources.where((source) => source.enabled).length} 个书源已启用',
          actions: <Widget>[
            Tooltip(
              message: '粘贴书源配置',
              child: IconButton(
                icon: const Icon(
                  FluentIcons.clipboard_list,
                  semanticLabel: '粘贴书源配置',
                ),
                onPressed: () => _showImportDialog(context, fromUrl: false),
              ),
            ),
            const SizedBox(width: 7),
            FilledButton(
              onPressed: () => _showImportDialog(context, fromUrl: true),
              child: const Text('导入'),
            ),
          ],
        ),
        command: Wrap(
          spacing: 8,
          runSpacing: 8,
          children: <Widget>[
            Button(
              onPressed: () => _showImportDialog(context, fromUrl: false),
              child: const Text('粘贴配置'),
            ),
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
            LoadState.empty => Column(
                children: <Widget>[
                  FeatureHero(
                    icon: FluentIcons.database,
                    title: '建立你的内容来源',
                    message: '支持直接粘贴 JSON、Legado 书源文本，或从可信网址导入配置。',
                    child: Row(
                      children: <Widget>[
                        Expanded(
                          child: Button(
                            onPressed: () => _showImportDialog(
                              context,
                              fromUrl: false,
                            ),
                            child: const Text('粘贴配置'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: FilledButton(
                            onPressed: () => _showImportDialog(
                              context,
                              fromUrl: true,
                            ),
                            child: const Text('导入网址'),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Expanded(
                    child: EmptyView(
                      icon: FluentIcons.database,
                      title: '暂未配置书源',
                      message: '导入并启用至少一个兼容书源后，即可在搜索页发现作品。',
                    ),
                  ),
                ],
              ),
            _ => Column(
                children: <Widget>[
                  _SourcesOverview(sources: controller.sources),
                  const SizedBox(height: 18),
                  Expanded(
                    child: ListView.builder(
                      cacheExtent: 360,
                      itemCount: controller.sources.length,
                      itemBuilder: (context, index) =>
                          _SourceTile(source: controller.sources[index]),
                    ),
                  ),
                ],
              ),
          },
        ),
      ),
    );
  }
}

class _SourcesOverview extends StatelessWidget {
  const _SourcesOverview({required this.sources});

  final List<BookSource> sources;

  @override
  Widget build(BuildContext context) {
    final enabled = sources.where((source) => source.enabled).length;
    final supported = sources.where((source) => source.supported).length;
    return FeatureHero(
      icon: FluentIcons.database,
      title: '书源运行状态',
      message: enabled == 0 ? '当前没有启用的书源。' : '$enabled 个书源正在为搜索提供内容。',
      child: Row(
        children: <Widget>[
          Expanded(child: AppMetric(label: '全部', value: '${sources.length}')),
          Expanded(
              child:
                  AppMetric(label: '已启用', value: '$enabled', accented: true)),
          Expanded(child: AppMetric(label: '兼容搜索', value: '$supported')),
        ],
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
    return AppSurface(
      margin: const EdgeInsets.only(bottom: 10),
      tone: AppSurfaceTone.elevated,
      child: Row(
        children: <Widget>[
          AccentIcon(
            FluentIcons.database,
            enabled: source.enabled,
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
                if (source.tags.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: source.tags
                        .take(3)
                        .map((tag) => StatusPill(tag))
                        .toList(growable: false),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: StatusPill(
              source.statusMessage.isEmpty
                  ? source.status
                  : source.statusMessage,
              accented: source.enabled,
            ),
          ),
        ],
      ),
    );
  }
}
