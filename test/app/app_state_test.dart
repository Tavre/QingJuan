import 'package:fluent_ui/fluent_ui.dart' show ThemeMode;
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/core/models/tts_voice.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('AppState persists theme and normalizes backend URL', () async {
    final preferences = await SharedPreferences.getInstance();
    final state = AppState(preferences);

    await state.setThemeMode(AppThemeMode.dark);
    await state.setBackendUrl('http://192.168.1.20:19453///');

    expect(state.themeMode, AppThemeMode.dark);
    expect(state.backendUrl, 'http://192.168.1.20:19453');
    expect(preferences.getString('qingjuan.theme'), 'dark');
  });

  test('AppState changes the selected section', () async {
    final state = AppState(await SharedPreferences.getInstance());
    var themeNotifications = 0;
    state.themeModeListenable.addListener(() => themeNotifications++);

    state.selectSection(AppSection.tasks);

    expect(state.section, AppSection.tasks);
    expect(themeNotifications, 0);
  });

  test('theme listenable only notifies theme changes', () async {
    final state = AppState(await SharedPreferences.getInstance());
    var themeNotifications = 0;
    state.themeModeListenable.addListener(() => themeNotifications++);

    state.showNotice('后端已连接');
    await state.setBackendUrl('http://127.0.0.1:20000');
    await state.setThemeMode(AppThemeMode.dark);

    expect(themeNotifications, 1);
    expect(state.themeModeListenable.value, ThemeMode.dark);
  });

  test('AppState persists and restores the selected TTS voice', () async {
    const voice = TtsVoice(
      name: 'Microsoft Xiaoxiao',
      locale: 'zh-CN',
      gender: 'female',
      identifier: 'voice-xiaoxiao',
    );
    final preferences = await SharedPreferences.getInstance();
    final state = AppState(preferences);

    await state.setTtsVoice(voice);
    final restored = AppState(preferences);

    expect(restored.ttsVoice, voice);

    await restored.setTtsVoice(null);
    expect(AppState(preferences).ttsVoice, isNull);
  });

  test('AppState ignores a corrupted persisted TTS voice', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'qingjuan.ttsVoice': '{"name":42,"locale":false}',
    });

    final state = AppState(await SharedPreferences.getInstance());

    expect(state.ttsVoice, isNull);
  });
}
