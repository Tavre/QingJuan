import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_miuix/miuix.dart' as miuix;

import '../../app/app_scope.dart';
import '../../core/models/source.dart';
import '../../core/state/load_state.dart';
import '../../shared/app_surface.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/mobile_miuix.dart';
import '../../shared/mobile_sheet.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../../shared/smooth_scroll.dart';
import 'sources_controller.dart';
import 'widgets/plugin_settings_widgets.dart';

class SourcesPage extends StatelessWidget {
  const SourcesPage({super.key});

  Future<void> _setSourceEnabled(
    BuildContext context,
    BookSource source,
    bool enabled,
  ) async {
    try {
      await AppScope.of(context).sources.setSourceEnabled(source, enabled);
    } catch (error) {
      if (!context.mounted) return;
      displayInfoBar(
        context,
        builder: (_, __) => InfoBar(
          title: const Text('书源状态保存失败'),
          content: Text('$error'),
          severity: InfoBarSeverity.error,
        ),
      );
    }
  }

  Future<void> _showImportDialog(
    BuildContext context, {
    required bool fromUrl,
  }) async {
    final controller = TextEditingController();
    String? error;
    var loading = false;
    Widget dialogBuilder(BuildContext dialogContext) => StatefulBuilder(
          builder: (sheetContext, setState) {
            final mobile = usesMobileUi(sheetContext);
            final content = Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (mobile)
                  miuix.MiuixTextField(
                    controller: controller,
                    label: fromUrl ? 'https://...' : '粘贴 JSON 或 Legado 书源文本',
                    useLabelAsPlaceholder: true,
                    singleLine: fromUrl,
                    maxLines: fromUrl ? 1 : 10,
                    minLines: fromUrl ? 1 : 5,
                    enabled: !loading,
                  )
                else
                  TextBox(
                    controller: controller,
                    magnifierConfiguration: textInputMagnifierConfiguration(
                      sheetContext,
                    ),
                    maxLines: fromUrl ? 1 : 10,
                    placeholder:
                        fromUrl ? 'https://...' : '粘贴 JSON 或 Legado 书源文本',
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
            );
            void cancel() => Navigator.pop(dialogContext);
            final importAction = loading
                ? null
                : () async {
                    setState(() {
                      loading = true;
                      error = null;
                    });
                    try {
                      final sources = AppScope.of(sheetContext).sources;
                      if (fromUrl) {
                        await sources.importUrl(controller.text);
                      } else {
                        await sources.importText(controller.text);
                      }
                      if (dialogContext.mounted) {
                        Navigator.pop(dialogContext);
                      }
                    } catch (exception) {
                      setState(() {
                        loading = false;
                        error = '$exception';
                      });
                    }
                  };
            final actions = mobile
                ? <Widget>[
                    MobileMiuixButton(
                      onPressed: loading ? null : cancel,
                      child: const Text('取消'),
                    ),
                    MobileMiuixButton(
                      primary: true,
                      onPressed: importAction,
                      child: Text(loading ? '导入中' : '导入'),
                    ),
                  ]
                : <Widget>[
                    Button(
                      onPressed: loading ? null : cancel,
                      child: const Text('取消'),
                    ),
                    FilledButton(
                        onPressed: importAction, child: const Text('导入')),
                  ];
            if (mobile) {
              return MobileSheet(
                title: fromUrl ? '从网址导入' : '粘贴书源',
                subtitle: '支持 Legado 兼容书源',
                onClose: loading ? null : () => Navigator.pop(dialogContext),
                actions: actions,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 20),
                  child: content,
                ),
              );
            }
            return ContentDialog(
              title: Text(fromUrl ? '从网址导入书源' : '粘贴书源配置'),
              content: content,
              actions: actions,
            );
          },
        );
    if (usesMobileUi(context)) {
      await showMobileSheet<void>(context: context, builder: dialogBuilder);
    } else {
      await showDialog<void>(context: context, builder: dialogBuilder);
    }
    controller.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final controller = scope.sources;
    final canManage = scope.auth.canManageServiceConfiguration;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        if (!usesMobileUi(context)) {
          return _buildDesktopPage(context, controller, canManage: canManage);
        }
        return PageFrame(
          title: '书源',
          subtitle: '维护内置、手动和 Legado 兼容书源。',
          scrollable: false,
          compactHeader: ReadingPageHeader(
            title: '书源',
            subtitle: controller.sources.isEmpty
                ? '连接内容来源'
                : '${controller.sources.where((source) => source.enabled).length} 个书源已启用',
            actions: canManage
                ? <Widget>[
                    MobileMiuixIconButton(
                      icon: FluentIcons.clipboard_list,
                      label: '粘贴书源配置',
                      onPressed: () =>
                          _showImportDialog(context, fromUrl: false),
                    ),
                    const SizedBox(width: 8),
                    MobileMiuixButton(
                      primary: true,
                      onPressed: () =>
                          _showImportDialog(context, fromUrl: true),
                      child: const Text('导入'),
                    ),
                  ]
                : const <Widget>[],
          ),
          command: canManage
              ? Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: <Widget>[
                    Button(
                      onPressed: () =>
                          _showImportDialog(context, fromUrl: false),
                      child: const Text('粘贴配置'),
                    ),
                    FilledButton(
                      onPressed: () =>
                          _showImportDialog(context, fromUrl: true),
                      child: const Text('导入网址'),
                    ),
                  ],
                )
              : null,
          child: Expanded(
            child: switch (controller.state) {
              LoadState.idle ||
              LoadState.loading =>
                const LoadingView(label: '正在加载书源'),
              LoadState.error => ErrorView(
                  message: controller.error ?? '未知错误',
                  onRetry: controller.load,
                ),
              _ when controller.sources.isEmpty && !canManage =>
                const EmptyView(
                  icon: FluentIcons.database,
                  title: '暂无可用书源',
                  message: '书源由管理员统一维护，请联系管理员添加或启用书源。',
                ),
              _ when controller.sources.isEmpty => Column(
                  children: <Widget>[
                    FeatureHero(
                      icon: FluentIcons.database,
                      title: '添加内容来源',
                      message: '支持直接粘贴 JSON、Legado 书源文本，或从可信网址导入配置。',
                      child: Row(
                        children: <Widget>[
                          Expanded(
                            child: MobileMiuixButton(
                              onPressed: () =>
                                  _showImportDialog(context, fromUrl: false),
                              child: const Text('粘贴配置'),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: MobileMiuixButton(
                              primary: true,
                              onPressed: () =>
                                  _showImportDialog(context, fromUrl: true),
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
                        itemCount: controller.sources.length,
                        itemBuilder: (context, index) {
                          final source = controller.sources[index];
                          return SourceRuleTile(
                            source: source,
                            saving: controller.isSourceSaving(source.id),
                            onChanged: canManage
                                ? (enabled) =>
                                    _setSourceEnabled(context, source, enabled)
                                : null,
                          );
                        },
                      ),
                    ),
                  ],
                ),
            },
          ),
        );
      },
    );
  }

  Widget _buildDesktopPage(
    BuildContext context,
    SourcesController controller, {
    required bool canManage,
  }) {
    return PageFrame(
      key: const ValueKey('desktop-sources-page'),
      title: '书源管理',
      subtitle: '维护内置、手动和 Legado 兼容书源。',
      scrollable: false,
      command: canManage
          ? Wrap(
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
            )
          : null,
      child: Expanded(
        child: switch (controller.state) {
          LoadState.idle ||
          LoadState.loading =>
            const LoadingView(label: '正在加载书源'),
          LoadState.error => ErrorView(
              message: controller.error ?? '未知错误',
              onRetry: controller.load,
            ),
          _ when controller.sources.isEmpty => EmptyView(
              icon: FluentIcons.database,
              title: canManage ? '暂无书源' : '暂无可用书源',
              message:
                  canManage ? '导入书源配置后即可使用全网搜索。' : '书源由管理员统一维护，请联系管理员添加或启用书源。',
            ),
          _ => QjScrollControllerBuilder(
              debugLabel: 'desktop-sources',
              builder: (context, scrollController) => ListView.builder(
                controller: scrollController,
                itemCount: controller.sources.length,
                itemBuilder: (context, index) {
                  final source = controller.sources[index];
                  return SourceRuleTile(
                    source: source,
                    saving: controller.isSourceSaving(source.id),
                    onChanged: canManage
                        ? (enabled) =>
                            _setSourceEnabled(context, source, enabled)
                        : null,
                  );
                },
              ),
            ),
        },
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
          Expanded(
            child: AppMetric(label: '全部', value: '${sources.length}'),
          ),
          Expanded(
            child: AppMetric(label: '已启用', value: '$enabled', accented: true),
          ),
          Expanded(
            child: AppMetric(label: '兼容搜索', value: '$supported'),
          ),
        ],
      ),
    );
  }
}
