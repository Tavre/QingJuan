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
  final Map<String, List<TaskPageResult>> taskPageResults =
      <String, List<TaskPageResult>>{};
  String? error;
  Timer? _poller;
  bool _loadInProgress = false;
  int _loadRequestId = 0;
  bool _disposed = false;
  int _contextGeneration = 0;

  int get activeCount => tasks
      .where((task) => task.status == 'running' || task.status == 'queued')
      .length;

  void resetForBackendSwitch() {
    _contextGeneration += 1;
    _poller?.cancel();
    _poller = null;
    tasks = const [];
    taskPageResults.clear();
    error = null;
    state = LoadState.idle;
    _loadInProgress = false;
    _loadRequestId += 1;
    notifyListeners();
  }

  Future<void> load({bool silent = false}) async {
    if (_loadInProgress || _disposed) return;
    final generation = _contextGeneration;
    final requestId = ++_loadRequestId;
    _loadInProgress = true;
    var shouldNotify = false;
    if (!silent) {
      state = LoadState.loading;
      error = null;
      notifyListeners();
    }
    try {
      final nextTasks = await api.fetchTasks();
      if (_disposed || generation != _contextGeneration) return;
      final pageResultsChanged = await _loadIncrementalPageResults(
        nextTasks,
        generation: generation,
      );
      if (_disposed || generation != _contextGeneration) return;
      final nextState = nextTasks.isEmpty ? LoadState.empty : LoadState.ready;
      shouldNotify = pageResultsChanged ||
          !_sameTasks(tasks, nextTasks) ||
          state != nextState ||
          error != null;
      if (shouldNotify) {
        tasks = nextTasks;
        state = nextState;
        error = null;
      }
      _updatePolling();
    } catch (exception) {
      if (_disposed || generation != _contextGeneration) return;
      final nextError = '$exception';
      shouldNotify = state != LoadState.error || error != nextError;
      if (shouldNotify) {
        error = nextError;
        state = LoadState.error;
      }
    } finally {
      if (requestId == _loadRequestId) _loadInProgress = false;
      if (!_disposed && generation == _contextGeneration && shouldNotify) {
        notifyListeners();
      }
    }
  }

  Future<void> enqueue(
      String bookId, String action, List<int> chapterIndexes) async {
    final generation = _contextGeneration;
    await api.enqueueTask(bookId, action, chapterIndexes);
    if (!_disposed && generation == _contextGeneration) {
      await load(silent: true);
    }
  }

  Future<void> retry(String taskId) async {
    final generation = _contextGeneration;
    await api.retryTask(taskId);
    if (!_disposed && generation == _contextGeneration) {
      await load(silent: true);
    }
  }

  List<TaskPageResult> pageResultsForTask(String taskId) =>
      taskPageResults[taskId] ?? const <TaskPageResult>[];

  Future<bool> _loadIncrementalPageResults(
    List<BookTask> nextTasks, {
    required int generation,
  }) async {
    final previousActiveIds = tasks
        .where((task) => task.type == 'translate' && _isActive(task))
        .map((task) => task.id)
        .toSet();
    final watchedIds = nextTasks
        .where(
          (task) =>
              task.type == 'translate' &&
              (_isActive(task) || previousActiveIds.contains(task.id)),
        )
        .map((task) => task.id)
        .toSet();
    var changed = false;
    for (final taskId in watchedIds) {
      final current = taskPageResults[taskId] ?? const <TaskPageResult>[];
      final after = current.isEmpty ? 0 : current.last.sequence;
      try {
        final additions = await api.fetchTaskPageResults(taskId, after: after);
        if (additions.isEmpty ||
            _disposed ||
            generation != _contextGeneration) {
          continue;
        }
        final seen = current.map((entry) => entry.sequence).toSet();
        final merged = <TaskPageResult>[
          ...current,
          ...additions.where((entry) => seen.add(entry.sequence)),
        ];
        taskPageResults[taskId] =
            merged.length <= 200 ? merged : merged.sublist(merged.length - 200);
        changed = true;
      } catch (_) {
        // 逐页结果是增量增强信息；单次获取失败不应遮蔽任务主进度。
      }
    }
    final liveTaskIds = nextTasks.map((task) => task.id).toSet();
    final beforeCleanup = taskPageResults.length;
    taskPageResults.removeWhere((taskId, _) => !liveTaskIds.contains(taskId));
    return changed || taskPageResults.length != beforeCleanup;
  }

  bool _isActive(BookTask task) =>
      task.status == 'running' || task.status == 'queued';

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
