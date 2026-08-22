import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/models/task.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';

void main() {
  test('active task logs are fetched incrementally with task polling',
      () async {
    final requestedAfter = <String?>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/tasks') {
          return _jsonResponse(<Map<String, Object?>>[
            _taskJson(status: 'running'),
          ]);
        }
        if (request.url.path == '/api/v1/tasks/task-1/logs') {
          final after = request.url.queryParameters['after'];
          requestedAfter.add(after);
          final sequence = int.parse(after ?? '0') + 1;
          return _jsonResponse(<Map<String, Object?>>[
            _taskLogJson(sequence),
          ]);
        }
        return http.Response('not found', 404);
      }),
    );
    final controller = TasksController(api);
    addTearDown(() {
      controller.dispose();
      api.close();
    });

    await controller.load();
    await controller.load(silent: true);

    expect(requestedAfter, <String?>['0', '1']);
    expect(
      controller.logsForTask('task-1').map((entry) => entry.sequence),
      <int>[1, 2],
    );
    expect(controller.taskLogsErrorForTask('task-1'), isNull);
  });

  test('on-demand task logs expose loading state and retain newest 500',
      () async {
    final response = Completer<http.Response>();
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) {
        expect(request.url.path, '/api/v1/tasks/task-1/logs');
        expect(request.url.queryParameters['after'], '0');
        return response.future;
      }),
    );
    final controller = TasksController(api)
      ..state = LoadState.ready
      ..tasks = <BookTask>[_task(status: 'completed')];
    addTearDown(() {
      controller.dispose();
      api.close();
    });

    final load = controller.loadTaskLogs('task-1');
    expect(controller.isTaskLogsLoading('task-1'), isTrue);

    response.complete(
      _jsonResponse(<Map<String, Object?>>[
        for (var sequence = 1; sequence <= 525; sequence++)
          _taskLogJson(sequence),
      ]),
    );
    await load;

    final logs = controller.logsForTask('task-1');
    expect(controller.isTaskLogsLoading('task-1'), isFalse);
    expect(logs, hasLength(500));
    expect(logs.first.sequence, 26);
    expect(logs.last.sequence, 525);
  });

  test('on-demand task log errors are isolated and clear after retry',
      () async {
    var requestCount = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requestCount += 1;
        if (requestCount == 1) {
          return http.Response(
            jsonEncode(<String, Object?>{'detail': '日志暂时不可用'}),
            500,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        return _jsonResponse(<Map<String, Object?>>[_taskLogJson(1)]);
      }),
    );
    final controller = TasksController(api)
      ..state = LoadState.ready
      ..tasks = <BookTask>[_task(status: 'failed')];
    addTearDown(() {
      controller.dispose();
      api.close();
    });

    await controller.loadTaskLogs('task-1');

    expect(controller.state, LoadState.ready);
    expect(controller.logsForTask('task-1'), isEmpty);
    expect(controller.taskLogsErrorForTask('task-1'), contains('日志暂时不可用'));

    await controller.loadTaskLogs('task-1');

    expect(controller.taskLogsErrorForTask('task-1'), isNull);
    expect(controller.logsForTask('task-1').single.sequence, 1);
  });

  test('backend switch clears logs and ignores an in-flight response',
      () async {
    final response = Completer<http.Response>();
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) => response.future),
    );
    final controller = TasksController(api)
      ..state = LoadState.ready
      ..tasks = <BookTask>[_task(status: 'completed')];
    addTearDown(() {
      controller.dispose();
      api.close();
    });

    final load = controller.loadTaskLogs('task-1');
    expect(controller.isTaskLogsLoading('task-1'), isTrue);

    controller.resetForBackendSwitch();
    response.complete(
      _jsonResponse(<Map<String, Object?>>[_taskLogJson(1)]),
    );
    await load;

    expect(controller.state, LoadState.idle);
    expect(controller.logsForTask('task-1'), isEmpty);
    expect(controller.taskLogsErrorForTask('task-1'), isNull);
    expect(controller.isTaskLogsLoading('task-1'), isFalse);
  });
}

BookTask _task({required String status}) => BookTask(
      id: 'task-1',
      bookId: 'book-1',
      type: 'download',
      status: status,
      totalCount: 2,
      completedCount: status == 'completed' ? 2 : 0,
      progress: status == 'completed' ? 100 : 0,
      message: '任务状态',
      attempts: 1,
      updatedAt: '2026-08-23T08:30:00Z',
    );

Map<String, Object?> _taskJson({required String status}) => <String, Object?>{
      'id': 'task-1',
      'bookId': 'book-1',
      'taskType': 'download',
      'status': status,
      'totalCount': 2,
      'completedCount': 0,
      'progress': 0,
      'message': '任务状态',
      'attempts': 1,
      'updatedAt': '2026-08-23T08:30:00Z',
    };

Map<String, Object?> _taskLogJson(int sequence) => <String, Object?>{
      'sequence': sequence,
      'taskId': 'task-1',
      'level': sequence.isEven ? 'warning' : 'info',
      'message': '日志 $sequence',
      'createdAt': '2026-08-23T08:30:00Z',
    };

http.Response _jsonResponse(Object payload) => http.Response(
      jsonEncode(payload),
      200,
      headers: <String, String>{'content-type': 'application/json'},
    );
