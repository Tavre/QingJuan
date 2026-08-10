import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/book.dart';
import '../../shared/feedback_widgets.dart';

class ReaderPage extends StatefulWidget {
  const ReaderPage({
    required this.detail,
    required this.initialChapterIndex,
    super.key,
  });

  final BookDetail detail;
  final int initialChapterIndex;

  @override
  State<ReaderPage> createState() => _ReaderPageState();
}

class _ReaderPageState extends State<ReaderPage> {
  final ScrollController _scrollController = ScrollController();
  late AppScope _scope;
  ChapterContent? _content;
  late int _chapterIndex;
  String _mode = 'translated';
  double _fontSize = 19;
  bool _loading = true;
  bool _initialized = false;
  int _loadToken = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _chapterIndex =
        widget.initialChapterIndex.clamp(1, widget.detail.chapters.length);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _scope = AppScope.of(context);
    if (!_initialized) {
      _initialized = true;
      _loadChapter();
    }
  }

  Future<void> _loadChapter() async {
    final loadToken = ++_loadToken;
    final chapterIndex = _chapterIndex;
    final mode = _mode;
    setState(() {
      _loading = true;
      _error = null;
      _content = null;
    });
    try {
      final content = await _scope.api.fetchChapter(
        widget.detail.book.id,
        chapterIndex,
        mode: mode,
      );
      if (!mounted || loadToken != _loadToken) return;
      setState(() => _content = content);
      if (_scrollController.hasClients) _scrollController.jumpTo(0);
    } catch (error) {
      if (mounted && loadToken == _loadToken) {
        setState(() => _error = '$error');
      }
    } finally {
      if (mounted && loadToken == _loadToken) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _saveProgress({int? chapterIndex}) async {
    if (!_scrollController.hasClients) return;
    final max = _scrollController.position.maxScrollExtent;
    final ratio =
        max <= 0 ? 0.0 : (_scrollController.offset / max).clamp(0.0, 1.0);
    try {
      await _scope.api.saveProgress(
        widget.detail.book.id,
        chapterIndex ?? _chapterIndex,
        ratio,
      );
    } catch (_) {
      // 阅读进度采用尽力保存，不阻断切章或退出。
    }
  }

  Future<void> _move(int delta) async {
    final next = _chapterIndex + delta;
    if (next < 1 || next > widget.detail.chapters.length) return;
    final previousChapterIndex = _chapterIndex;
    final previousContent = _content;
    unawaited(_saveProgress(chapterIndex: previousChapterIndex));
    setState(() => _chapterIndex = next);
    _evictChapterImages(previousContent);
    await _loadChapter();
  }

  void _evictChapterImages(ChapterContent? content) {
    if (content == null) return;
    for (final source in content.imageSources) {
      unawaited(
        NetworkImage(
          source,
          headers: _scope.api.headersForUrl(source),
        ).evict().then<void>((_) {}),
      );
    }
  }

  @override
  void dispose() {
    unawaited(_saveProgress());
    _evictChapterImages(_content);
    _scrollController.dispose();
    super.dispose();
  }

  Widget _buildReaderItem(
    BuildContext context,
    ChapterContent content,
    int index,
  ) {
    final theme = FluentTheme.of(context);
    if (index == 0) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 30),
        child: Text(content.chapter.title, style: theme.typography.title),
      );
    }

    final contentIndex = index - 1;
    if (content.imageSources.isNotEmpty) {
      final translation = contentIndex < content.pageTranslations.length
          ? content.pageTranslations[contentIndex].trim()
          : '';
      final placeholderHeight =
          (MediaQuery.sizeOf(context).height * 0.72).clamp(360.0, 720.0);
      return Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          children: <Widget>[
            // 漫画页按原始分辨率解码；ListView 仅创建视口附近的页面。
            Image.network(
              content.imageSources[contentIndex],
              headers:
                  _scope.api.headersForUrl(content.imageSources[contentIndex]),
              width: double.infinity,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
              loadingBuilder: (context, child, progress) {
                if (progress == null) return child;
                return SizedBox(
                  height: placeholderHeight,
                  child: const Center(child: ProgressRing()),
                );
              },
              errorBuilder: (_, __, ___) => const InfoBar(
                title: Text('图片加载失败'),
                severity: InfoBarSeverity.warning,
              ),
            ),
            if (translation.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: SelectableText(
                  translation,
                  style: TextStyle(fontSize: _fontSize, height: 1.7),
                ),
              ),
          ],
        ),
      );
    }

    final paragraphs = content.paragraphs.isEmpty
        ? <String>[content.content]
        : content.paragraphs;
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: SelectableText(
        paragraphs[contentIndex],
        style: TextStyle(fontSize: _fontSize, height: 1.85),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return NavigationView(
      appBar: NavigationAppBar(
        automaticallyImplyLeading: false,
        backgroundColor: theme.micaBackgroundColor,
        leading: Tooltip(
          message: '返回作品详情',
          child: IconButton(
            icon: const Icon(FluentIcons.back, semanticLabel: '返回作品详情'),
            onPressed: () => Navigator.pop(context),
          ),
        ),
        title: Text(widget.detail.book.title),
        actions: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Tooltip(
              message: '减小字号',
              child: IconButton(
                icon: const Icon(
                  FluentIcons.font_decrease,
                  semanticLabel: '减小字号',
                ),
                onPressed: () =>
                    setState(() => _fontSize = (_fontSize - 1).clamp(15, 28)),
              ),
            ),
            Tooltip(
              message: '增大字号',
              child: IconButton(
                icon: const Icon(
                  FluentIcons.font_increase,
                  semanticLabel: '增大字号',
                ),
                onPressed: () =>
                    setState(() => _fontSize = (_fontSize + 1).clamp(15, 28)),
              ),
            ),
            ToggleButton(
              checked: _mode == 'original',
              onChanged: (checked) {
                setState(() => _mode = checked ? 'original' : 'translated');
                _loadChapter();
              },
              child: Text(_mode == 'original' ? '原文' : '译文'),
            ),
            const SizedBox(width: 12),
          ],
        ),
      ),
      content: Column(
        children: <Widget>[
          Expanded(
            child: _loading
                ? const LoadingView(label: '正在打开章节')
                : _error != null
                    ? ErrorView(message: _error!, onRetry: _loadChapter)
                    : Scrollbar(
                        controller: _scrollController,
                        child: ListView.builder(
                          key: ValueKey<String>(
                            'reader-$_chapterIndex-$_mode',
                          ),
                          controller: _scrollController,
                          padding: const EdgeInsets.fromLTRB(24, 32, 24, 72),
                          cacheExtent: 900,
                          addAutomaticKeepAlives: false,
                          itemCount: 1 +
                              (_content!.imageSources.isNotEmpty
                                  ? _content!.imageSources.length
                                  : (_content!.paragraphs.isEmpty
                                      ? 1
                                      : _content!.paragraphs.length)),
                          itemBuilder: (context, index) => Center(
                            child: ConstrainedBox(
                              constraints: BoxConstraints(
                                maxWidth: _content!.imageSources.isNotEmpty
                                    ? 920
                                    : 760,
                              ),
                              child:
                                  _buildReaderItem(context, _content!, index),
                            ),
                          ),
                        ),
                      ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
            decoration: BoxDecoration(
              color: theme.micaBackgroundColor,
              border: Border(
                  top: BorderSide(
                      color: theme.resources.cardStrokeColorDefault)),
            ),
            child: Row(
              children: <Widget>[
                Button(
                  onPressed:
                      _chapterIndex > 1 && !_loading ? () => _move(-1) : null,
                  child: const Text('上一章'),
                ),
                Expanded(
                  child: Text(
                    '第 $_chapterIndex / ${widget.detail.chapters.length} 章',
                    textAlign: TextAlign.center,
                  ),
                ),
                FilledButton(
                  onPressed:
                      _chapterIndex < widget.detail.chapters.length && !_loading
                          ? () => _move(1)
                          : null,
                  child: const Text('下一章'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
