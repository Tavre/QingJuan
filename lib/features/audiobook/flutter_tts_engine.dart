import 'package:flutter_tts/flutter_tts.dart';

import '../../core/models/tts_voice.dart';
import 'audiobook_controller.dart';

class FlutterTtsEngine implements TtsEngine {
  FlutterTtsEngine({this.voice, FlutterTts? flutterTts})
      : _flutterTts = flutterTts ?? FlutterTts();

  final FlutterTts _flutterTts;
  final TtsVoice? voice;

  @override
  Future<void> initialize(String language) async {
    await _flutterTts.awaitSpeakCompletion(true);
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
    final result = await _flutterTts.speak(text);
    if (result != 1) throw StateError('Windows TTS 未能开始朗读');
  }

  @override
  Future<void> pause() async {
    await _flutterTts.pause();
  }

  @override
  Future<void> resume() async {
    await _flutterTts.speak('');
  }

  @override
  Future<void> stop() async {
    await _flutterTts.stop();
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
    await _flutterTts.stop();
  }
}
