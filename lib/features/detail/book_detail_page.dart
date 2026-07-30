import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/book.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../reader/reader_page.dart';

class BookDetailPage extends StatefulWidget {
  const BookDetailPage({required this.bookId, super.key});

  final String bookId;

  @override
  State<BookDetailPage> createState() => _BookDetailPageState();
}

class _BookDetailPageState extends State<BookDetailPage> {
  final ScrollController _chapterScrollController = ScrollController();
  late AppScope _scope;
  BookDetail? _detail;
  String? _error;
  bool _loading = true;
  bool _actionRunning = false;
  bool _initialized = false;
  final Set<int> _selected = <int>{};

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _scope = AppScope.of(context);
    if (!_initialized) {
      _initialized = true;
      _load();
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final detail = await _scope.api.fetchBookDetail(widget.bookId);
      if (mounted) setState(() => _detail = detail);
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _enqueue(String action) async {
    final detail = _detail;
    if (detail == null) return;
    final chapters = _selected.isEmpty
        ? detail.chapters.map((chapter) => chapter.index).toList()
        : _selected.toList()
      ..sort();
    setState(() => _actionRunning = true);
    try {
      await _scope.tasks.enqueue(widget.bookId, action, chapters);
      if (mounted) {
        await displayInfoBar(
          context,
          builder: (_, __) => InfoBar(
            title: Text(action == 'download' ? '下载任务已创建' : '翻译任务已创建'),
            content: Text('共 ${chapters.length} 章，可在任务页面查看进度。'),
            severity: InfoBarSeverity.success,
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        await displayInfoBar(
          context,
          builder: (_, __) => InfoBar(
            title: const Text('任务创建失败'),
            content: Text('$error'),
            severity: InfoBarSeverity.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _actionRunning = false);
    }
  }

  Future<void> _delete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => ContentDialog(
        title: const Text('删除这本书？'),
        content: const Text('本地章节、翻译内容和阅读进度都将被删除，此操作无法撤销。'),
        actions: <Widget>[
          Button(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('删除')),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    await _scope.library.delete(widget.bookId);
    if (mounted) {
      Navigator.pop(context);
    }
  }

  void _openReader([int? chapterIndex]) {
    final detail = _detail;
    if (detail == null) return;
    Navigator.of(context).push<void>(
      PageRouteBuilder<void>(
        pageBuilder: (_, __, ___) => ReaderPage(
          detail: detail,
          initialChapterIndex: chapterIndex ?? detail.progress.chapterIndex,
        ),
      ),
    );
  }

  Widget _buildOverview(BookDetail detail, bool compact) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Flex(
          direction: compact ? Axis.vertical : Axis.horizontal,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            _BookSummary(detail: detail),
            SizedBox(width: compact ? 0 : 24, height: compact ? 20 : 0),
            if (!compact)
              Expanded(child: _Stats(detail: detail))
            else
              _Stats(detail: detail),
          ],
        ),
        const SizedBox(height: 24),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            FilledButton(
              onPressed: () => _openReader(),
              child: const Text('继续阅读'),
            ),
            Button(
              onPressed: _actionRunning ? null : () => _enqueue('download'),
              child: Text(_selected.isEmpty ? '下载全部' : '下载所选'),
            ),
            Button(
              onPressed: _actionRunning ? null : () => _enqueue('translate'),
              child: Text(_selected.isEmpty ? '翻译全部' : '翻译所选'),
            ),
            Button(
              onPressed: () {
                setState(() {
                  if (_selected.length == detail.chapters.length) {
                    _selected.clear();
                  } else {
                    _selected
                      ..clear()
                      ..addAll(
                        detail.chapters.map((chapter) => chapter.index),
                      );
                  }
                });
              },
              child: Text(
                _selected.length == detail.chapters.length ? '取消全选' : '全选章节',
              ),
            ),
          ],
        ),
        const SizedBox(height: 30),
        SectionTitle('章节', trailing: Text('已选择 ${_selected.length} 章')),
      ],
    );
  }

  @override
  void dispose() {
    _chapterScrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const NavigationView(content: LoadingView(label: '正在加载作品详情'));
    }
    if (_error != null) {
      return NavigationView(
          content: ErrorView(message: _error!, onRetry: _load));
    }
    final detail = _detail!;
    final compact = windowClassOf(context) == WindowClass.compact;
    return NavigationView(
      appBar: NavigationAppBar(
        automaticallyImplyLeading: false,
        leading: IconButton(
          icon: const Icon(FluentIcons.back),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(detail.book.title),
      ),
      content: PageFrame(
        title: detail.book.title,
        subtitle: [
          if (detail.author?.trim().isNotEmpty == true) detail.author!,
          detail.book.kind,
          detail.book.language,
          '${detail.chapters.length} 章',
        ].join(' · '),
        command: Button(onPressed: _delete, child: const Text('删除')),
        scrollable: false,
        child: Expanded(
          child: Scrollbar(
            controller: _chapterScrollController,
            child: CustomScrollView(
              controller: _chapterScrollController,
              cacheExtent: 600,
              slivers: <Widget>[
                SliverToBoxAdapter(child: _buildOverview(detail, compact)),
                SliverFixedExtentList(
                  itemExtent: 48,
                  delegate: SliverChildBuilderDelegate(
                    (context, index) {
                      final chapter = detail.chapters[index];
                      return _ChapterRow(
                        chapter: chapter,
                        selected: _selected.contains(chapter.index),
                        onSelected: (value) => setState(() {
                          if (value) {
                            _selected.add(chapter.index);
                          } else {
                            _selected.remove(chapter.index);
                          }
                        }),
                        onOpen: () => _openReader(chapter.index),
                      );
                    },
                    childCount: detail.chapters.length,
                    addAutomaticKeepAlives: false,
                  ),
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 24)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _BookSummary extends StatelessWidget {
  const _BookSummary({required this.detail});

  final BookDetail detail;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 620),
      child: Text(
        detail.synopsis.trim().isEmpty ? '暂无简介。' : detail.synopsis,
        style: FluentTheme.of(context)
            .typography
            .bodyLarge
            ?.copyWith(height: 1.65),
      ),
    );
  }
}

class _Stats extends StatelessWidget {
  const _Stats({required this.detail});

  final BookDetail detail;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 20,
      runSpacing: 12,
      children: <Widget>[
        _Metric(label: '总字数', value: '${detail.totalWords}'),
        _Metric(label: '已下载', value: '${detail.downloadedCount}'),
        _Metric(label: '已翻译', value: '${detail.translatedCount}'),
      ],
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 92,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(value, style: FluentTheme.of(context).typography.subtitle),
          const SizedBox(height: 3),
          Text(label, style: FluentTheme.of(context).typography.caption),
        ],
      ),
    );
  }
}

class _ChapterRow extends StatelessWidget {
  const _ChapterRow({
    required this.chapter,
    required this.selected,
    required this.onSelected,
    required this.onOpen,
  });

  final Chapter chapter;
  final bool selected;
  final ValueChanged<bool> onSelected;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 4),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: Row(
        children: <Widget>[
          Checkbox(
            checked: selected,
            onChanged: (value) => onSelected(value ?? false),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Button(
              onPressed: onOpen,
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('${chapter.index}. ${chapter.title}',
                    overflow: TextOverflow.ellipsis),
              ),
            ),
          ),
          const SizedBox(width: 10),
          if (chapter.downloaded) const Icon(FluentIcons.download, size: 14),
          if (chapter.translated) ...<Widget>[
            const SizedBox(width: 8),
            const Icon(FluentIcons.locale_language, size: 14),
          ],
        ],
      ),
    );
  }
}
