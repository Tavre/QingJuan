import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/core/models/book.dart';
import 'package:qingjuan/core/models/tts_speech_style.dart';
import 'package:qingjuan/features/audiobook/audiobook_controller.dart';
import 'package:qingjuan/features/audiobook/audiobook_page.dart';
import 'package:qingjuan/shared/responsive.dart';

void main() {
  testWidgets('audiobook page loads text and exposes playback controls',
      (tester) async {
    final engine = _PageTestTtsEngine();
    final detail = _singleChapterDetail();
    await tester.pumpWidget(
      FluentApp(
        home: AudiobookPage(
          detail: detail,
          engine: engine,
          loadChapter: (index, mode) async => ChapterContent(
            chapter: detail.chapters.single,
            content: '这是一段用于测试听书功能的正文。',
            paragraphs: const <String>['这是一段用于测试听书功能的正文。'],
            mode: mode,
            translatedAvailable: false,
            imageSources: const <String>[],
            pageTranslations: const <String>[],
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('播放'), findsOneWidget);
    expect(find.text('语速'), findsOneWidget);
    expect(find.text('音量'), findsOneWidget);
    expect(find.text('朗读风格'), findsOneWidget);
    expect(find.text('自然叙述'), findsOneWidget);
    expect(find.textContaining('用于测试听书功能'), findsOneWidget);

    await tester.tap(find.byType(ComboBox<TtsSpeechStyle>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('温柔陪伴').last);
    await tester.pumpAndSettle();

    expect(engine.rates.last, closeTo(0.42, 0.001));
    expect(engine.pitches.last, closeTo(1.01, 0.001));

    await tester.tap(find.widgetWithText(FilledButton, '播放'));
    await tester.pump(const Duration(milliseconds: 100));

    expect(engine.spoken, <String>['这是一段用于测试听书功能的正文。']);
    expect(find.textContaining('本书播放完成'), findsOneWidget);
  });

  testWidgets('audiobook styles remain usable at 200 percent text scaling',
      (tester) async {
    tester.view.physicalSize = const Size(960, 640);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final detail = _singleChapterDetail();

    await tester.pumpWidget(
      FluentApp(
        home: MediaQuery(
          data: const MediaQueryData(textScaler: TextScaler.linear(2)),
          child: AudiobookPage(
            detail: detail,
            engine: _PageTestTtsEngine(),
            loadChapter: (index, mode) async => ChapterContent(
              chapter: detail.chapters.single,
              content: '这是一段用于测试听书功能的正文。',
              paragraphs: const <String>['这是一段用于测试听书功能的正文。'],
              mode: mode,
              translatedAvailable: false,
              imageSources: const <String>[],
              pageTranslations: const <String>[],
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('朗读风格'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Windows renders the v1.3.4 desktop audiobook layout',
      (tester) async {
    final detail = _singleChapterDetail();
    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(
          Brightness.light,
          platform: TargetPlatform.windows,
        ),
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: AudiobookPage(
            detail: detail,
            engine: _PageTestTtsEngine(),
            loadChapter: (index, mode) async => ChapterContent(
              chapter: detail.chapters.single,
              content: '这是一段用于测试听书功能的正文。',
              paragraphs: const <String>['这是一段用于测试听书功能的正文。'],
              mode: mode,
              translatedAvailable: false,
              imageSources: const <String>[],
              pageTranslations: const <String>[],
            ),
          ),
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 100));

    expect(
      find.byKey(const ValueKey('desktop-audiobook-page')),
      findsOneWidget,
    );
    expect(find.text('上一章'), findsOneWidget);
    expect(find.text('下一章'), findsOneWidget);
    expect(find.textContaining('用于测试听书功能'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

BookDetail _singleChapterDetail() => const BookDetail(
      book: Book(
        id: 'book-1',
        title: '测试小说',
        sourceUrl: '',
        kind: '长小说',
        language: '中文',
        status: '已下载',
        chapterCount: 1,
        translated: false,
        synopsis: '',
        lastReadChapterIndex: 1,
      ),
      author: '作者',
      synopsis: '',
      totalWords: 20,
      downloadedCount: 1,
      translatedCount: 0,
      progress: ReadingProgress(chapterIndex: 1, scrollRatio: 0),
      chapters: <Chapter>[
        Chapter(
          index: 1,
          title: '第一章',
          downloaded: true,
          translated: false,
          wordCount: 20,
          imageCount: 0,
        ),
      ],
    );

class _PageTestTtsEngine implements TtsEngine {
  final List<String> spoken = <String>[];
  final List<double> rates = <double>[];
  final List<double> pitches = <double>[];

  @override
  Future<void> initialize(String language) async {}

  @override
  Future<void> speak(String text) async => spoken.add(text);

  @override
  Future<void> pause() async {}

  @override
  Future<void> resume() async {}

  @override
  Future<void> stop() async {}

  @override
  Future<void> setRate(double value) async => rates.add(value);

  @override
  Future<void> setPitch(double value) async => pitches.add(value);

  @override
  Future<void> setVolume(double value) async {}

  @override
  Future<void> dispose() async {}
}
