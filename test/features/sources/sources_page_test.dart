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
import 'package:qingjuan/core/models/site_plugin.dart';
import 'package:qingjuan/core/state/load_state.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/plugins_page.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/shared/responsive.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _samplePlugins = <SitePlugin>[
  SitePlugin(
    id: 'fanqie',
    name: '番茄小说',
    description: '解析作品目录与章节正文。',
    category: 'novel',
    domains: <String>['fanqienovel.com'],
    bookKinds: <String>['长小说'],
    tags: <String>['中文', '连载'],
    capabilities: <String>['preview', 'chapter', 'search'],
    version: '1.0.0',
    enabled: true,
    defaultEnabled: true,
  ),
  SitePlugin(
    id: 'bika',
    name: '哔咔漫画',
    description: '解析漫画作品与图片章节。',
    category: 'manga',
    domains: <String>['bika.example'],
    bookKinds: <String>['漫画'],
    tags: <String>['中文', '漫画'],
    capabilities: <String>['preview', 'chapter'],
    version: '1.1.0',
    enabled: false,
    defaultEnabled: true,
  ),
  SitePlugin(
    id: 'generic-web',
    name: '通用网页',
    description: '尝试解析未匹配专用模块的网页。',
    category: 'general',
    domains: <String>[],
    bookKinds: <String>['短文'],
    tags: <String>['回退'],
    capabilities: <String>['preview', 'chapter'],
    version: '1.0.0',
    enabled: true,
    defaultEnabled: true,
  ),
];

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('plugin settings toggles a backend-owned site module',
      (tester) async {
    final requests = <http.Request>[];
    final preferences = await SharedPreferences.getInstance();
    final appState = AppState(
      preferences,
      initialRemoteBackendToken: 'test-token',
    );
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests.add(request);
        final payload = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response.bytes(
          utf8.encode(jsonEncode(<String, Object?>{
            'id': 'fanqie',
            'name': '番茄小说',
            'description': '解析作品目录与章节正文。',
            'category': 'novel',
            'domains': <String>['fanqienovel.com'],
            'bookKinds': <String>['长小说'],
            'tags': <String>['中文'],
            'capabilities': <String>['preview', 'chapter'],
            'version': '1.0.0',
            'enabled': payload['enabled'],
            'defaultEnabled': true,
          })),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final backend = BackendConnectionManager(
      api,
      isConfigured: () => true,
    );
    final library = LibraryController(api);
    final sources = SourcesController(api)
      ..plugins = const <SitePlugin>[
        SitePlugin(
          id: 'fanqie',
          name: '番茄小说',
          description: '解析作品目录与章节正文。',
          category: 'novel',
          domains: <String>['fanqienovel.com'],
          bookKinds: <String>['长小说'],
          tags: <String>['中文'],
          capabilities: <String>['preview', 'chapter'],
          version: '1.0.0',
          enabled: true,
          defaultEnabled: true,
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
          data: const MediaQueryData(
            size: Size(390, 844),
            textScaler: TextScaler.linear(2),
          ),
          child: UiPlatformScope(
            platform: TargetPlatform.android,
            child: AppScope(
              appState: appState,
              api: api,
              backend: backend,
              library: library,
              sources: sources,
              tasks: tasks,
              settings: settings,
              child: const PluginsPage(),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('站点插件'), findsWidgets);
    expect(find.text('番茄小说'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey<String>('site-plugin-toggle-fanqie')),
    );
    await tester.pumpAndSettle();

    expect(sources.plugins.single.enabled, isFalse);
    expect(requests.single.method, 'PUT');
    expect(requests.single.url.path, '/api/v1/plugins/fanqie');
    expect(
        jsonDecode(requests.single.body), <String, Object?>{'enabled': false});
    expect(tester.takeException(), isNull);
  });

  testWidgets('plugin settings searches metadata and filters by state',
      (tester) async {
    await _pumpPluginPage(
      tester,
      plugins: _samplePlugins,
      platform: TargetPlatform.android,
      size: const Size(390, 844),
    );

    await tester.enterText(
      find.byKey(const ValueKey('plugin-search-box')),
      'bika.example',
    );
    await tester.pumpAndSettle();

    expect(find.text('哔咔漫画'), findsOneWidget);
    expect(find.text('番茄小说'), findsNothing);
    expect(find.text('1 个结果'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('site-plugin-details-bika')),
    );
    await tester.pumpAndSettle();
    expect(find.text('插件详情'), findsOneWidget);
    expect(find.byType(ContentDialog), findsNothing);
    expect(
      find.byKey(const ValueKey('mobile-sheet-surface')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('plugin-details-pane-bika')),
      findsOneWidget,
    );
    expect(find.text('模块标识'), findsOneWidget);
    await tester.tap(find.byIcon(FluentIcons.chrome_close));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('plugin-search-box')),
      '',
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('plugin-status-filter')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('已停用').last);
    await tester.pumpAndSettle();

    expect(find.text('哔咔漫画'), findsOneWidget);
    expect(find.text('番茄小说'), findsNothing);
    expect(find.text('1 个结果'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('plugin-search-box')),
      '不存在的模块',
    );
    await tester.pumpAndSettle();

    expect(find.text('没有匹配的插件'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('windows plugin settings uses grouped catalog and detail pane',
      (tester) async {
    await _pumpPluginPage(
      tester,
      plugins: _samplePlugins,
      platform: TargetPlatform.windows,
      size: const Size(1280, 800),
    );

    expect(find.byKey(const ValueKey('plugin-catalog')), findsOneWidget);
    expect(find.text('小说解析器'), findsWidgets);
    expect(find.text('漫画解析器'), findsWidgets);
    expect(find.text('通用回退'), findsWidgets);
    expect(
      find.byKey(const ValueKey('plugin-details-pane-fanqie')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey('plugin-nav-bika')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('plugin-details-pane-bika')),
      findsOneWidget,
    );
    expect(find.text('bika.example'), findsWidgets);
    expect(
      find.byKey(const ValueKey('site-plugin-toggle-bika')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('windows plugin workspace expands with independent scrollbars',
      (tester) async {
    await _pumpPluginPage(
      tester,
      plugins: _samplePlugins,
      platform: TargetPlatform.windows,
      size: const Size(1600, 900),
    );

    final catalogPane = find.byKey(const ValueKey('plugin-catalog-pane'));
    final detailsPane =
        find.byKey(const ValueKey('plugin-details-pane-fanqie'));
    expect(tester.getSize(catalogPane).width, inInclusiveRange(320, 400));
    expect(tester.getSize(detailsPane).width, greaterThan(1000));

    final catalogScrollbar = tester.widget<Scrollbar>(
      find.byKey(const ValueKey('plugin-catalog-scrollbar')),
    );
    final detailsScrollbar = tester.widget<Scrollbar>(
      find.byKey(const ValueKey('plugin-details-scrollbar-fanqie')),
    );
    expect(catalogScrollbar.thumbVisibility, isFalse);
    expect(detailsScrollbar.thumbVisibility, isFalse);
    expect(catalogScrollbar.controller, isNotNull);
    expect(detailsScrollbar.controller, isNotNull);
    expect(
      identical(catalogScrollbar.controller, detailsScrollbar.controller),
      isFalse,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
      'fanqie cookie login clears the secret and enables bookshelf import',
      (tester) async {
    final requests = <http.Request>[];
    final sources = await _pumpPluginPage(
      tester,
      plugins: const <SitePlugin>[
        SitePlugin(
          id: 'fanqie',
          name: '番茄小说',
          description: '解析番茄作品与当前账号书架。',
          category: 'novel',
          domains: <String>['fanqienovel.com'],
          bookKinds: <String>['长小说'],
          tags: <String>['中文', '账号书架'],
          capabilities: <String>[
            'preview',
            'chapter',
            'account_login',
            'cookie_login',
            'bookshelf_import',
          ],
          version: '1.1.0',
          enabled: true,
          defaultEnabled: true,
        ),
      ],
      platform: TargetPlatform.windows,
      size: const Size(1280, 800),
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path ==
            '/api/v1/plugins/fanqie/account/login-cookies') {
          return http.Response(
            jsonEncode(<String, Object?>{
              'loggedIn': true,
              'expiresAt': null,
            }),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        return http.Response('{}', 404);
      }),
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('plugin-cookie-login-fanqie')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('plugin-cookie-login-input')),
      'sessionid=private-cookie-value; sid_tt=private-session',
    );
    await tester.tap(
      find.byKey(const ValueKey('plugin-cookie-login-submit')),
    );
    await tester.pumpAndSettle();

    expect(requests, hasLength(1));
    expect(
      jsonDecode(requests.single.body),
      <String, Object?>{
        'cookies': 'sessionid=private-cookie-value; sid_tt=private-session',
      },
    );
    expect(sources.plugins.single.accountLoggedIn, isTrue);
    expect(find.textContaining('private-cookie-value'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('plugin-bookshelf-import-fanqie')),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('qidian exposes QR login before enabling one-click bookshelf',
      (tester) async {
    final sources = await _pumpPluginPage(
      tester,
      plugins: const <SitePlugin>[
        SitePlugin(
          id: 'qidian',
          name: '起点读书',
          description: '解析起点作品并添加当前账号书架。',
          category: 'novel',
          domains: <String>['qidian.com'],
          bookKinds: <String>['长小说', '轻小说'],
          tags: <String>['中文', '账号书架'],
          capabilities: <String>[
            'preview',
            'chapter',
            'on_demand',
            'account_login',
            'bookshelf_import',
          ],
          version: '1.0.0',
          enabled: true,
          defaultEnabled: true,
        ),
      ],
      platform: TargetPlatform.windows,
      size: const Size(1280, 800),
    );

    expect(
      find.byKey(const ValueKey<String>('plugin-login-qidian')),
      findsOneWidget,
    );
    final disabledImport = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('plugin-bookshelf-import-qidian')),
    );
    expect(disabledImport.onPressed, isNull);

    sources.setPluginAccountLoggedIn('qidian', true);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('plugin-login-qidian')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('plugin-logout-qidian')),
      findsOneWidget,
    );
    final enabledImport = tester.widget<FilledButton>(
      find.byKey(const ValueKey<String>('plugin-bookshelf-import-qidian')),
    );
    expect(enabledImport.onPressed, isNotNull);
    expect(tester.takeException(), isNull);
  });
}

Future<SourcesController> _pumpPluginPage(
  WidgetTester tester, {
  required List<SitePlugin> plugins,
  required TargetPlatform platform,
  required Size size,
  http.Client? client,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  final preferences = await SharedPreferences.getInstance();
  final appState = AppState(
    preferences,
    initialRemoteBackendToken: 'test-token',
  );
  final api = ApiClient(
    () => 'https://qingjuan.example.test',
    client: client ?? MockClient((_) async => http.Response('{}', 500)),
  );
  final backend = BackendConnectionManager(
    api,
    isConfigured: () => true,
  );
  final library = LibraryController(api);
  final sources = SourcesController(api)
    ..plugins = plugins
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
        data: MediaQueryData(size: size),
        child: UiPlatformScope(
          platform: platform,
          child: AppScope(
            appState: appState,
            api: api,
            backend: backend,
            library: library,
            sources: sources,
            tasks: tasks,
            settings: settings,
            child: const PluginsPage(),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return sources;
}
