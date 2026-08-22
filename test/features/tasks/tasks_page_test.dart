import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_miuix/miuix.dart' as miuix;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/models/task.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/features/tasks/tasks_page.dart';
import 'package:qingjuan/shared/responsive.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('task summaries filter cards and expose useful metadata',
      (tester) async {
    final harness = await _Harness.create();
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('task-summary-all')), findsOneWidget);
    expect(find.byKey(const ValueKey('task-summary-active')), findsOneWidget);
    expect(find.byKey(const ValueKey('task-summary-failed')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('task-summary-completed')), findsOneWidget);
    expect(find.byKey(const ValueKey('task-tile-running')), findsOneWidget);
    expect(find.byKey(const ValueKey('task-tile-failed')), findsOneWidget);
    expect(find.text('08-09 12:30'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('task-page-text-running')), findsOneWidget);
    expect(find.textContaining('こんにちは → 你好'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('task-summary-failed')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('task-tile-failed')), findsOneWidget);
    expect(find.byKey(const ValueKey('task-tile-running')), findsNothing);
    expect(find.text('网络连接中断'), findsOneWidget);
    expect(find.text('正在下载章节'), findsNothing);
  });

  testWidgets('task page remains usable at 200 percent text scaling',
      (tester) async {
    final harness = await _Harness.create(
      size: const Size(960, 640),
      textScaler: const TextScaler.linear(2),
      brightness: Brightness.dark,
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pumpAndSettle();

    expect(find.text('任务'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('mobile task center opens incremental runtime logs',
      (tester) async {
    final harness = await _Harness.create(
      size: const Size(390, 844),
      platform: TargetPlatform.android,
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/tasks/running/logs') {
          expect(request.url.queryParameters['after'], '0');
          return http.Response(
            jsonEncode(<Map<String, Object?>>[
              <String, Object?>{
                'sequence': 7,
                'taskId': 'running',
                'level': 'info',
                'message': '开始下载第七章',
                'createdAt': '2026-08-23T08:30:00Z',
              },
              <String, Object?>{
                'sequence': 8,
                'taskId': 'running',
                'level': 'warning',
                'message': '网络波动，正在重试',
                'createdAt': '2026-08-23T08:30:01Z',
              },
            ]),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pumpAndSettle();

    expect(find.byType(miuix.MiuixTabRow), findsOneWidget);
    final logButton = find.byKey(const ValueKey('task-logs-toggle-running'));
    await tester.ensureVisible(logButton);
    await tester.pumpAndSettle();
    await tester.tap(logButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('task-logs-running')), findsOneWidget);
    expect(find.text('开始下载第七章'), findsOneWidget);
    expect(find.text('网络波动，正在重试'), findsOneWidget);
    expect(find.textContaining('#8'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test('task controller appends page results from the last sequence', () async {
    final requestedAfter = <String?>[];
    var logRequest = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/tasks') {
          return http.Response(
            jsonEncode(<Map<String, Object?>>[
              <String, Object?>{
                'id': 'translate-1',
                'bookId': 'book-1',
                'taskType': 'translate',
                'status': 'running',
                'totalCount': 1,
                'completedCount': 0,
                'progress': 0,
                'message': '正在翻译',
                'attempts': 1,
                'updatedAt': '2026-08-10T08:00:00Z',
              },
            ]),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        if (request.url.path == '/api/v1/tasks/translate-1/logs') {
          return http.Response(
            '[]',
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        requestedAfter.add(request.url.queryParameters['after']);
        logRequest += 1;
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            <String, Object?>{
              'sequence': logRequest,
              'taskId': 'translate-1',
              'chapterIndex': 1,
              'chapterTitle': '第一话',
              'pageNumber': logRequest,
              'totalPages': 2,
              'texts': <Map<String, Object?>>[
                <String, Object?>{
                  'order': 1,
                  'sourceText': '原文 $logRequest',
                  'translation': '译文 $logRequest',
                },
              ],
            },
          ]),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
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
      controller
          .pageResultsForTask('translate-1')
          .map((entry) => entry.sequence),
      <int>[1, 2],
    );
  });
}

class _Harness {
  _Harness({required this.widget, required this.scope});

  static Future<_Harness> create({
    Size size = const Size(1280, 800),
    TextScaler textScaler = TextScaler.noScaling,
    Brightness brightness = Brightness.light,
    TargetPlatform platform = TargetPlatform.windows,
    http.Client? client,
  }) async {
    final appState = AppState(await SharedPreferences.getInstance());
    final api = ApiClient(() => appState.backendUrl, client: client);
    final tasks = TasksController(api)
      ..state = LoadState.ready
      ..tasks = const <BookTask>[
        BookTask(
          id: 'running',
          bookId: 'book-1',
          type: 'download',
          status: 'running',
          totalCount: 10,
          completedCount: 4,
          progress: 40,
          message: '正在下载章节',
          attempts: 1,
          updatedAt: '2026-08-09T12:30:00',
        ),
        BookTask(
          id: 'failed',
          bookId: 'book-2',
          type: 'translate',
          status: 'failed',
          totalCount: 8,
          completedCount: 2,
          progress: 25,
          message: '翻译已停止',
          attempts: 2,
          updatedAt: '2026-08-09T11:10:00',
          error: '网络连接中断',
        ),
        BookTask(
          id: 'completed',
          bookId: 'book-3',
          type: 'download',
          status: 'completed',
          totalCount: 5,
          completedCount: 5,
          progress: 100,
          message: '下载完成',
          attempts: 1,
          updatedAt: '2026-08-08T18:20:00',
        ),
      ]
      ..taskPageResults['running'] = const <TaskPageResult>[
        TaskPageResult(
          sequence: 1,
          taskId: 'running',
          chapterIndex: 1,
          chapterTitle: '第一话',
          pageNumber: 1,
          totalPages: 10,
          texts: <TaskPageText>[
            TaskPageText(
              order: 1,
              sourceText: 'こんにちは',
              translation: '你好',
            ),
          ],
        ),
      ];
    final scope = AppScope(
      appState: appState,
      api: api,
      backend: BackendConnectionManager(api, isConfigured: () => false),
      auth: AuthController.localAdministrator(api),
      library: LibraryController(api),
      sources: SourcesController(api),
      tasks: tasks,
      settings: SettingsController(api),
      child: const TasksPage(),
    );
    return _Harness(
      scope: scope,
      widget: FluentApp(
        theme: buildQingJuanTheme(brightness),
        home: MediaQuery(
          data: MediaQueryData(size: size, textScaler: textScaler),
          child: UiPlatformScope(
            platform: platform,
            child: scope,
          ),
        ),
      ),
    );
  }

  final Widget widget;
  final AppScope scope;

  void dispose() {
    scope.library.dispose();
    scope.sources.dispose();
    scope.tasks.dispose();
    scope.settings.dispose();
    scope.api.close();
  }
}
