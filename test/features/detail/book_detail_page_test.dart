import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';
import 'package:qingjuan/features/detail/book_detail_page.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('loads detail after AppScope becomes available', (tester) async {
    final harness = await _Harness.create(
      MockClient((request) async {
        expect(request.url.path, '/books/book-1');
        return http.Response(
          jsonEncode(_detailPayload),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('测试作品'), findsWidgets);
    expect(find.text('暂时无法加载'), findsNothing);
  });

  testWidgets('builds only visible chapter rows for a large book',
      (tester) async {
    final chapters = List<Object?>.generate(
      1000,
      (index) => <String, Object?>{
        'index': index + 1,
        'title': '第${index + 1}章',
        'downloaded': true,
        'translated': false,
        'wordCount': 1200,
        'imageCount': 0,
      },
    );
    final payload = <String, Object?>{
      ..._detailPayload,
      'chapters': chapters,
    };
    final harness = await _Harness.create(
      MockClient((_) async => http.Response(
            jsonEncode(payload),
            200,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          )),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.byType(Checkbox).evaluate().length, lessThan(50));
    expect(find.text('1000. 第1000章'), findsNothing);
  });
}

const _detailPayload = <String, Object?>{
  'book': <String, Object?>{
    'id': 'book-1',
    'title': '测试作品',
    'sourceUrl': 'https://example.com/book-1',
    'bookKind': '长小说',
    'language': '中文',
    'status': '已导入',
    'chapterCount': 1,
    'translated': false,
    'synopsis': '用于验证页面生命周期。',
    'lastReadChapterIndex': 1,
  },
  'author': '测试作者',
  'synopsis': '用于验证页面生命周期。',
  'totalWords': 1200,
  'downloadedChapterCount': 1,
  'translatedChapterCount': 0,
  'progress': <String, Object?>{
    'lastChapterIndex': 1,
    'lastScrollRatio': 0.0,
  },
  'chapters': <Object?>[
    <String, Object?>{
      'index': 1,
      'title': '第一章',
      'downloaded': true,
      'translated': false,
      'wordCount': 1200,
      'imageCount': 0,
    },
  ],
};

class _Harness {
  _Harness({
    required this.widget,
    required this.api,
    required this.library,
    required this.sources,
    required this.tasks,
    required this.settings,
  });

  static Future<_Harness> create(http.Client client) async {
    final appState = AppState(await SharedPreferences.getInstance());
    final api = ApiClient(() => appState.backendUrl, client: client);
    final backend = BackendProcessManager(api);
    final library = LibraryController(api);
    final sources = SourcesController(api);
    final tasks = TasksController(api);
    final settings = SettingsController(api);
    final widget = FluentApp(
      theme: buildQingJuanTheme(Brightness.light),
      home: AppScope(
        appState: appState,
        api: api,
        backend: backend,
        library: library,
        sources: sources,
        tasks: tasks,
        settings: settings,
        child: const BookDetailPage(bookId: 'book-1'),
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
