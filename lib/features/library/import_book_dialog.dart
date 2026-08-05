import 'package:file_selector/file_selector.dart';
import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/book.dart';
import '../../core/models/link_job.dart';
import 'library_controller.dart';

const _localNovelFiles = XTypeGroup(
  label: '小说文档',
  extensions: <String>['txt', 'text', 'docx', 'epub'],
);
const _localMangaFiles = XTypeGroup(
  label: 'PDF 漫画',
  extensions: <String>['pdf'],
);

Future<Book?> showImportBookDialog(BuildContext context) {
  final controller = AppScope.of(context).library;
  return showDialog<Book>(
    context: context,
    barrierDismissible: false,
    builder: (context) => _ImportBookDialog(controller: controller),
  );
}

class _ImportBookDialog extends StatefulWidget {
  const _ImportBookDialog({required this.controller});

  final LibraryController controller;

  @override
  State<_ImportBookDialog> createState() => _ImportBookDialogState();
}

class _ImportBookDialogState extends State<_ImportBookDialog> {
  final _urlController = TextEditingController();
  final _titleController = TextEditingController();
  final _logScrollController = ScrollController();
  String _kind = '长小说';
  String _language = '中文';
  bool _translate = false;
  bool _loading = false;
  bool _restoredPayload = false;
  int _visibleLogCount = 0;
  String? _error;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_restoredPayload) return;
    _restoredPayload = true;
    final payload = widget.controller.linkJobPayload;
    if (payload == null) return;
    _urlController.text = payload['sourceUrl'] as String? ?? '';
    _titleController.text = payload['title'] as String? ?? '';
    _kind = payload['bookKind'] as String? ?? _kind;
    _language = payload['language'] as String? ?? _language;
    _translate = payload['needTranslation'] as bool? ?? _translate;
  }

  @override
  void dispose() {
    _urlController.dispose();
    _titleController.dispose();
    _logScrollController.dispose();
    super.dispose();
  }

  JsonMap get _payload => <String, dynamic>{
        'sourceUrl': _urlController.text.trim(),
        'bookKind': _kind,
        'title': _titleController.text.trim(),
        'language': _language,
        'needTranslation': _translate,
      };

  Future<void> _previewRemote() async {
    if (_urlController.text.trim().isEmpty) {
      setState(() => _error = '请输入作品地址');
      return;
    }
    await _run(() async {
      await widget.controller.startLinkJob('preview', _payload);
    });
  }

  Future<void> _importRemote() async {
    if (_urlController.text.trim().isEmpty) {
      setState(() => _error = '请输入作品地址');
      return;
    }
    await _run(() async {
      await widget.controller.startLinkJob('import', _payload);
    });
  }

  Future<void> _importLocal() async {
    final file = await openFile(
      acceptedTypeGroups: const <XTypeGroup>[
        _localNovelFiles,
        _localMangaFiles,
      ],
    );
    if (file == null) return;
    final suffix = file.name.split('.').last.toLowerCase();
    final importKind = suffix == 'pdf'
        ? '漫画'
        : _kind == '漫画'
            ? '长小说'
            : _kind;
    await _run(() async {
      final book = await widget.controller.importLocal(
        filePath: file.path,
        kind: importKind,
        language: _language,
        translate: _translate,
        title: _titleController.text,
      );
      if (mounted) _close(book);
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _error = '$error');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final job = controller.linkJob;
        final busy = _loading || (job?.isActive ?? false);
        final preview = job?.preview;
        final importedBook = job?.book;
        _scrollLogsAfterBuild(job?.logs.length ?? 0);
        return ContentDialog(
          constraints: const BoxConstraints(maxWidth: 660),
          title: Row(
            children: <Widget>[
              const Expanded(child: Text('添加书籍')),
              if (busy)
                const Padding(
                  padding: EdgeInsets.only(left: 12),
                  child: ProgressRing(strokeWidth: 3, value: null),
                ),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text('导入网页地址，或选择 TXT、DOCX、EPUB 小说与 PDF 漫画。链接任务收起后会继续运行。'),
                const SizedBox(height: 18),
                InfoLabel(
                  label: '作品地址',
                  child: TextBox(
                    controller: _urlController,
                    placeholder: 'https://...',
                    enabled: !busy,
                  ),
                ),
                const SizedBox(height: 12),
                InfoLabel(
                  label: '自定义标题（可选）',
                  child: TextBox(controller: _titleController, enabled: !busy),
                ),
                const SizedBox(height: 12),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: InfoLabel(
                        label: '类型',
                        child: ComboBox<String>(
                          value: _kind,
                          isExpanded: true,
                          items: const <ComboBoxItem<String>>[
                            ComboBoxItem(value: '长小说', child: Text('长小说')),
                            ComboBoxItem(value: '轻小说', child: Text('轻小说')),
                            ComboBoxItem(value: '漫画', child: Text('漫画')),
                          ],
                          onChanged: busy
                              ? null
                              : (value) =>
                                  setState(() => _kind = value ?? _kind),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: InfoLabel(
                        label: '语言',
                        child: ComboBox<String>(
                          value: _language,
                          isExpanded: true,
                          items: const <ComboBoxItem<String>>[
                            ComboBoxItem(value: '中文', child: Text('中文')),
                            ComboBoxItem(value: '英文', child: Text('英文')),
                            ComboBoxItem(value: '日文', child: Text('日文')),
                          ],
                          onChanged: busy
                              ? null
                              : (value) => setState(
                                  () => _language = value ?? _language),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                ToggleSwitch(
                  checked: _translate,
                  onChanged: busy
                      ? null
                      : (value) => setState(() => _translate = value),
                  content: const Text('导入后启用翻译'),
                ),
                if (job != null) ...<Widget>[
                  const SizedBox(height: 18),
                  _LinkJobProgress(
                      job: job, scrollController: _logScrollController),
                ],
                if (preview != null) ...<Widget>[
                  const SizedBox(height: 14),
                  InfoBar(
                    title: Text(preview.title),
                    content:
                        Text('${preview.author} · ${preview.chapterCount} 章'),
                    severity: InfoBarSeverity.success,
                  ),
                ],
                if (importedBook != null) ...<Widget>[
                  const SizedBox(height: 14),
                  InfoBar(
                    title: const Text('导入完成'),
                    content: Text('《${importedBook.title}》已经加入书架。'),
                    severity: InfoBarSeverity.success,
                  ),
                ],
                if (_error != null || controller.linkJobConnectionError != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 14),
                    child: InfoBar(
                      title: const Text('操作失败'),
                      content: Text(
                          _error ?? controller.linkJobConnectionError ?? ''),
                      severity: InfoBarSeverity.error,
                    ),
                  ),
              ],
            ),
          ),
          actions: <Widget>[
            Button(
              onPressed: _loading ? null : _close,
              child: Text(job?.isActive ?? false ? '收起' : '取消'),
            ),
            if (job != null && !job.isActive)
              Button(
                onPressed: controller.clearLinkJob,
                child: const Text('新建'),
              ),
            Button(
              onPressed: busy ? null : _importLocal,
              child: const Text('导入本地文件'),
            ),
            Button(
              onPressed: busy ? null : _previewRemote,
              child: const Text('预览'),
            ),
            FilledButton(
              onPressed: busy
                  ? null
                  : importedBook != null
                      ? () => _close(importedBook)
                      : _importRemote,
              child: Text(importedBook != null ? '打开书籍' : '导入'),
            ),
          ],
        );
      },
    );
  }

  void _scrollLogsAfterBuild(int count) {
    if (count == _visibleLogCount) return;
    _visibleLogCount = count;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_logScrollController.hasClients) return;
      _logScrollController.animateTo(
        _logScrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  void _close([Book? book]) {
    Navigator.of(context, rootNavigator: true).pop(book);
  }
}

class _LinkJobProgress extends StatelessWidget {
  const _LinkJobProgress({required this.job, required this.scrollController});

  final LinkJob job;
  final ScrollController scrollController;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final failed = job.isFailed;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.resources.subtleFillColorSecondary,
        border: Border.all(color: theme.resources.cardStrokeColorDefault),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(failed ? FluentIcons.error : FluentIcons.processing),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  failed ? '链接任务失败' : job.message,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text('${job.progress.round()}%'),
            ],
          ),
          const SizedBox(height: 10),
          ProgressBar(value: job.progress.clamp(0, 100)),
          const SizedBox(height: 14),
          Text('实时日志', style: theme.typography.bodyStrong),
          const SizedBox(height: 8),
          SizedBox(
            height: 150,
            child: job.logs.isEmpty
                ? const Center(child: Text('等待后端返回进度…'))
                : ListView.builder(
                    controller: scrollController,
                    itemCount: job.logs.length,
                    itemBuilder: (context, index) {
                      final log = job.logs[index];
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Text(
                          '${log.createdAt}  ${log.message}',
                          style: theme.typography.caption,
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
