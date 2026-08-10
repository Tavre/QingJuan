import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/models/task.dart';
import '../../core/state/load_state.dart';

class TasksController extends ChangeNotifier {
  TasksController(this.api);

  final ApiClient api;
  LoadState state = LoadState.idle;
  List<BookTask> tasks = const [];
  String? error;
  Timer? _poller;
  bool _loadInProgress = false;
  bool _disposed = false;

  int get activeCount => tasks
      .where((task) => task.status == 'running' || task.status == 'queued')
      .length;

  void resetForBackendSwitch() {
    _poller?.cancel();
    _poller = null;
    tasks = const [];
    error = null;
    state = LoadState.idle;
    notifyListeners();
  }

  Future<void> load({bool silent = false}) async {
    if (_loadInProgress || _disposed) return;
    _loadInProgress = true;
    var shouldNotify = false;
    if (!silent) {
      state = LoadState.loading;
      error = null;
      notifyListeners();
    }
    try {
      final nextTasks = await api.fetchTasks();
      if (_disposed) return;
      final nextState = nextTasks.isEmpty ? LoadState.empty : LoadState.ready;
      shouldNotify =
          !_sameTasks(tasks, nextTasks) || state != nextState || error != null;
      if (shouldNotify) {
        tasks = nextTasks;
        state = nextState;
        error = null;
      }
      _updatePolling();
    } catch (exception) {
      if (_disposed) return;
      final nextError = '$exception';
      shouldNotify = state != LoadState.error || error != nextError;
      if (shouldNotify) {
        error = nextError;
        state = LoadState.error;
      }
    } finally {
      _loadInProgress = false;
      if (!_disposed && shouldNotify) notifyListeners();
    }
  }

  Future<void> enqueue(
      String bookId, String action, List<int> chapterIndexes) async {
    await api.enqueueTask(bookId, action, chapterIndexes);
    await load(silent: true);
  }

  Future<void> retry(String taskId) async {
    await api.retryTask(taskId);
    await load(silent: true);
  }

  void _updatePolling() {
    if (activeCount > 0 && _poller == null) {
      _poller = Timer.periodic(
        const Duration(seconds: 2),
        (_) => unawaited(load(silent: true)),
      );
    } else if (activeCount == 0) {
      _poller?.cancel();
      _poller = null;
    }
  }

  bool _sameTasks(List<BookTask> current, List<BookTask> next) {
    if (identical(current, next)) return true;
    if (current.length != next.length) return false;
    for (var index = 0; index < current.length; index++) {
      final left = current[index];
      final right = next[index];
      if (left.id != right.id ||
          left.status != right.status ||
          left.completedCount != right.completedCount ||
          left.totalCount != right.totalCount ||
          left.progress != right.progress ||
          left.message != right.message ||
          left.error != right.error ||
          left.updatedAt != right.updatedAt) {
        return false;
      }
    }
    return true;
  }

  @override
  void dispose() {
    _disposed = true;
    _poller?.cancel();
    super.dispose();
  }
}
