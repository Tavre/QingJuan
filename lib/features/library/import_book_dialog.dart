import 'package:file_selector/file_selector.dart';
import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/book.dart';

Future<Book?> showImportBookDialog(BuildContext context) {
  return showDialog<Book>(
    context: context,
    builder: (context) => const _ImportBookDialog(),
  );
}

class _ImportBookDialog extends StatefulWidget {
  const _ImportBookDialog();

  @override
  State<_ImportBookDialog> createState() => _ImportBookDialogState();
}

class _ImportBookDialogState extends State<_ImportBookDialog> {
  final _urlController = TextEditingController();
  final _titleController = TextEditingController();
  String _kind = '长小说';
  String _language = '中文';
  bool _translate = false;
  bool _loading = false;
  BookPreview? _preview;
  String? _error;

  @override
  void dispose() {
    _urlController.dispose();
    _titleController.dispose();
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
      final preview = await AppScope.of(context).library.preview(_payload);
      if (!mounted) return;
      setState(() {
        _preview = preview;
        if (_titleController.text.trim().isEmpty) {
          _titleController.text = preview.title;
        }
      });
    });
  }

  Future<void> _importRemote() async {
    await _run(() async {
      final book = await AppScope.of(context).library.import(_payload);
      if (mounted) Navigator.pop(context, book);
    });
  }

  Future<void> _importLocal() async {
    const group = XTypeGroup(label: '文本', extensions: <String>['txt', 'text']);
    final file = await openFile(acceptedTypeGroups: const <XTypeGroup>[group]);
    if (file == null) return;
    await _run(() async {
      final book = await AppScope.of(context).library.importLocal(
            filePath: file.path,
            kind: _kind,
            language: _language,
            translate: _translate,
            title: _titleController.text,
          );
      if (mounted) Navigator.pop(context, book);
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
    return ContentDialog(
      constraints: const BoxConstraints(maxWidth: 620),
      title: const Text('添加书籍'),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text('导入网页地址，或选择本地 TXT/TEXT 文件。'),
            const SizedBox(height: 18),
            InfoLabel(
              label: '作品地址',
              child: TextBox(
                controller: _urlController,
                placeholder: 'https://...',
                enabled: !_loading,
              ),
            ),
            const SizedBox(height: 12),
            InfoLabel(
              label: '自定义标题（可选）',
              child: TextBox(controller: _titleController, enabled: !_loading),
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
                      onChanged: _loading
                          ? null
                          : (value) => setState(() => _kind = value ?? _kind),
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
                      onChanged: _loading
                          ? null
                          : (value) =>
                              setState(() => _language = value ?? _language),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            ToggleSwitch(
              checked: _translate,
              onChanged: _loading
                  ? null
                  : (value) => setState(() => _translate = value),
              content: const Text('导入后启用翻译'),
            ),
            if (_preview != null) ...<Widget>[
              const SizedBox(height: 18),
              InfoBar(
                title: Text(_preview!.title),
                content:
                    Text('${_preview!.author} · ${_preview!.chapterCount} 章'),
                severity: InfoBarSeverity.success,
              ),
            ],
            if (_error != null) ...<Widget>[
              const SizedBox(height: 14),
              InfoBar(
                title: const Text('操作失败'),
                content: Text(_error!),
                severity: InfoBarSeverity.error,
              ),
            ],
          ],
        ),
      ),
      actions: <Widget>[
        Button(
            onPressed: _loading ? null : () => Navigator.pop(context),
            child: const Text('取消')),
        Button(
            onPressed: _loading ? null : _importLocal,
            child: const Text('导入本地文件')),
        Button(
            onPressed: _loading ? null : _previewRemote,
            child: const Text('预览')),
        FilledButton(
            onPressed: _loading ? null : _importRemote,
            child: const Text('导入')),
      ],
    );
  }
}
