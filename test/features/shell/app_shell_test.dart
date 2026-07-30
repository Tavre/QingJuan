import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';
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
    expect(compactView.pane?.footerItems, hasLength(1));
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
    expect(expandedView.pane?.footerItems, hasLength(1));
    expect(expandedView.appBar?.automaticallyImplyLeading, isFalse);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('about navigation shows project and community information',
      (tester) async {
    MethodCall? clipboardCall;
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') clipboardCall = call;
      return null;
    });
    addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null),
    );
    final harness = await _Harness.create(const Size(1280, 800));
    addTearDown(harness.dispose);
    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 600));

    final view = tester.widget<NavigationView>(find.byType(NavigationView));
    final aboutItem = view.pane!.footerItems.single as PaneItem;
    expect((aboutItem.title! as Text).data, '关于');

    await tester.tap(
      find.byKey(const ValueKey('about-navigation-item')),
    );
    await tester.pumpAndSettle();

    expect(find.text('关于青卷'), findsOneWidget);
    expect(find.text('https://github.com/Tavre/QingJuan'), findsOneWidget);
    expect(find.text('1074882763'), findsOneWidget);
    expect(find.text('Windows 10 / Windows 11'), findsOneWidget);
    expect(find.text('GNU General Public License v3.0'), findsOneWidget);

    await tester.tap(
      find.byKey(
        const ValueKey('copy-https://github.com/Tavre/QingJuan'),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('GitHub 地址已复制'), findsOneWidget);
    expect(clipboardCall?.method, 'Clipboard.setData');
    expect(
      (clipboardCall?.arguments as Map<Object?, Object?>?)?['text'],
      'https://github.com/Tavre/QingJuan',
    );
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
