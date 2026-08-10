import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:qingjuan/core/models/tts_voice.dart';
import 'package:qingjuan/features/audiobook/flutter_tts_engine.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('selected voice is applied instead of the language default', () async {
    final plugin = _FakeFlutterTts();
    const voice = TtsVoice(
      name: 'Microsoft Xiaoxiao',
      locale: 'zh-CN',
      gender: 'female',
      identifier: 'voice-xiaoxiao',
    );
    final engine = FlutterTtsEngine(voice: voice, flutterTts: plugin);

    await engine.initialize('en-US');

    expect(plugin.selectedVoice, voice.pluginValue);
    expect(plugin.language, isNull);
  });

  test('system default voice follows the book language', () async {
    final plugin = _FakeFlutterTts();
    final engine = FlutterTtsEngine(flutterTts: plugin);

    await engine.initialize('ja-JP');

    expect(plugin.language, 'ja-JP');
    expect(plugin.selectedVoice, isNull);
  });
}

class _FakeFlutterTts extends FlutterTts {
  String? language;
  Map<String, String>? selectedVoice;
  double? pitch;

  @override
  Future<dynamic> awaitSpeakCompletion(bool awaitCompletion) async => 1;

  @override
  Future<dynamic> setLanguage(String language) async {
    this.language = language;
    return 1;
  }

  @override
  Future<dynamic> setVoice(Map<String, String> voice) async {
    selectedVoice = voice;
    return 1;
  }

  @override
  Future<dynamic> setPitch(double pitch) async {
    this.pitch = pitch;
    return 1;
  }
}
