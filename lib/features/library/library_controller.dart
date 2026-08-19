import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_exception.dart';
import '../../core/models/book.dart';
import '../../core/models/link_job.dart';
import '../../core/state/load_state.dart';

class LibraryController extends ChangeNotifier {
  LibraryController(this.api);

  final ApiClient api;
  LoadState state = LoadState.idle;
  List<Book> books = const [];
  String query = '';
  String? error;
  LinkJob? linkJob;
  JsonMap? linkJobPayload;
  String? linkJobConnectionError;
  Timer? _linkJobPoller;
  bool _linkJobLoadInProgress = false;
  bool _disposed = false;
  double? importProgress;

  bool get hasActiveLinkJob => linkJob?.isActive ?? false;

  void resetForBackendSwitch() {
    _linkJobPoller?.cancel();
    _linkJobPoller = null;
    books = const [];
    query = '';
    error = null;
    linkJob = null;
    linkJobPayload = null;
    linkJobConnectionError = null;
    state = LoadState.idle;
    notifyListeners();
  }

  List<Book> get filteredBooks {
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty) return books;
    return books
        .where(
          (book) =>
              book.title.toLowerCase().contains(needle) ||
              book.synopsis.toLowerCase().contains(needle),
        )
        .toList();
  }

  Future<void> load({bool silent = false}) async {
    if (!silent) {
      state = LoadState.loading;
      error = null;
      notifyListeners();
    }
    try {
      books = await api.fetchBooks();
      state = books.isEmpty ? LoadState.empty : LoadState.ready;
    } catch (exception) {
      error = '$exception';
      state = LoadState.error;
    }
    notifyListeners();
  }

  void setQuery(String value) {
    if (query == value) return;
    query = value;
    notifyListeners();
  }

  Future<BookPreview> preview(JsonMap payload) => api.previewBook(payload);

  Future<void> startLinkJob(String mode, JsonMap payload) async {
    if (hasActiveLinkJob) return;
    linkJobConnectionError = null;
    linkJobPayload = Map<String, dynamic>.from(payload);
    linkJob = await api.startLinkJob(mode, payload);
    if (_disposed) return;
    notifyListeners();
    _updateLinkJobPolling();
    await refreshLinkJob();
  }

  Future<void> refreshLinkJob() async {
    final current = linkJob;
    if (current == null || _linkJobLoadInProgress || _disposed) return;
    _linkJobLoadInProgress = true;
    try {
      final next = await api.fetchLinkJob(current.id);
      if (_disposed) return;
      linkJob = next;
      linkJobConnectionError = null;
      _updateLinkJobPolling();
      if (next.isCompleted && next.mode == 'import' && next.book != null) {
        await load(silent: true);
      } else {
        notifyListeners();
      }
    } catch (exception) {
      if (_disposed) return;
      linkJobConnectionError = '$exception';
      notifyListeners();
    } finally {
      _linkJobLoadInProgress = false;
    }
  }

  void clearLinkJob() {
    if (hasActiveLinkJob) return;
    _linkJobPoller?.cancel();
    _linkJobPoller = null;
    linkJob = null;
    linkJobPayload = null;
    linkJobConnectionError = null;
    notifyListeners();
  }

  void _updateLinkJobPolling() {
    if (hasActiveLinkJob && _linkJobPoller == null) {
      _linkJobPoller = Timer.periodic(
        const Duration(seconds: 1),
        (_) => unawaited(refreshLinkJob()),
      );
    } else if (!hasActiveLinkJob) {
      _linkJobPoller?.cancel();
      _linkJobPoller = null;
    }
  }

  Future<Book> import(JsonMap payload) async {
    final book = await api.importBook(payload);
    await load(silent: true);
    return book;
  }

  Future<Book> importFromSearch(
    JsonMap payload, {
    Duration pollInterval = const Duration(milliseconds: 600),
    Duration timeout = const Duration(minutes: 3),
  }) async {
    if (hasActiveLinkJob) {
      throw const ApiException('已有链接任务正在处理，请等待当前任务完成后重试');
    }
    await startLinkJob('import', payload);
    final jobId = linkJob?.id;
    if (jobId == null || jobId.isEmpty) {
      throw const ApiException('后端未返回导入任务编号');
    }
    final deadline = DateTime.now().add(timeout);
    while (!_disposed && DateTime.now().isBefore(deadline)) {
      final current = linkJob;
      if (current == null || current.id != jobId) {
        throw const ApiException('导入任务状态已失效，请重新加入书架');
      }
      if (current.isCompleted) {
        final book = current.book;
        if (book == null) {
          throw const ApiException('导入任务已完成，但未返回书籍信息');
        }
        return book;
      }
      if (current.isFailed) {
        throw ApiException(
          current.error?.trim().isNotEmpty == true
              ? current.error!.trim()
              : (current.message.trim().isEmpty
                  ? '导入失败，请稍后重试'
                  : current.message.trim()),
        );
      }
      await Future<void>.delayed(pollInterval);
      await refreshLinkJob();
    }
    if (_disposed) throw const ApiException('导入已取消');
    throw const ApiException('导入等待超时，任务仍可在书架页继续查看');
  }

  Future<Book> importLocal({
    required String filePath,
    required String kind,
    required String language,
    required bool translate,
    String? title,
  }) async {
    importProgress = 0;
    notifyListeners();
    try {
      final book = await api.importLocalBook(
        filePath: filePath,
        kind: kind,
        language: language,
        translate: translate,
        title: title,
        onProgress: (sentBytes, totalBytes) {
          if (_disposed || totalBytes <= 0) return;
          importProgress = sentBytes / totalBytes;
          notifyListeners();
        },
      );
      await load(silent: true);
      return book;
    } finally {
      importProgress = null;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> delete(String bookId) async {
    await api.deleteBook(bookId);
    books = books.where((book) => book.id != bookId).toList();
    state = books.isEmpty ? LoadState.empty : LoadState.ready;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _linkJobPoller?.cancel();
    super.dispose();
  }
}
