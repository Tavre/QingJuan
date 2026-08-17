import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/source.dart';
import '../../shared/app_surface.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/motion.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../detail/book_detail_page.dart';
import '../sources/sources_controller.dart';

class SearchPage extends StatefulWidget {
  const SearchPage({super.key});

  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _import(SourceSearchResult result) async {
    try {
      final book =
          await AppScope.of(context).library.import(result.toImportPayload());
      if (mounted) {
        await Navigator.of(context).push<void>(
          qjPageRoute<void>(
            context: context,
            builder: (_) => BookDetailPage(bookId: book.id),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        displayInfoBar(
          context,
          builder: (_, __) => InfoBar(
            title: const Text('导入失败'),
            content: Text('$error'),
            severity: InfoBarSeverity.error,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final sources = AppScope.of(context).sources;
    return AnimatedBuilder(
      animation: sources,
      builder: (context, _) {
        if (!usesMobileUi(context)) return _buildDesktopPage(sources);
        return PageFrame(
          title: '搜索',
          subtitle: '从已启用书源发现作品，找到后直接加入书架。',
          compactHeader: ReadingPageHeader(
            title: '搜索',
            subtitle:
                '${sources.sources.where((source) => source.enabled).length} 个书源已启用',
            actions: const <Widget>[],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              FeatureHero(
                icon: FluentIcons.search,
                title: '发现下一本想读的书',
                message: '输入书名或作者，青卷会同时查询所有已启用且兼容搜索的书源。',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: TextBox(
                            controller: _controller,
                            placeholder: '输入书名或作者',
                            onSubmitted: sources.search,
                            prefix: const Padding(
                              padding: EdgeInsets.only(left: 10),
                              child: Icon(FluentIcons.search, size: 18),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        FilledButton(
                          onPressed: sources.searching
                              ? null
                              : () => sources.search(_controller.text),
                          child: const Text('搜索'),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: <Widget>[
                        StatusPill(
                          '${sources.sources.where((source) => source.enabled).length} 个书源可用',
                          accented: true,
                          icon: FluentIcons.database,
                        ),
                        const StatusPill(
                          '小说 · 漫画 · 本地书',
                          icon: FluentIcons.book_answers,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              if (sources.searching)
                const LoadingView(label: '正在查询书源')
              else if (sources.error != null)
                ErrorView(
                  message: sources.error!,
                  onRetry: () => sources.search(_controller.text),
                )
              else if (sources.results.isEmpty)
                const AppSurface(
                  tone: AppSurfaceTone.muted,
                  padding: EdgeInsets.symmetric(horizontal: 22, vertical: 24),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      AccentIcon(FluentIcons.lightbulb, size: 46),
                      SizedBox(width: 15),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              '搜索小提示',
                              style: TextStyle(fontWeight: FontWeight.w700),
                            ),
                            SizedBox(height: 6),
                            Text(
                              '使用作品完整名称更容易命中；加入书架前可以核对作者、来源和简介。',
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                )
              else ...<Widget>[
                SectionTitle(
                  '搜索结果',
                  trailing: Text(
                    '${sources.results.length} 本',
                    style: FluentTheme.of(context).typography.caption,
                  ),
                ),
                ...sources.results.map(
                  (result) => _SearchResultTile(
                    result: result,
                    onImport: () => _import(result),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }

  Widget _buildDesktopPage(SourcesController sources) {
    return PageFrame(
      key: const ValueKey('desktop-search-page'),
      title: '全网搜索',
      subtitle: '通过已启用书源查找作品，并直接加入书架。',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: TextBox(
                  controller: _controller,
                  placeholder: '输入书名或作者',
                  onSubmitted: sources.search,
                  prefix: const Padding(
                    padding: EdgeInsets.only(left: 10),
                    child: Icon(FluentIcons.search),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              FilledButton(
                onPressed: sources.searching
                    ? null
                    : () => sources.search(_controller.text),
                child: const Text('搜索'),
              ),
            ],
          ),
          const SizedBox(height: 22),
          if (sources.searching)
            const LoadingView(label: '正在查询书源')
          else if (sources.error != null)
            ErrorView(
              message: sources.error!,
              onRetry: () => sources.search(_controller.text),
            )
          else if (sources.results.isEmpty)
            const EmptyView(
              icon: FluentIcons.search_issue,
              title: '输入关键词开始搜索',
              message: '搜索结果会按书源返回，可在导入前核对作者和简介。',
            )
          else
            ...sources.results.map(
              (result) => _SearchResultTile(
                result: result,
                onImport: () => _import(result),
              ),
            ),
        ],
      ),
    );
  }
}

class _SearchResultTile extends StatelessWidget {
  const _SearchResultTile({required this.result, required this.onImport});

  final SourceSearchResult result;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final compact = usesMobileUi(context);
    if (!compact) {
      return AppSurface(
        margin: const EdgeInsets.only(bottom: 8),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final narrow = constraints.maxWidth < 560;
            final details = Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const AccentIcon(FluentIcons.book_answers),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        result.title,
                        style: theme.typography.bodyLarge
                            ?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: <Widget>[
                          if (result.author.isNotEmpty)
                            StatusPill(result.author),
                          StatusPill(result.sourceName, accented: true),
                          StatusPill(result.kind),
                        ],
                      ),
                      if (result.synopsis.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 9),
                        Text(
                          result.synopsis,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.typography.body?.copyWith(
                            color: theme.resources.textFillColorSecondary,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            );
            if (narrow) {
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  details,
                  const SizedBox(height: 14),
                  FilledButton(
                    onPressed: onImport,
                    child: const Text('加入书架'),
                  ),
                ],
              );
            }
            return Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                Expanded(child: details),
                const SizedBox(width: 20),
                FilledButton(
                  onPressed: onImport,
                  child: const Text('加入书架'),
                ),
              ],
            );
          },
        ),
      );
    }
    return AppSurface(
      margin: const EdgeInsets.only(bottom: 12),
      padding: EdgeInsets.all(compact ? 14 : 16),
      tone: AppSurfaceTone.elevated,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          SizedBox(
            width: compact ? 70 : 62,
            height: compact ? 98 : 88,
            child: _SearchCover(result: result),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  result.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.typography.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  result.author.isEmpty ? result.sourceName : result.author,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.typography.caption?.copyWith(
                    color: theme.resources.textFillColorSecondary,
                  ),
                ),
                if (result.synopsis.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 6),
                  Text(
                    result.synopsis,
                    maxLines: compact ? 2 : 3,
                    overflow: TextOverflow.ellipsis,
                    style: theme.typography.caption?.copyWith(height: 1.4),
                  ),
                ],
                const SizedBox(height: 10),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: <Widget>[
                          StatusPill(result.sourceName, accented: true),
                          StatusPill(result.kind),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    FilledButton(
                      onPressed: onImport,
                      child: const Text('加入'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SearchCover extends StatelessWidget {
  const _SearchCover({required this.result});

  final SourceSearchResult result;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final cover = result.cover?.trim();
    final api = AppScope.of(context).api;
    final fallback = ColoredBox(
      color: theme.accentColor.withAlpha(
        theme.brightness == Brightness.dark ? 56 : 26,
      ),
      child: Icon(
        FluentIcons.book_answers,
        color: theme.accentColor,
      ),
    );
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: cover == null || cover.isEmpty
          ? fallback
          : Image.network(
              api.resolveUrl(cover),
              headers: api.headersForUrl(cover),
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => fallback,
            ),
    );
  }
}
