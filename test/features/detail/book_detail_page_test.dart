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

  test('posts the selected chapter export format and destination', () async {
    late http.Request capturedRequest;
    final api = ApiClient(
      () => 'http://127.0.0.1:8000',
      client: MockClient((request) async {
        capturedRequest = request;
        return http.Response(
          jsonEncode(<String, Object?>{
            'bookId': 'book-1',
            'chapterIndex': 3,
            'format': 'docx',
            'fileName': '第三章.docx',
            'filePath': r'D:\导出\第三章.docx',
            'fileCount': 1,
          }),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(api.close);

    final result = await api.exportChapter(
      bookId: 'book-1',
      chapterIndex: 3,
      format: 'docx',
      targetPath: r'D:\导出\第三章.docx',
    );

    expect(capturedRequest.method, 'POST');
    expect(capturedRequest.url.path, '/books/book-1/chapters/3/export');
    expect(
      jsonDecode(capturedRequest.body),
      <String, Object?>{
        'format': 'docx',
        'targetPath': r'D:\导出\第三章.docx',
      },
    );
    expect(result['fileCount'], 1);
  });

  test('posts selected chapters through the book export endpoint', () async {
    late http.Request capturedRequest;
    final api = ApiClient(
      () => 'http://127.0.0.1:8000',
      client: MockClient((request) async {
        capturedRequest = request;
        return http.Response(
          jsonEncode(<String, Object?>{
            'bookId': 'book-1',
            'format': 'epub',
            'fileName': '测试作品.epub',
            'filePath': r'D:\导出\测试作品.epub',
            'downloadUrl': '',
            'chapterCount': 2,
            'fileCount': 1,
          }),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(api.close);

    final result = await api.exportBook(
      bookId: 'book-1',
      chapterIndexes: const <int>[2, 4],
      format: 'epub',
      targetPath: r'D:\导出\测试作品.epub',
    );

    expect(capturedRequest.method, 'POST');
    expect(capturedRequest.url.path, '/books/book-1/export');
    expect(
      jsonDecode(capturedRequest.body),
      <String, Object?>{
        'format': 'epub',
        'targetPath': r'D:\导出\测试作品.epub',
        'chapterIndexes': <int>[2, 4],
      },
    );
    expect(result['chapterCount'], 2);
  });

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
    expect(find.text('听小说'), findsOneWidget);
  });

  testWidgets('hides audiobook action for manga books', (tester) async {
    final payload = <String, Object?>{
      ..._detailPayload,
      'book': <String, Object?>{
        ...(_detailPayload['book']! as Map<String, Object?>),
        'bookKind': '漫画',
      },
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

    expect(find.text('听小说'), findsNothing);
  });

  testWidgets('opens import-compatible novel chapter export formats',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((_) async => http.Response(
            jsonEncode(_detailPayload),
            200,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          )),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(
      find.byKey(const ValueKey<String>('chapter-export-1')),
    );
    await tester.pumpAndSettle();

    expect(find.text('导出本章'), findsOneWidget);
    expect(find.text('TXT'), findsOneWidget);
    expect(find.text('TEXT'), findsOneWidget);
    expect(find.text('DOCX'), findsOneWidget);
    expect(find.text('EPUB'), findsOneWidget);
    expect(
      tester.getTopLeft(find.text('TXT')).dx,
      closeTo(
        tester.getTopLeft(find.text('通用 UTF-8 纯文本，可重新导入青卷。')).dx,
        0.5,
      ),
    );
  });

  testWidgets('top download action opens the same export format dialog',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((_) async => http.Response(
            jsonEncode(_detailPayload),
            200,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          )),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('下载全部'));
    await tester.pumpAndSettle();

    expect(find.text('导出全部章节'), findsOneWidget);
    expect(find.text('TXT'), findsOneWidget);
    expect(find.text('TEXT'), findsOneWidget);
    expect(find.text('DOCX'), findsOneWidget);
    expect(find.text('EPUB'), findsOneWidget);
  });

  testWidgets('opens ordered image folder and PDF formats for manga chapters',
      (tester) async {
    final payload = <String, Object?>{
      ..._detailPayload,
      'book': <String, Object?>{
        ...(_detailPayload['book']! as Map<String, Object?>),
        'bookKind': '漫画',
      },
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
    await tester.tap(
      find.byKey(const ValueKey<String>('chapter-export-1')),
    );
    await tester.pumpAndSettle();

    expect(find.text('导出本章'), findsOneWidget);
    expect(find.text('图片文件夹'), findsOneWidget);
    expect(find.text('PDF'), findsOneWidget);
    expect(find.text('TXT'), findsNothing);
  });

  testWidgets('offers recovery and bookshelf deletion when detail fails',
      (tester) async {
    var deleteRequested = false;
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'DELETE') {
          deleteRequested = true;
          expect(request.url.path, '/books/book-1');
          return http.Response(
            jsonEncode(<String, String>{
              'status': 'ok',
              'bookId': 'book-1',
            }),
            200,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          );
        }
        expect(request.url.path, '/books/book-1');
        return http.Response(
          jsonEncode(<String, String>{
            'detail': '本地书籍目录不存在：C:/QingJuan/data/library/测试',
          }),
          404,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
      child: const _DetailLauncher(),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.tap(find.text('打开作品'));
    await tester.pumpAndSettle();

    expect(find.text('暂时无法加载'), findsOneWidget);
    expect(find.byIcon(FluentIcons.back), findsOneWidget);
    expect(find.text('重试'), findsOneWidget);
    expect(find.text('从书架删除'), findsOneWidget);

    await tester.tap(find.text('从书架删除'));
    await tester.pumpAndSettle();

    expect(find.text('删除这本书？'), findsOneWidget);
    expect(deleteRequested, isFalse);

    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pumpAndSettle();

    expect(deleteRequested, isTrue);
    expect(find.text('打开作品'), findsOneWidget);
  });

  testWidgets('returns from missing directory error without deleting',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((_) async => http.Response(
            jsonEncode(<String, String>{
              'detail': '本地书籍目录不存在：C:/QingJuan/data/library/测试',
            }),
            404,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          )),
      child: const _DetailLauncher(),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.tap(find.text('打开作品'));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(FluentIcons.back));
    await tester.pumpAndSettle();

    expect(find.text('打开作品'), findsOneWidget);
    expect(find.text('暂时无法加载'), findsNothing);
  });

  testWidgets('keeps error page available when bookshelf deletion fails',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((request) async {
        final detail = request.method == 'DELETE'
            ? '无法删除书架记录'
            : '本地书籍目录不存在：C:/QingJuan/data/library/测试';
        return http.Response(
          jsonEncode(<String, String>{'detail': detail}),
          request.method == 'DELETE' ? 500 : 404,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.pumpAndSettle();
    await tester.tap(find.text('从书架删除'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pumpAndSettle();

    expect(find.text('删除失败'), findsOneWidget);
    expect(find.text('暂时无法加载'), findsOneWidget);
    expect(find.text('从书架删除'), findsOneWidget);
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

  static Future<_Harness> create(
    http.Client client, {
    Widget child = const BookDetailPage(bookId: 'book-1'),
  }) async {
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
        child: child,
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

class _DetailLauncher extends StatelessWidget {
  const _DetailLauncher();

  @override
  Widget build(BuildContext context) {
    return Navigator(
      onGenerateRoute: (_) => PageRouteBuilder<void>(
        pageBuilder: (_, __, ___) => const _DetailLauncherButton(),
      ),
    );
  }
}

class _DetailLauncherButton extends StatelessWidget {
  const _DetailLauncherButton();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Button(
        onPressed: () => Navigator.of(context).push<void>(
          PageRouteBuilder<void>(
            pageBuilder: (_, __, ___) => const BookDetailPage(bookId: 'book-1'),
          ),
        ),
        child: const Text('打开作品'),
      ),
    );
  }
}
