import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../core/models/book.dart';
import '../../core/models/tts_speech_style.dart';

typedef ChapterLoader = Future<ChapterContent> Function(
  int chapterIndex,
  String mode,
);

enum AudiobookPlaybackState {
  idle,
  loading,
  playing,
  paused,
  stopped,
  completed,
  error,
}

abstract class TtsEngine {
  Future<void> initialize(String language);
  Future<void> speak(String text);
  Future<void> pause();
  Future<void> resume();
  Future<void> stop();
  Future<void> setRate(double value);
  Future<void> setPitch(double value);
  Future<void> setVolume(double value);
  Future<void> dispose();
}

List<String> splitTextForTts(String text, {int maxLength = 800}) {
  final limit = maxLength.clamp(8, 4000);
  final normalized = text
      .replaceAll('\r', '')
      .replaceAllMapped(
        RegExp(r'([。！？!?；;])\s*\n+'),
        (match) => match.group(1)!,
      )
      .replaceAll(RegExp(r'\s*\n+\s*'), '。')
      .replaceAll(RegExp(r'[\t ]+'), ' ')
      .trim();
  if (normalized.isEmpty) return const <String>[];

  final chunks = <String>[];
  var start = 0;
  const punctuation = '。！？!?；;，,、：:';
  while (start < normalized.length) {
    var end = (start + limit).clamp(0, normalized.length);
    if (end < normalized.length) {
      final minimumBreak = start + limit ~/ 3;
      for (var index = end - 1; index >= minimumBreak; index--) {
        if (punctuation.contains(normalized[index])) {
          end = index + 1;
          break;
        }
      }
    }
    final chunk = normalized.substring(start, end).trim();
    if (chunk.isNotEmpty) chunks.add(chunk);
    start = end;
  }
  return chunks;
}

class AudiobookController extends ChangeNotifier {
  AudiobookController({
    required this.detail,
    required this.engine,
    required this.loadChapter,
    int? initialChapterIndex,
    this.initialStyle = TtsSpeechStyle.natural,
  })  : chapterIndex = (initialChapterIndex ?? detail.progress.chapterIndex)
            .clamp(1, detail.chapters.length),
        style = initialStyle,
        rate = initialStyle.defaultRate;

  final BookDetail detail;
  final TtsEngine engine;
  final ChapterLoader loadChapter;
  final TtsSpeechStyle initialStyle;

  AudiobookPlaybackState state = AudiobookPlaybackState.idle;
  int chapterIndex;
  int chunkIndex = 0;
  List<String> chunks = const <String>[];
  String mode = 'translated';
  TtsSpeechStyle style;
  double rate;
  double volume = 1;
  String? error;

  bool _initialized = false;
  bool _disposed = false;
  int _playbackToken = 0;

  bool get isPlaying => state == AudiobookPlaybackState.playing;
  bool get isPaused => state == AudiobookPlaybackState.paused;
  bool get isLoading => state == AudiobookPlaybackState.loading;

  Chapter get currentChapter => detail.chapters.firstWhere(
        (chapter) => chapter.index == chapterIndex,
        orElse: () => detail.chapters.first,
      );

  String get currentText {
    if (chunks.isEmpty) return '';
    return chunks[chunkIndex.clamp(0, chunks.length - 1)];
  }

  double get chapterProgress {
    if (chunks.isEmpty) return 0;
    if (state == AudiobookPlaybackState.completed) return 100;
    return (chunkIndex / chunks.length * 100).clamp(0, 100);
  }

  Future<void> initialize() async {
    if (_initialized && state != AudiobookPlaybackState.error) return;
    _initialized = true;
    try {
      await engine.initialize(_languageCode(detail.book.language));
      await engine.setRate(rate);
      await engine.setPitch(style.basePitch);
      await engine.setVolume(volume);
      await _loadCurrentChapter();
    } catch (exception) {
      _setError(exception);
    }
  }

