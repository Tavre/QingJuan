import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/source.dart';
import '../../shared/app_surface.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';
import '../detail/book_detail_page.dart';

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
          PageRouteBuilder<void>(
            pageBuilder: (_, __, ___) => BookDetailPage(bookId: book.id),
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
      builder: (context, _) => PageFrame(
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
                    result: result, onImport: () => _import(result)),
              ),
          ],
        ),
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
    return AppSurface(
      margin: const EdgeInsets.only(bottom: 8),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 560;
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
                        if (result.author.isNotEmpty) StatusPill(result.author),
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
          if (compact) {
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
}
