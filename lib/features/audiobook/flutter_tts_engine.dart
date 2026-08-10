import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';

import '../../core/models/tts_voice.dart';
import 'audiobook_controller.dart';

class FlutterTtsEngine implements TtsEngine {
  FlutterTtsEngine({this.voice, FlutterTts? flutterTts})
      : _flutterTts = flutterTts ?? FlutterTts();

  final FlutterTts _flutterTts;
  final TtsVoice? voice;
  Completer<void>? _speechCompletion;
  bool _disposed = false;

  @override
  Future<void> initialize(String language) async {
    // flutter_tts 4.2.5 的 Windows awaitSpeakCompletion 路径会把原生
    // MethodResult 指针交给后台回调。停止、退出或快速切章时容易形成竞态。
    // 改用插件的完成/取消事件等待，避开该原生生命周期问题。
    await _flutterTts.awaitSpeakCompletion(false);
    _flutterTts.setCompletionHandler(_completeSpeech);
    _flutterTts.setCancelHandler(_completeSpeech);
    _flutterTts.setErrorHandler(
      (message) => _completeSpeechError(
        StateError('Windows TTS 播放失败：${message.toString()}'),
      ),
    );
    if (voice == null) {
      final languageResult = await _flutterTts.setLanguage(language);
      if (languageResult != 1) {
        throw StateError('Windows 未安装 $language 对应的系统语音');
      }
    } else {
      final voiceResult = await _flutterTts.setVoice(voice!.pluginValue);
      if (voiceResult != 1) {
        throw StateError('已选声线“${voice!.name}”不可用，请前往设置重新选择');
      }
    }
    await _flutterTts.setPitch(1);
  }

  @override
  Future<void> speak(String text) async {
    if (_disposed) throw StateError('Windows TTS 已关闭');
    if (_speechCompletion?.isCompleted == false) {
      throw StateError('Windows TTS 正在处理上一段文字');
    }
    final completion = Completer<void>();
    _speechCompletion = completion;
    try {
      final result = await _flutterTts.speak(text);
      if (result != 1) {
        _completeSpeech();
        throw StateError('Windows TTS 未能开始朗读');
      }
      await completion.future;
    } catch (_) {
      _completeSpeech();
      rethrow;
    } finally {
      if (identical(_speechCompletion, completion)) {
        _speechCompletion = null;
      }
    }
  }

  @override
  Future<void> pause() async {
    final result = await _flutterTts.pause();
    if (result != 1) throw StateError('Windows TTS 未能暂停朗读');
  }

  @override
  Future<void> resume() async {
    final result = await _flutterTts.speak('');
    if (result != 1) throw StateError('Windows TTS 未能继续朗读');
  }

  @override
  Future<void> stop() async {
    if (_disposed) {
      _completeSpeech();
      return;
    }
    try {
      final result = await _flutterTts.stop();
      if (result != 1) throw StateError('Windows TTS 未能停止朗读');
    } finally {
      _completeSpeech();
    }
  }

  @override
  Future<void> setRate(double value) async {
    await _flutterTts.setSpeechRate(value);
  }

  @override
  Future<void> setPitch(double value) async {
    await _flutterTts.setPitch(value);
  }

  @override
  Future<void> setVolume(double value) async {
    await _flutterTts.setVolume(value);
  }

  @override
  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    try {
      await _flutterTts.stop();
    } finally {
      _completeSpeech();
    }
  }

  void _completeSpeech() {
    final completion = _speechCompletion;
    if (completion != null && !completion.isCompleted) completion.complete();
  }

  void _completeSpeechError(Object error) {
    final completion = _speechCompletion;
    if (completion != null && !completion.isCompleted) {
      completion.completeError(error);
    }
  }
}