  Future<void> play() async {
    if (!_initialized) await initialize();
    if (state == AudiobookPlaybackState.error || chunks.isEmpty) return;
    if (isPaused) {
      await engine.resume();
      state = AudiobookPlaybackState.playing;
      _notify();
      return;
    }
    if (state == AudiobookPlaybackState.completed) chunkIndex = 0;
    final token = ++_playbackToken;
    state = AudiobookPlaybackState.playing;
    error = null;
    _notify();

    try {
      while (token == _playbackToken && !_disposed) {
        while (chunkIndex < chunks.length && token == _playbackToken) {
          final chunk = chunks[chunkIndex];
          await engine.setRate(style.rateFor(chunk, rate));
          await engine.setPitch(style.pitchFor(chunk));
          await engine.speak(chunk);
          if (token != _playbackToken || _disposed) return;
          await Future<void>.delayed(style.pauseAfter(chunk));
          if (token != _playbackToken || _disposed) return;
          chunkIndex += 1;
          _notify();
        }
        if (token != _playbackToken || _disposed) return;
        final nextChapter = _adjacentChapter(1);
        if (nextChapter == null) {
          state = AudiobookPlaybackState.completed;
          chunkIndex = chunks.isEmpty ? 0 : chunks.length - 1;
          _notify();
          return;
        }
        chapterIndex = nextChapter.index;
        chunkIndex = 0;
        await _loadCurrentChapter();
        if (token != _playbackToken || _disposed || chunks.isEmpty) return;
        state = AudiobookPlaybackState.playing;
        _notify();
      }
    } catch (exception) {
      if (token == _playbackToken) _setError(exception);
    }
  }

  Future<void> pause() async {
    if (!isPlaying) return;
    await engine.pause();
    state = AudiobookPlaybackState.paused;
    _notify();
  }

  Future<void> stop() async {
    _playbackToken += 1;
    await engine.stop();
    chunkIndex = 0;
    state = AudiobookPlaybackState.stopped;
    _notify();
  }

  Future<void> moveChapter(int delta, {bool autoplay = false}) async {
    final target = _adjacentChapter(delta);
    if (target == null) return;
    _playbackToken += 1;
    await engine.stop();
    chapterIndex = target.index;
    chunkIndex = 0;
    await _loadCurrentChapter();
    if (autoplay && state != AudiobookPlaybackState.error) {
      await play();
    }
  }

  Future<void> setMode(String value) async {
    if (value == mode) return;
    _playbackToken += 1;
    await engine.stop();
    mode = value;
    chunkIndex = 0;
    await _loadCurrentChapter();
  }

  Future<void> setRate(double value) async {
    rate = value.clamp(0.2, 1);
    _notify();
    await engine.setRate(rate);
  }

  Future<void> setStyle(TtsSpeechStyle value) async {
    if (style == value) return;
    style = value;
    rate = value.defaultRate;
    _notify();
    await engine.setRate(rate);
    await engine.setPitch(value.basePitch);
  }

  Future<void> setVolume(double value) async {
    volume = value.clamp(0, 1);
    _notify();
    await engine.setVolume(volume);
  }

  Future<void> _loadCurrentChapter() async {
    state = AudiobookPlaybackState.loading;
    error = null;
    _notify();
    try {
      final content = await loadChapter(chapterIndex, mode);
      final text = content.content.trim().isNotEmpty
          ? content.content
          : content.paragraphs.join('\n');
      chunks = splitTextForTts(text);
      if (chunks.isEmpty) {
        throw StateError('当前章节没有可朗读的文字内容');
      }
      chunkIndex = chunkIndex.clamp(0, chunks.length - 1);
      state = AudiobookPlaybackState.idle;
      _notify();
    } catch (exception) {
      _setError(exception);
    }
  }

  Chapter? _adjacentChapter(int delta) {
    final currentPosition = detail.chapters.indexWhere(
      (chapter) => chapter.index == chapterIndex,
    );
    final nextPosition = currentPosition + delta;
    if (currentPosition < 0 ||
        nextPosition < 0 ||
        nextPosition >= detail.chapters.length) {
      return null;
    }
    return detail.chapters[nextPosition];
  }

  void _setError(Object exception) {
    error = '$exception';
    state = AudiobookPlaybackState.error;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  String _languageCode(String language) => switch (language) {
        '英文' => 'en-US',
        '日文' => 'ja-JP',
        _ => 'zh-CN',
      };

  @override
  void dispose() {
    _disposed = true;
    _playbackToken += 1;
    unawaited(engine.stop());
    unawaited(engine.dispose());
    super.dispose();
  }
}
