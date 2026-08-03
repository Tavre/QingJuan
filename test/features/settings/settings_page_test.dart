import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';
import 'package:qingjuan/core/models/tts_voice.dart';
import 'package:qingjuan/features/audiobook/tts_voice_service.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/settings/settings_page.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  testWidgets('settings lists, persists and previews Windows voices',
      (tester) async {
    const voice = TtsVoice(
      name: 'Microsoft Xiaoxiao',
      locale: 'zh-CN',
      gender: 'female',
      identifier: 'voice-xiaoxiao',
    );
    final voiceService = _FakeTtsVoiceService(<TtsVoice>[voice]);
    final preferences = await SharedPreferences.getInstance();
    final appState = AppState(preferences);
    final api = ApiClient(() => appState.backendUrl);

    await tester.pumpWidget(
      FluentApp(
        home: AppScope(
          appState: appState,
          api: api,
          backend: BackendProcessManager(api),
          library: LibraryController(api),
          sources: SourcesController(api),
          tasks: TasksController(api),
          settings: SettingsController(api),
          child: SettingsPage(voiceService: voiceService),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('已发现 1 个系统声音。选择会立即保存，并用于之后打开的听书页面。'), findsOneWidget);

    await tester.tap(find.byType(ComboBox<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Microsoft Xiaoxiao · 简体中文 · 女声').last);
    await tester.pumpAndSettle();

    expect(appState.ttsVoice, voice);

    await tester.tap(find.widgetWithText(Button, '试听'));
    await tester.pumpAndSettle();

    expect(voiceService.previewed, <TtsVoice>[voice]);
    api.close();
  });
}

class _FakeTtsVoiceService implements TtsVoiceService {
  _FakeTtsVoiceService(this.voices);

  final List<TtsVoice> voices;
  final List<TtsVoice> previewed = <TtsVoice>[];

  @override
  Future<List<TtsVoice>> loadVoices() async => voices;

  @override
  Future<void> preview(TtsVoice voice) async => previewed.add(voice);

  @override
  Future<void> stop() async {}

  @override
  Future<void> dispose() async {}
}
