import 'dart:async';
import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/models/book.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/reader/reader_page.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/shared/responsive.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('loads chapter after AppScope becomes available', (tester) async {
    final harness = await _Harness.create(
      MockClient((request) async {
        expect(request.url.path, '/api/v1/books/book-1/chapters/1');
        return http.Response(
          jsonEncode(_chapterPayload),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    expect(find.text('这是章节正文。'), findsOneWidget);
    expect(find.text('暂时无法加载'), findsNothing);
  });

  testWidgets('Windows renders the v1.3.4 desktop reader chrome',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((_) async => http.Response(
            jsonEncode(_chapterPayload),
            200,
            headers: const <String, String>{
              'content-type': 'application/json; charset=utf-8',
            },
          )),
      targetPlatform: TargetPlatform.windows,
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    expect(find.byKey(const ValueKey('desktop-reader-page')), findsOneWidget);
    expect(find.text('上一章'), findsOneWidget);
    expect(find.text('下一章'), findsOneWidget);
    expect(find.text('这是章节正文。'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('reader-bottom-controls')),
      findsNothing,
    );
  });

  testWidgets('builds only visible paragraphs for a long chapter',
      (tester) async {
    final paragraphs =
        List<String>.generate(500, (index) => '正文段落 ${index + 1}');
    final payload = <String, Object?>{
      ..._chapterPayload,
      'content': paragraphs.join('\n'),
      'paragraphs': paragraphs,
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
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    expect(find.byType(SelectableText).evaluate().length, lessThan(50));
    expect(find.text('正文段落 500'), findsNothing);
  });

  testWidgets('prefetches the next chapter and switches without a loading page',
      (tester) async {
    final requestedChapters = <int>[];
    final prefetchRequests = <int>[];
    final releaseFirstChapter = Completer<void>();
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'PUT') {
          return http.Response('{}', 200);
        }
        final chapterIndex = int.parse(request.url.pathSegments.last);
        requestedChapters.add(chapterIndex);
        if (request.url.queryParameters['prefetch'] == 'true') {
          prefetchRequests.add(chapterIndex);
        }
        if (chapterIndex == 1) await releaseFirstChapter.future;
        return http.Response(
          jsonEncode(_chapterPayloadFor(chapterIndex)),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
      detail: _threeChapterDetail,
    );
    addTearDown(harness.dispose);
    addTearDown(() {
      if (!releaseFirstChapter.isCompleted) releaseFirstChapter.complete();
    });

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));

    expect(requestedChapters, containsAll(<int>[1, 2]));
    expect(prefetchRequests, contains(2));
    expect(prefetchRequests, isNot(contains(1)));

    releaseFirstChapter.complete();
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    expect(find.text('第一章正文。'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('reader-next-button')));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump(const Duration(milliseconds: 150));

    expect(find.text('正在打开章节'), findsNothing);
    expect(find.text('第二章正文。'), findsOneWidget);
    expect(requestedChapters.where((index) => index == 2), hasLength(1));
    expect(requestedChapters, contains(3));
  });

  testWidgets('opens reader settings and quickly jumps from the directory',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'PUT') return http.Response('{}', 200);
        return http.Response(
          jsonEncode(_chapterPayloadFor(
            int.parse(request.url.pathSegments.last),
          )),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
      detail: _threeChapterDetail,
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('reader-settings-button')));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byKey(const ValueKey('reader-settings-panel')), findsOneWidget);
    expect(find.byType(BackdropFilter), findsNothing);
    expect(find.byType(RepaintBoundary), findsWidgets);
    final bottomControls = find.byKey(
      const ValueKey('reader-bottom-controls'),
    );
    expect(tester.widget<AnimatedSlide>(bottomControls).offset, Offset.zero);
    expect(
      tester
          .widget<IgnorePointer>(
            find
                .descendant(
                  of: bottomControls,
                  matching: find.byType(IgnorePointer),
                )
                .first,
          )
          .ignoring,
      isFalse,
    );
    final eyeCare = find.byKey(const ValueKey('reader-palette-eyeCare'));
    await tester.ensureVisible(eyeCare);
    await tester.tap(eyeCare);
    final fontIncrease = find.byKey(
      const ValueKey('reader-font-increase'),
    );
    await tester.ensureVisible(fontIncrease);
    await tester.tap(fontIncrease);
    final relaxedSpacing = find.byKey(
      const ValueKey('reader-spacing-relaxed'),
    );
    await tester.ensureVisible(relaxedSpacing);
    await tester.tap(relaxedSpacing);
    final fadeAnimation = find.byKey(
      const ValueKey('reader-animation-fade'),
    );
    await tester.ensureVisible(fadeAnimation);
    await tester.tap(fadeAnimation);
    await tester.pump();
    expect(harness.appState.readerPaletteMode, ReaderPaletteMode.eyeCare);
    expect(harness.appState.readerFontSize, 20);
    expect(harness.appState.readerLineSpacing, ReaderLineSpacing.relaxed);
    expect(harness.appState.readerPageAnimation, ReaderPageAnimation.fade);
    expect(harness.appState.readerFlowMode, ReaderFlowMode.paged);

    final continuousMode = find.byKey(
      const ValueKey('reader-mode-continuous'),
    );
    await tester.ensureVisible(continuousMode);
    await tester.tap(continuousMode);
    await tester.pump();
    expect(harness.appState.readerFlowMode, ReaderFlowMode.continuous);
    final continuousReader = find.byKey(
      const ValueKey('reader-continuous-translated'),
    );
    expect(continuousReader, findsOneWidget);
    final continuousList = tester.widget<ListView>(continuousReader);
    final contentPadding = continuousList.padding! as EdgeInsets;
    expect(contentPadding.bottom, lessThan(80));
    expect(continuousList.cacheExtent, 420);
    expect(tester.getSize(continuousReader).height, 600);

    await tester.tap(find.byKey(const ValueKey('reader-settings-button')));
    await tester.pump();
    expect(find.byKey(const ValueKey('reader-settings-panel')), findsNothing);
    expect(
      find.byKey(const ValueKey('reader-directory-button')).hitTestable(),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('reader-directory-button')));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('reader-chapter-dialog')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('reader-chapter-3')));
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pumpAndSettle();

    expect(find.text('第三章正文。'), findsOneWidget);
    expect(find.text('第 3 / 3 章'), findsOneWidget);
  });

  testWidgets('a short tap on selectable text hides and restores controls',
      (tester) async {
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'PUT') return http.Response('{}', 200);
        return http.Response(
          jsonEncode(_chapterPayload),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();

    final topControls = find.byKey(const ValueKey('reader-top-controls'));
    final bottomControls = find.byKey(
      const ValueKey('reader-bottom-controls'),
    );
    await tester.tapAt(const Offset(400, 300));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.widget<AnimatedSlide>(topControls).offset.dy, lessThan(0));
    expect(
      tester.widget<AnimatedSlide>(bottomControls).offset.dy,
      greaterThan(0),
    );

    await tester.tapAt(const Offset(400, 300));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.widget<AnimatedSlide>(topControls).offset, Offset.zero);
    expect(tester.widget<AnimatedSlide>(bottomControls).offset, Offset.zero);
  });

  testWidgets('hiding Android reader controls keeps edge-to-edge system UI',
      (tester) async {
    final platformCalls = <MethodCall>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      platformCalls.add(call);
      return null;
    });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null),
    );
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'PUT') return http.Response('{}', 200);
        return http.Response(
          jsonEncode(_chapterPayload),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    platformCalls.clear();

    await tester.tapAt(const Offset(400, 300));
    await tester.pump(const Duration(milliseconds: 300));

    final modeCalls = platformCalls.where(
      (call) => call.method == 'SystemChrome.setEnabledSystemUIMode',
    );
    expect(modeCalls, isNotEmpty);
    expect(
      modeCalls.map((call) => '${call.arguments}').join('\n'),
      contains('SystemUiMode.edgeToEdge'),
    );
    expect(
      modeCalls.map((call) => '${call.arguments}').join('\n'),
      isNot(contains('SystemUiMode.immersiveSticky')),
    );
  });

  testWidgets('reader settings fit a narrow phone viewport', (tester) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.view.resetPhysicalSize);
    final harness = await _Harness.create(
      MockClient((request) async {
        if (request.method == 'PUT') return http.Response('{}', 200);
        return http.Response(
          jsonEncode(_chapterPayload),
          200,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
      }),
    );
    addTearDown(harness.dispose);

    await tester.pumpWidget(harness.widget);
    await tester.runAsync(() => Future<void>.delayed(Duration.zero));
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('reader-settings-button')));
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(const ValueKey('reader-settings-panel')), findsOneWidget);
    expect(find.byKey(const ValueKey('reader-palette-night')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

const _detail = BookDetail(
  book: Book(
    id: 'book-1',
    title: '测试作品',
    sourceUrl: 'https://example.com/book-1',
    kind: '长小说',
    language: '中文',
    status: '已导入',
    chapterCount: 1,
    translated: false,
    synopsis: '',
    lastReadChapterIndex: 1,
  ),
  author: '测试作者',
  synopsis: '',
  totalWords: 8,
  downloadedCount: 1,
  translatedCount: 0,
  progress: ReadingProgress(chapterIndex: 1, scrollRatio: 0),
  chapters: <Chapter>[
    Chapter(
      index: 1,
      title: '第一章',
      downloaded: true,
      translated: false,
      wordCount: 8,
      imageCount: 0,
    ),
  ],
);

const _chapterPayload = <String, Object?>{
  'chapter': <String, Object?>{
    'index': 1,
    'title': '第一章',
    'downloaded': true,
    'translated': false,
    'wordCount': 8,
    'imageCount': 0,
  },
  'content': '这是章节正文。',
  'paragraphs': <String>['这是章节正文。'],
  'mode': 'translated',
  'translatedAvailable': false,
  'imageSources': <String>[],
  'pageTranslations': <String>[],
};

const _threeChapterDetail = BookDetail(
  book: Book(
    id: 'book-1',
    title: '测试作品',
    sourceUrl: 'https://example.com/book-1',
    kind: '长小说',
    language: '中文',
    status: '已导入',
    chapterCount: 3,
    translated: false,
    synopsis: '',
    lastReadChapterIndex: 1,
  ),
  author: '测试作者',
  synopsis: '',
  totalWords: 24,
  downloadedCount: 3,
  translatedCount: 0,
  progress: ReadingProgress(chapterIndex: 1, scrollRatio: 0),
  chapters: <Chapter>[
    Chapter(
      index: 1,
      title: '第一章',
      downloaded: true,
      translated: false,
      wordCount: 8,
      imageCount: 0,
    ),
    Chapter(
      index: 2,
      title: '第二章',
      downloaded: true,
      translated: false,
      wordCount: 8,
      imageCount: 0,
    ),
    Chapter(
      index: 3,
      title: '第三章',
      downloaded: true,
      translated: false,
      wordCount: 8,
      imageCount: 0,
    ),
  ],
);

Map<String, Object?> _chapterPayloadFor(int chapterIndex) => <String, Object?>{
      'chapter': <String, Object?>{
        'index': chapterIndex,
        'title': '第${<String>['一', '二', '三'][chapterIndex - 1]}章',
        'downloaded': true,
        'translated': false,
        'wordCount': 8,
        'imageCount': 0,
      },
      'content': '第${<String>['一', '二', '三'][chapterIndex - 1]}章正文。',
      'paragraphs': <String>[
        '第${<String>['一', '二', '三'][chapterIndex - 1]}章正文。',
      ],
      'mode': 'translated',
      'translatedAvailable': false,
      'imageSources': <String>[],
      'pageTranslations': <String>[],
    };

class _Harness {
  _Harness({
    required this.widget,
    required this.appState,
    required this.api,
    required this.library,
    required this.sources,
    required this.tasks,
    required this.settings,
  });

  static Future<_Harness> create(
    http.Client client, {
    BookDetail detail = _detail,
    TargetPlatform targetPlatform = TargetPlatform.android,
  }) async {
    final appState = AppState(await SharedPreferences.getInstance());
    final api = ApiClient(() => appState.backendUrl, client: client);
    final backend = BackendConnectionManager(api, isConfigured: () => false);
    final library = LibraryController(api);
    final sources = SourcesController(api);
    final tasks = TasksController(api);
    final settings = SettingsController(api);
    final widget = FluentApp(
      theme: buildQingJuanTheme(
        Brightness.light,
        platform: targetPlatform,
      ),
      home: UiPlatformScope(
        platform: targetPlatform,
        child: AppScope(
          appState: appState,
          api: api,
          backend: backend,
          library: library,
          sources: sources,
          tasks: tasks,
          settings: settings,
          child: ReaderPage(
            detail: detail,
            initialChapterIndex: 1,
          ),
        ),
      ),
    );
    return _Harness(
      widget: widget,
      appState: appState,
      api: api,
      library: library,
      sources: sources,
      tasks: tasks,
      settings: settings,
    );
  }

  final Widget widget;
  final AppState appState;
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
    appState.dispose();
  }
}
