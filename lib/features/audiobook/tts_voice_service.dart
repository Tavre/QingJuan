import 'package:flutter_tts/flutter_tts.dart';

import '../../core/models/tts_voice.dart';
import '../../core/models/tts_speech_style.dart';

abstract class TtsVoiceService {
  Future<List<TtsVoice>> loadVoices();
  Future<void> preview(
    TtsVoice voice, {
    TtsSpeechStyle style = TtsSpeechStyle.natural,
  });
  Future<void> stop();
  Future<void> dispose();
}

class FlutterTtsVoiceService implements TtsVoiceService {
  FlutterTtsVoiceService({FlutterTts? flutterTts})
      : _flutterTts = flutterTts ?? FlutterTts();

  final FlutterTts _flutterTts;

  @override
  Future<List<TtsVoice>> loadVoices() async {
    return parseTtsVoices(await _flutterTts.getVoices);
  }

  @override
  Future<void> preview(
    TtsVoice voice, {
    TtsSpeechStyle style = TtsSpeechStyle.natural,
  }) async {
    await _flutterTts.stop();
    await _flutterTts.awaitSpeakCompletion(true);
    final voiceResult = await _flutterTts.setVoice(voice.pluginValue);
    if (voiceResult != 1) {
      throw StateError('系统中已找不到“${voice.name}”，请刷新声音列表');
    }
    await _flutterTts.setSpeechRate(style.defaultRate);
    await _flutterTts.setPitch(style.pitchFor(voice.previewText));
    await _flutterTts.setVolume(1);
    final speakResult = await _flutterTts.speak(voice.previewText);
    if (speakResult != 1) throw StateError('设备 TTS 未能开始试听');
  }

  @override
  Future<void> stop() async {
    await _flutterTts.stop();
  }

  @override
  Future<void> dispose() async {
    await _flutterTts.stop();
  }
}
