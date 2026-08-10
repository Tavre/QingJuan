import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';
import 'package:qingjuan/core/models/task.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/features/tasks/tasks_page.dart';
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

    expect(find.text('任务'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _Harness {
  _Harness({required this.widget, required this.scope});

  static Future<_Harness> create({
    Size size = const Size(1280, 800),
    TextScaler textScaler = TextScaler.noScaling,
    Brightness brightness = Brightness.light,
  }) async {
    final appState = AppState(await SharedPreferences.getInstance());
    final api = ApiClient(() => appState.backendUrl);
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
          progress: 0.4,
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
          progress: 0.25,
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
          progress: 1,
          message: '下载完成',
          attempts: 1,
          updatedAt: '2026-08-08T18:20:00',
        ),
      ];
    final scope = AppScope(
      appState: appState,
      api: api,
      backend: BackendProcessManager(api),
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
          child: scope,
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
