import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_scope.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/backend/local_backend_process.dart';
import 'package:qingjuan/core/models/settings.dart';
import 'package:qingjuan/core/models/tts_speech_style.dart';
import 'package:qingjuan/core/models/tts_voice.dart';
import 'package:qingjuan/features/audiobook/tts_voice_service.dart';
import 'package:qingjuan/features/library/library_controller.dart';
import 'package:qingjuan/features/settings/settings_controller.dart';
import 'package:qingjuan/features/settings/settings_page.dart';
import 'package:qingjuan/features/sources/sources_controller.dart';
import 'package:qingjuan/features/tasks/tasks_controller.dart';
import 'package:qingjuan/shared/responsive.dart';
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

  testWidgets('settings lists, persists and previews device voices',
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
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: AppScope(
            appState: appState,
            api: api,
            backend: BackendConnectionManager(api, isConfigured: () => false),
            library: LibraryController(api),
            sources: SourcesController(api),
            tasks: TasksController(api),
            settings: SettingsController(api),
            child: SettingsPage(voiceService: voiceService),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Windows的浅色与深色设置'), findsOneWidget);
    expect(find.byIcon(FluentIcons.system), findsOneWidget);
    expect(find.byIcon(FluentIcons.brightness), findsOneWidget);
    expect(find.byIcon(FluentIcons.clear_night), findsOneWidget);
    expect(find.byIcon(FluentIcons.cell_phone), findsNothing);
    final systemIcon = tester.widget<Icon>(
      find.descendant(
        of: find.byKey(const ValueKey('theme-mode-system')),
        matching: find.byType(Icon),
      ),
    );
    expect(systemIcon.semanticLabel, '跟随系统外观');
    expect(find.text('已发现 1 个系统声音。选择会立即保存，并用于之后打开的听书页面。'), findsOneWidget);
    expect(find.text('由后端管理界面统一配置'), findsOneWidget);
    expect(find.text('等待服务端模型自检'), findsOneWidget);
    expect(find.text('重新检测模型'), findsOneWidget);
    expect(find.text('启用翻译模型'), findsNothing);
    expect(find.text('使用模型辅助识图'), findsNothing);
    expect(find.text('API 密钥'), findsNothing);
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

    await tester.tap(find.byType(ComboBox<String>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('跟随系统默认声音').last);
    await tester.pumpAndSettle();

    expect(appState.ttsVoice, isNull);
    api.close();
  });

  testWidgets('Windows settings can choose local or Linux remote backend',
      (tester) async {
    final preferences = await SharedPreferences.getInstance();
    final appState = AppState(preferences, localBackendSupported: true);
    final api = ApiClient(() => appState.backendUrl);
    Uri? openedModelSettings;
    final backend = BackendConnectionManager(
      api,
      isConfigured: () => appState.hasBackendConnection,
      isLocal: () => appState.connectionMode == BackendConnectionMode.local,
      localBackend: WindowsLocalBackendLifecycle(
        isWindows: () => true,
        openUri: (uri) async => openedModelSettings = uri,
      ),
    )..status = BackendStatus.ready;

    await tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: AppScope(
            appState: appState,
            api: api,
            backend: backend,
            library: LibraryController(api),
            sources: SourcesController(api),
            tasks: TasksController(api),
            settings: SettingsController(api),
            child: SettingsPage(
              voiceService: _FakeTtsVoiceService(const <TtsVoice>[]),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('本机模式使用固定回环地址'), findsOneWidget);
    expect(find.textContaining(AppState.defaultLocalBackendUrl), findsWidgets);
    final openModelSettings =
        find.byKey(const ValueKey('open-local-model-settings'));
    await tester.ensureVisible(openModelSettings);
    await tester.pumpAndSettle();
    await tester.tap(openModelSettings);
    await tester.pumpAndSettle();
    expect(
      openedModelSettings,
      Uri.parse('http://127.0.0.1:19453/admin/#settings'),
    );

    final modeSelector = find.byType(ComboBox<BackendConnectionMode>);
    await tester.ensureVisible(modeSelector);
    await tester.pumpAndSettle();
    await tester.tap(modeSelector);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Linux 远程后端').last);
    await tester.pumpAndSettle();

    expect(find.text('FastAPI 地址'), findsOneWidget);
    expect(find.text('连接 Token'), findsOneWidget);
    expect(find.text('Linux 连接参数独立保存'), findsOneWidget);
    expect(find.textContaining('远程失败不会回退本机'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('linux-backend-url')),
      'https://draft.example.test',
    );
    await tester.enterText(
      find.byKey(const ValueKey('linux-backend-token')),
      'draft-token',
    );

    await tester.tap(modeSelector);
    await tester.pumpAndSettle();
    await tester.tap(find.text('本机后端').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('linux-backend-url')), findsNothing);

    await tester.tap(modeSelector);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Linux 远程后端').last);
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<TextBox>(find.byKey(const ValueKey('linux-backend-url')))
          .controller!
          .text,
      'https://draft.example.test',
    );
    expect(
      tester
          .widget<TextBox>(find.byKey(const ValueKey('linux-backend-token')))
          .controller!
          .text,
      'draft-token',
    );
    await backend.dispose();
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
