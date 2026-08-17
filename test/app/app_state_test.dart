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

    await state.saveRemoteBackendConnection(
      url: 'https://qingjuan.example.test///',
      token: 'remote-secret-token',
    );
    await state.selectBackendMode(BackendConnectionMode.remote);

    expect(state.backendUrl, 'https://qingjuan.example.test');
    expect(state.hasBackendConnection, isTrue);
    expect(secrets.token, 'remote-secret-token');
    expect(preferences.getString('qingjuan.backendToken'), isNull);
    expect(
      preferences.getString('qingjuan.backend.remote.url'),
      'https://qingjuan.example.test',
    );
    expect(preferences.getString('qingjuan.backendUrl'), isNull);
  });

  test('fresh Windows state defaults to the local backend', () async {
    final state = AppState(
      await SharedPreferences.getInstance(),
      localBackendSupported: true,
    );

    expect(state.connectionMode, BackendConnectionMode.local);
    expect(state.backendUrl, AppState.defaultLocalBackendUrl);
    expect(state.backendToken, isEmpty);
    expect(state.hasBackendConnection, isTrue);
    expect(state.section, AppSection.library);
  });

  test('v1.4 Windows remote settings remain remote after upgrade', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'qingjuan.backendUrl': 'https://qingjuan.example.test/',
    });

    final state = AppState(
      await SharedPreferences.getInstance(),
      initialRemoteBackendToken: 'saved-token',
      localBackendSupported: true,
    );

    expect(state.connectionMode, BackendConnectionMode.remote);
    expect(state.backendUrl, 'https://qingjuan.example.test');
    expect(state.backendToken, 'saved-token');
  });

  test('Android ignores a persisted local mode', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'qingjuan.backendMode': 'local',
      'qingjuan.backendUrl': AppState.defaultLocalBackendUrl,
    });

    final state = AppState(await SharedPreferences.getInstance());

    expect(state.connectionMode, BackendConnectionMode.remote);
    expect(state.backendUrl, isEmpty);
    expect(state.hasBackendConnection, isFalse);
    expect(state.section, AppSection.settings);
  });

  test('switching to local preserves the secure remote connection', () async {
    final preferences = await SharedPreferences.getInstance();
    final secrets = _MemorySecretStore();
    final state = AppState(
      preferences,
      secretStore: secrets,
      localBackendSupported: true,
    );

    await state.saveRemoteBackendConnection(
      url: 'https://qingjuan.example.test',
      token: 'remote-secret-token',
    );
    await state.selectBackendMode(BackendConnectionMode.remote);
    await state.selectBackendMode(BackendConnectionMode.local);

    expect(state.connectionMode, BackendConnectionMode.local);
    expect(state.backendUrl, AppState.defaultLocalBackendUrl);
    expect(state.backendToken, isEmpty);
    expect(state.remoteBackendUrl, 'https://qingjuan.example.test');
    expect(state.remoteBackendToken, 'remote-secret-token');
    expect(state.remoteBackendConnection.isConfigured, isTrue);
    expect(AppState.localBackendConnection.token, isEmpty);
    expect(secrets.token, 'remote-secret-token');
  });

  test('remote mode hides client plugin management and leaves its page',
      () async {
    final state = AppState(
      await SharedPreferences.getInstance(),
      localBackendSupported: true,
    );
    state.selectSection(AppSection.plugins);

    expect(state.clientPluginManagementAvailable, isTrue);
    expect(state.section, AppSection.plugins);

    await state.selectBackendMode(BackendConnectionMode.remote);

    expect(state.clientPluginManagementAvailable, isFalse);
    expect(state.section, AppSection.settings);
    state.selectSection(AppSection.plugins);
    expect(state.section, AppSection.settings);
  });

  test('dedicated Linux profile wins over a stale v1.4 URL', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'qingjuan.backendMode': 'remote',
      'qingjuan.backendUrl': 'https://legacy.example.test',
      'qingjuan.backend.remote.url': 'https://current.example.test/',
    });

    final state = AppState(
      await SharedPreferences.getInstance(),
      initialRemoteBackendToken: 'saved-token',
      localBackendSupported: true,
    );

    expect(state.remoteBackendUrl, 'https://current.example.test');
    expect(state.backendUrl, 'https://current.example.test');
    expect(state.backendToken, 'saved-token');
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
