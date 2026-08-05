import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/tts_voice.dart';

void main() {
  test('parseTtsVoices filters invalid entries, removes duplicates and sorts',
      () {
    final voices = parseTtsVoices(<Object?>[
      <Object?, Object?>{
        'name': 'Microsoft Yunxi',
        'locale': 'zh-CN',
        'gender': 'male',
        'identifier': 'voice-yunxi',
      },
      <Object?, Object?>{
        'name': 'Microsoft Xiaoxiao',
        'locale': 'zh-CN',
        'gender': 'female',
        'identifier': 'voice-xiaoxiao',
      },
      <Object?, Object?>{
        'name': 'Microsoft Xiaoxiao',
        'locale': 'zh-CN',
        'gender': 'female',
        'identifier': 'voice-xiaoxiao',
      },
      <Object?, Object?>{'name': '', 'locale': 'en-US'},
      'invalid',
    ]);

    expect(voices, hasLength(2));
    expect(voices.first.name, 'Microsoft Xiaoxiao');
    expect(voices.last.genderLabel, '男声');
    expect(voices.first.pluginValue, <String, String>{
      'name': 'Microsoft Xiaoxiao',
      'locale': 'zh-CN',
    });
  });

  test('TtsVoice JSON round-trip preserves the selected system voice', () {
    const voice = TtsVoice(
      name: 'Microsoft Xiaoxiao',
      locale: 'zh-CN',
      gender: 'female',
      identifier: 'voice-xiaoxiao',
    );

    expect(TtsVoice.fromJson(voice.toJson()), voice);
    expect(voice.localeLabel, '简体中文');
    expect(voice.description, '简体中文 · 女声');
  });
}
