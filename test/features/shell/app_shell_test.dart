import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';
import 'package:qingjuan/core/models/book.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/shell/app_shell.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('narrow desktop window uses compact navigation pane',
      (tester) async {
    final harness = await _Harness.create(const Size(390, 844));
    addTearDown(harness.dispose);
    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    final compactView =
        tester.widget<NavigationView>(find.byType(NavigationView));
    expect(compactView.pane?.displayMode, PaneDisplayMode.compact);
    expect(compactView.pane?.items, hasLength(5));
    expect(find.text('书架'), findsWidgets);
  });

  testWidgets('expanded layout uses persistent navigation pane',
      (tester) async {
    final harness = await _Harness.create(const Size(1280, 800));
    addTearDown(harness.dispose);
    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    final expandedView =
        tester.widget<NavigationView>(find.byType(NavigationView));
    expect(expandedView.pane?.displayMode, PaneDisplayMode.open);
    expect(expandedView.pane?.items, hasLength(5));
    expect(expandedView.appBar?.automaticallyImplyLeading, isFalse);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('expanded navigation pane can collapse and expand',
      (tester) async {
    final harness = await _Harness.create(const Size(1280, 800));
    addTearDown(harness.dispose);
    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    await tester.tap(find.byKey(const ValueKey('navigation-pane-toggle')));
    await tester.pump(const Duration(milliseconds: 600));

    var view = tester.widget<NavigationView>(find.byType(NavigationView));
    expect(view.pane?.displayMode, PaneDisplayMode.compact);

    await tester.tap(find.byKey(const ValueKey('navigation-pane-toggle')));
    await tester.pump(const Duration(milliseconds: 600));

    view = tester.widget<NavigationView>(find.byType(NavigationView));
    expect(view.pane?.displayMode, PaneDisplayMode.open);
  });

  testWidgets('expanded navigation pane supports drag resizing',
      (tester) async {
    final harness = await _Harness.create(const Size(1280, 800));
    addTearDown(harness.dispose);
    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    final before =
        tester.widget<NavigationView>(find.byType(NavigationView)).pane!;
    final initialWidth = before.size!.openWidth!;

    await tester.drag(
      find.byKey(const ValueKey('navigation-pane-resizer')),
      const Offset(60, 0),
    );
    await tester.pump(const Duration(milliseconds: 600));

    final after =
        tester.widget<NavigationView>(find.byType(NavigationView)).pane!;
    expect(after.size!.openWidth, greaterThan(initialWidth));
  });

  testWidgets('book card handles a long CJK title without overflowing',
      (tester) async {
    final harness = await _Harness.create(
      const Size(1280, 800),
      textScaler: const TextScaler.linear(1.5),
      books: const <Book>[
        Book(
          id: 'long-title',
          title: '[Aliceholic13]花火制服コスで竜マ＆バイオナナの非常に長い作品タイトル',
          sourceUrl: '',
          kind: '漫画',
          language: '中文',
          status: '已导入',
          chapterCount: 120,
          translated: true,
          synopsis: '',
          lastReadChapterIndex: 99,
        ),
      ],
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    expect(find.textContaining('[Aliceholic13]'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

class _Harness {
  _Harness({
    required this.widget,
    required this.api,
    required this.library,
    required this.sources,
    required this.tasks,
    required this.settings,
  });

  static Future<_Harness> create(
    Size viewport, {
    List<Book> books = const <Book>[],
    TextScaler textScaler = TextScaler.noScaling,
  }) async {
    final appState = AppState(await SharedPreferences.getInstance());
    final api = ApiClient(() => appState.backendUrl);
    final backend = BackendProcessManager(api);
    final library = LibraryController(api);
    if (books.isNotEmpty) {
      library.books = books;
      library.state = LoadState.ready;
    }
    final sources = SourcesController(api);
    final tasks = TasksController(api);
    final settings = SettingsController(api);
    final widget = FluentApp(
      theme: buildQingJuanTheme(Brightness.light),
      home: MediaQuery(
        data: MediaQueryData(size: viewport, textScaler: textScaler),
        child: AppScope(
          appState: appState,
          api: api,
          backend: backend,
          library: library,
          sources: sources,
          tasks: tasks,
          settings: settings,
          child: const AppShell(),
        ),
      ),
    );
    return _Harness(
      widget: widget,
      api: api,
      library: library,
      sources: sources,
      tasks: tasks,
      settings: settings,
    );
  }

  final Widget widget;
  final ApiClient api;
  final LibraryController library;
  final SourcesController sources;
  final TasksController tasks;
  final SettingsController settings;

  void dispose() {
    library.dispose();
    sources.dispose();
    tasks.dispose();
    settings.dispose();
    api.close();
  }
}
