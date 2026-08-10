import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';
import 'package:qingjuan/core/models/settings.dart';
import 'package:qingjuan/core/models/tts_speech_style.dart';
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

  test('legacy provider settings migrate to one OpenAI-compatible model', () {
    final settings = TranslationSettings.fromJson(<String, dynamic>{
      'defaultProvider': 'custom',
      'providers': <String, dynamic>{
        'openai': <String, dynamic>{'enabled': false},
        'custom': <String, dynamic>{
          'enabled': true,
          'baseUrl': 'https://gateway.example.test/v1',
          'apiKey': 'secret',
          'model': 'vision-model',
        },
      },
    });

    expect(settings.translationModel.enabled, isTrue);
    expect(
        settings.translationModel.baseUrl, 'https://gateway.example.test/v1');
    expect(settings.translationModel.model, 'vision-model');
    expect(settings.translationModel.supportsVision, isFalse);
    expect(settings.translationModel.toJson()['supportsVision'], isFalse);
    expect(settings.toJson().containsKey('providers'), isFalse);
    expect(settings.toJson().containsKey('defaultProvider'), isFalse);
  });

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
    expect(find.text('OpenAI 兼容接口'), findsOneWidget);
    expect(find.text('启用翻译模型'), findsOneWidget);
    expect(find.text('使用模型辅助识图'), findsOneWidget);
    expect(find.textContaining('纯文本模型也可以翻译'), findsOneWidget);
    expect(find.text('启用当前提供商'), findsNothing);
    expect(find.text('newapi'), findsNothing);
    expect(find.text('anthropic'), findsNothing);

    await tester.tap(find.byType(ComboBox<String>));
    await tester.pumpAndSettle();
    await tester.tap(
      find.text('Microsoft Xiaoxiao · 简体中文 · 女声 · 标准声线').last,
    );
    await tester.pumpAndSettle();

    expect(appState.ttsVoice, voice);

    await tester.tap(find.byType(ComboBox<TtsSpeechStyle>));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('沉浸小说').last);
    await tester.pumpAndSettle();

    expect(appState.ttsSpeechStyle, TtsSpeechStyle.immersive);

    await tester.tap(find.widgetWithText(Button, '试听'));
    await tester.pumpAndSettle();

    expect(voiceService.previewed, <TtsVoice>[voice]);
    expect(
      voiceService.previewedStyles,
      <TtsSpeechStyle>[TtsSpeechStyle.immersive],
    );
    api.close();
  });
}

class _FakeTtsVoiceService implements TtsVoiceService {
  _FakeTtsVoiceService(this.voices);

  final List<TtsVoice> voices;
  final List<TtsVoice> previewed = <TtsVoice>[];
  final List<TtsSpeechStyle> previewedStyles = <TtsSpeechStyle>[];

  @override
  Future<List<TtsVoice>> loadVoices() async => voices;

  @override
  Future<void> preview(
    TtsVoice voice, {
    TtsSpeechStyle style = TtsSpeechStyle.natural,
  }) async {
    previewed.add(voice);
    previewedStyles.add(style);
  }

  @override
  Future<void> stop() async {}

  @override
  Future<void> dispose() async {}
}
