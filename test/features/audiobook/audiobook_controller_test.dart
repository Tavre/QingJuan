import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/book.dart';
import 'package:qingjuan/features/audiobook/audiobook_controller.dart';

void main() {
  test('splitTextForTts keeps content and respects chunk size', () {
    const text = '第一句。第二句比较长，需要继续朗读！第三句？\n第四段。';

    final chunks = splitTextForTts(text, maxLength: 12);

    expect(chunks, isNotEmpty);
    expect(chunks.every((chunk) => chunk.length <= 12), isTrue);
    expect(chunks.join(), text.replaceAll('\n', ''));
  });

  test('controller reads chapter chunks and continues to next chapter',
      () async {
    final engine = _FakeTtsEngine();
    final controller = AudiobookController(
      detail: _detail(),
      engine: engine,
      loadChapter: (chapterIndex, mode) async => _content(
        chapterIndex,
        chapterIndex == 1 ? '第一章正文。' : '第二章正文。',
        mode,
      ),
    );

    await controller.initialize();
    await controller.play();

    expect(engine.language, 'zh-CN');
    expect(engine.spoken, <String>['第一章正文。', '第二章正文。']);
    expect(controller.chapterIndex, 2);
    expect(controller.state, AudiobookPlaybackState.completed);
  });

  test('controller pauses active speech without advancing chapter', () async {
    final engine = _FakeTtsEngine(blockSpeech: true);
    final controller = AudiobookController(
      detail: _detail(),
      engine: engine,
      loadChapter: (chapterIndex, mode) async =>
          _content(chapterIndex, '等待暂停的正文。', mode),
    );
    await controller.initialize();

    final playing = controller.play();
    await Future<void>.delayed(Duration.zero);
    await controller.pause();

    expect(engine.pauseCount, 1);
    expect(controller.chapterIndex, 1);
    expect(controller.state, AudiobookPlaybackState.paused);

    await controller.play();
    await playing;
    expect(engine.resumeCount, 1);
  });
}

BookDetail _detail() => const BookDetail(
      book: Book(
        id: 'book-1',
        title: '测试小说',
        sourceUrl: 'https://example.com/book-1',
        kind: '长小说',
        language: '中文',
        status: '已下载',
        chapterCount: 2,
        translated: false,
        synopsis: '',
        lastReadChapterIndex: 1,
      ),
      author: '作者',
      synopsis: '',
      totalWords: 20,
      downloadedCount: 2,
      translatedCount: 0,
      progress: ReadingProgress(chapterIndex: 1, scrollRatio: 0),
      chapters: <Chapter>[
        Chapter(
          index: 1,
          title: '第一章',
          downloaded: true,
          translated: false,
          wordCount: 10,
          imageCount: 0,
        ),
        Chapter(
          index: 2,
          title: '第二章',
          downloaded: true,
          translated: false,
          wordCount: 10,
          imageCount: 0,
        ),
      ],
    );

ChapterContent _content(int index, String text, String mode) => ChapterContent(
      chapter: Chapter(
        index: index,
        title: '第$index章',
        downloaded: true,
        translated: false,
        wordCount: text.length,
        imageCount: 0,
      ),
      content: text,
      paragraphs: <String>[text],
      mode: mode,
      translatedAvailable: false,
      imageSources: const <String>[],
      pageTranslations: const <String>[],
    );

class _FakeTtsEngine implements TtsEngine {
  _FakeTtsEngine({this.blockSpeech = false});

  final bool blockSpeech;
  final List<String> spoken = <String>[];
  Completer<void>? _speechCompleter;
  String? language;
  int pauseCount = 0;
  int resumeCount = 0;
  bool _didBlock = false;

  @override
  Future<void> initialize(String language) async {
    this.language = language;
  }

  @override
  Future<void> speak(String text) async {
    spoken.add(text);
    if (!blockSpeech || _didBlock) return;
    _didBlock = true;
    _speechCompleter = Completer<void>();
    await _speechCompleter!.future;
  }

  @override
  Future<void> pause() async {
    pauseCount += 1;
  }

  @override
  Future<void> resume() async {
    resumeCount += 1;
    _speechCompleter?.complete();
  }

  @override
  Future<void> stop() async {
    if (_speechCompleter?.isCompleted == false) _speechCompleter?.complete();
  }

  @override
  Future<void> setRate(double value) async {}

  @override
  Future<void> setVolume(double value) async {}

  @override
  Future<void> dispose() async {}
}
