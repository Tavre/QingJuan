import 'package:fluent_ui/fluent_ui.dart' show ThemeMode;
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/core/backend/connection_secret_store.dart';
import 'package:qingjuan/core/models/tts_speech_style.dart';
import 'package:qingjuan/core/models/tts_voice.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('AppState starts in settings until a server is configured', () async {
    final preferences = await SharedPreferences.getInstance();
    final state = AppState(preferences);

    expect(state.section, AppSection.settings);
    expect(state.backendUrl, isEmpty);
    expect(state.hasBackendConnection, isFalse);
  });

  test('server connection stores token outside SharedPreferences', () async {
    final preferences = await SharedPreferences.getInstance();
    final secrets = _MemorySecretStore();
    final state = AppState(preferences, secretStore: secrets);

    await state.setBackendConnection(
      url: 'https://qingjuan.example.test///',
      token: 'remote-secret-token',
    );

    expect(state.backendUrl, 'https://qingjuan.example.test');
    expect(state.hasBackendConnection, isTrue);
    expect(secrets.token, 'remote-secret-token');
    expect(preferences.getString('qingjuan.backendToken'), isNull);
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
    await state.setThemeMode(AppThemeMode.dark);

    expect(themeNotifications, 1);
    expect(state.themeModeListenable.value, ThemeMode.dark);
  });

  test('section listenable ignores unrelated application updates', () async {
    final state = AppState(await SharedPreferences.getInstance());
    var sectionNotifications = 0;
    state.sectionListenable.addListener(() => sectionNotifications++);

    state.showNotice('后端已连接');
    state.selectSection(AppSection.tasks);

    expect(sectionNotifications, 1);
    expect(state.sectionListenable.value, AppSection.tasks);
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

  test('AppState persists and restores the TTS speech style', () async {
    final preferences = await SharedPreferences.getInstance();
    final state = AppState(preferences);

    await state.setTtsSpeechStyle(TtsSpeechStyle.immersive);

    expect(
      AppState(preferences).ttsSpeechStyle,
      TtsSpeechStyle.immersive,
    );
  });

  test('AppState persists reader controls and clamps the font size', () async {
    final preferences = await SharedPreferences.getInstance();
    final state = AppState(preferences);

    await state.setReaderFlowMode(ReaderFlowMode.continuous);
    await state.setReaderPaletteMode(ReaderPaletteMode.eyeCare);
    await state.setReaderPageAnimation(ReaderPageAnimation.fade);
    await state.setReaderLineSpacing(ReaderLineSpacing.relaxed);
    await state.setReaderFontSize(42);
    await state.setVolumeKeyReadingEnabled(true);
    final restored = AppState(preferences);

    expect(restored.readerFlowMode, ReaderFlowMode.continuous);
    expect(restored.readerPaletteMode, ReaderPaletteMode.eyeCare);
    expect(restored.readerPageAnimation, ReaderPageAnimation.fade);
    expect(restored.readerLineSpacing, ReaderLineSpacing.relaxed);
    expect(restored.readerFontSize, 30);
    expect(restored.volumeKeyReadingEnabled, isTrue);
  });
}

class _MemorySecretStore implements ConnectionSecretStore {
  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> readToken() async => token;

  @override
  Future<void> writeToken(String token) async => this.token = token;
}
