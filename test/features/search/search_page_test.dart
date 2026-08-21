import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/models/source.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/search/search_page.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/shared/responsive.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('search engine switches among sources, Quark, Fanqie and Qidian',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'POST' &&
            request.url.path == '/api/v1/books/link-jobs') {
          return _jsonResponse(<String, Object?>{
            'id': 'link-quark-1',
            'mode': 'import',
            'status': 'queued',
            'progress': 0,
            'message': '等待解析',
            'logs': <Object?>[],
            'createdAt': '2026-08-19T12:00:00Z',
            'updatedAt': '2026-08-19T12:00:00Z',
          });
        }
        if (request.method == 'GET' &&
            request.url.path == '/api/v1/books/link-jobs/link-quark-1') {
          return _jsonResponse(<String, Object?>{
            'id': 'link-quark-1',
            'mode': 'import',
            'status': 'failed',
            'progress': 20,
            'message': '测试停止导入',
            'error': '测试停止导入',
            'logs': <Object?>[],
            'createdAt': '2026-08-19T12:00:00Z',
            'updatedAt': '2026-08-19T12:00:01Z',
          });
        }
        if (request.url.path == '/api/v1/sources/search') {
          return _jsonResponse(<Map<String, Object?>>[
            <String, Object?>{
              'title': '书源结果',
              'author': '作者甲',
              'synopsis': '来自已启用书源',
              'sourceUrl': 'https://source.example.test/book/1',
              'sourceId': 'source-1',
              'sourceName': '测试书源',
              'bookKind': '长小说',
              'sourceLanguage': '中文',
            },
          ]);
        }
        if (request.url.path == '/api/v1/builtin-sites/search') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          final isFanqie = body['sourceId'] == 'source-builtin-fanqie';
          final isQidian = body['sourceId'] == 'source-builtin-qidian';
          return _jsonResponse(<Map<String, Object?>>[
            <String, Object?>{
              'title': isQidian ? '起点结果' : (isFanqie ? '番茄结果' : '夸克结果'),
              'author': isQidian ? '作者丁' : (isFanqie ? '作者丙' : '作者乙'),
              'synopsis':
                  isQidian ? '来自起点移动站' : (isFanqie ? '来自番茄公开搜索' : '来自书旗网页内核'),
              'sourceUrl': isQidian
                  ? 'https://www.qidian.com/book/1209977/'
                  : (isFanqie
                      ? 'https://fanqienovel.com/page/7080092010052324352'
                      : 'https://www.shuqi.com/book/46543.html'),
              'bookKind': '长小说',
            },
          ]);
        }
        return _jsonResponse(<String, Object?>{'detail': 'unexpected'}, 404);
      }),
    );
    final preferences = await SharedPreferences.getInstance();
    final appState = AppState(
      preferences,
      initialRemoteBackendToken: 'test-token',
    );
    final backend = BackendConnectionManager(api, isConfigured: () => true);
    final library = LibraryController(api);
    final sources = SourcesController(api)
      ..sources = const <BookSource>[
        BookSource(
          id: 'source-1',
          name: '测试书源',
          baseUrl: 'https://source.example.test',
          description: '测试',
          enabled: true,
          supported: true,
          status: 'online',
          statusMessage: '',
          tags: <String>['搜索'],
        ),
      ]
      ..state = LoadState.ready;
    final tasks = TasksController(api);
    final settings = SettingsController(api);
    addTearDown(() {
      library.dispose();
      sources.dispose();
      tasks.dispose();
      settings.dispose();
      api.close();
      appState.dispose();
    });

    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(Brightness.light),
        home: MediaQuery(
          data: const MediaQueryData(size: Size(390, 844)),
          child: UiPlatformScope(
            platform: TargetPlatform.android,
            child: AppScope(
              appState: appState,
              api: api,
              backend: backend,
              auth: AuthController.localAdministrator(api),
              library: library,
              sources: sources,
              tasks: tasks,
              settings: settings,
              child: const SearchPage(),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<ComboBox<BookSearchEngine>>(
            find.byKey(const ValueKey('search-engine-selector')),
          )
          .value,
      BookSearchEngine.bookSources,
    );
    await tester.enterText(
      find.byKey(const ValueKey('search-query-input')),
      '测试作品',
    );
    await tester.tap(find.byKey(const ValueKey('search-submit-button')));
    await tester.pumpAndSettle();

    expect(find.text('书源结果'), findsOneWidget);
    expect(requests.single.url.path, '/api/v1/sources/search');

    await tester.tap(find.byKey(const ValueKey('search-engine-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('夸克').last);
    await tester.pumpAndSettle();

    expect(sources.results, isEmpty);
    expect(find.text('书源结果'), findsNothing);
    expect(find.text('结果来自书旗网页内核'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('search-submit-button')));
    await tester.pumpAndSettle();

    final quarkBody = jsonDecode(requests.last.body) as Map<String, dynamic>;
    expect(requests.last.url.path, '/api/v1/builtin-sites/search');
    expect(quarkBody['sourceId'], 'source-builtin-quark');
    expect(find.text('夸克结果'), findsOneWidget);
    expect(find.text('夸克小说'), findsWidgets);

    await tester.tap(find.text('加入').last);
    await tester.pumpAndSettle();

    final linkJobRequest = requests.lastWhere(
      (request) => request.url.path == '/api/v1/books/link-jobs',
    );
    final linkJobBody = jsonDecode(linkJobRequest.body) as Map<String, dynamic>;
    final importPayload = linkJobBody['payload'] as Map<String, dynamic>;
    expect(linkJobBody['mode'], 'import');
    expect(importPayload['sourceId'], 'source-builtin-quark');
    expect(importPayload['downloadMode'], 'on_demand');
    expect(
      requests.where((request) => request.url.path == '/api/v1/books/import'),
      isEmpty,
    );
    expect(find.text('导入失败'), findsOneWidget);
    await tester.pump(const Duration(seconds: 7));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('search-engine-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('番茄').last);
    await tester.pumpAndSettle();

    expect(sources.results, isEmpty);
    expect(find.text('夸克结果'), findsNothing);
    expect(find.text('结果来自番茄公开搜索'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('search-submit-button')));
    await tester.pumpAndSettle();

    final fanqieBody = jsonDecode(requests.last.body) as Map<String, dynamic>;
    expect(requests.last.url.path, '/api/v1/builtin-sites/search');
    expect(fanqieBody['sourceId'], 'source-builtin-fanqie');
    expect(find.text('番茄结果'), findsOneWidget);
    expect(find.text('番茄小说'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('search-engine-selector')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('起点').last);
    await tester.pumpAndSettle();

    expect(sources.results, isEmpty);
    expect(find.text('番茄结果'), findsNothing);
    expect(find.text('结果来自起点移动站'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('search-submit-button')));
    await tester.pumpAndSettle();

    final qidianBody = jsonDecode(requests.last.body) as Map<String, dynamic>;
    expect(requests.last.url.path, '/api/v1/builtin-sites/search');
    expect(qidianBody['sourceId'], 'source-builtin-qidian');
    expect(find.text('起点结果'), findsOneWidget);
    expect(find.text('起点中文网'), findsWidgets);
    expect(tester.takeException(), isNull);
  });
}

http.Response _jsonResponse(Object body, [int statusCode = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: <String, String>{'content-type': 'application/json'},
    );
