import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../core/backend/backend_process_manager.dart';
import '../../core/models/settings.dart';
import '../../core/models/tts_speech_style.dart';
import '../../core/models/tts_voice.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../audiobook/tts_voice_service.dart';
import 'widgets/settings_section_card.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({this.voiceService, super.key});

  final TtsVoiceService? voiceService;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static const _systemVoiceKey = '__system_default__';

  final _backendController = TextEditingController();
  final _backendTokenController = TextEditingController();
  final _baseUrlController = TextEditingController();
  final _apiKeyController = TextEditingController();
  final _modelController = TextEditingController();
  final _promptController = TextEditingController();
  final _autoTranslateController = TextEditingController();
  final _concurrencyController = TextEditingController();
  bool _translationModelEnabled = false;
  bool _translationModelSupportsVision = false;
  bool _clearTranslationApiKey = false;
  BackendConnectionMode _connectionMode = BackendConnectionMode.local;
  bool _initialized = false;
  late final TtsVoiceService _voiceService;
  List<TtsVoice> _voices = const <TtsVoice>[];
  bool _voicesLoading = true;
  String? _voiceError;
  String? _previewingVoiceKey;

  @override
  void initState() {
    super.initState();
    _voiceService = widget.voiceService ?? FlutterTtsVoiceService();
    unawaited(_loadVoices());
  }

  Future<void> _loadVoices() async {
    if (mounted) {
      setState(() {
        _voicesLoading = true;
        _voiceError = null;
      });
    }
    try {
      final voices = await _voiceService.loadVoices();
      if (!mounted) return;
      setState(() {
        _voices = voices;
        _voicesLoading = false;
        if (voices.isEmpty) {
          _voiceError = 'Windows 当前没有可用的系统声音，请先安装语音包。';
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _voicesLoading = false;
        _voiceError = '$error';
      });
    }
  }

  Future<void> _selectVoice(AppState appState, String? key) async {
    if (key == null) return;
    final voice = key == _systemVoiceKey
        ? null
        : _voices.cast<TtsVoice?>().firstWhere(
              (item) => item?.stableKey == key,
              orElse: () => appState.ttsVoice,
            );
    await _voiceService.stop();
    await appState.setTtsVoice(voice);
  }

  Future<void> _previewVoice(
    TtsVoice voice,
    TtsSpeechStyle style,
  ) async {
    setState(() {
      _previewingVoiceKey = voice.stableKey;
      _voiceError = null;
    });
    try {
      await _voiceService.preview(voice, style: style);
    } catch (error) {
      if (mounted) setState(() => _voiceError = '$error');
    } finally {
      if (mounted) setState(() => _previewingVoiceKey = null);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _initialized = true;
    final scope = AppScope.of(context);
    _backendController.text = scope.appState.backendUrl;
    _backendTokenController.text = scope.appState.backendToken;
    _connectionMode = scope.appState.connectionMode;
    _loadModel(scope.settings.value);
  }

  void _loadModel(TranslationSettings settings) {
    final translationModel = settings.translationModel;
    _baseUrlController.text = translationModel.baseUrl;
    _apiKeyController.text = translationModel.apiKey;
    _modelController.text = translationModel.model;
    _promptController.text = settings.systemPrompt;
    _autoTranslateController.text = '${settings.autoTranslateNextChapters}';
    _concurrencyController.text = '${settings.downloadConcurrency}';
    _translationModelEnabled = translationModel.enabled;
    _translationModelSupportsVision = translationModel.supportsVision;
    _clearTranslationApiKey = false;
  }

  TranslationSettings _commitTranslationModel(TranslationSettings settings) {
    final translationModel = TranslationModelSettings(
      enabled: _translationModelEnabled,
      baseUrl: _baseUrlController.text.trim(),
      apiKey: _apiKeyController.text.trim(),
      model: _modelController.text.trim(),
      supportsVision: _translationModelSupportsVision,
      apiKeyConfigured: settings.translationModel.apiKeyConfigured,
      clearApiKey: _clearTranslationApiKey,
    );
    return settings.copyWith(translationModel: translationModel);
  }

  Future<void> _save() async {
    final scope = AppScope.of(context);
    var settings = _commitTranslationModel(scope.settings.value);
    settings = settings.copyWith(
      systemPrompt: _promptController.text,
      autoTranslateNextChapters:
          int.tryParse(_autoTranslateController.text) ?? 2,
      downloadConcurrency: int.tryParse(_concurrencyController.text) ?? 4,
    );
    scope.settings.update(settings);
    try {
      final backendUrl = _backendController.text.trim();
      final backendToken = _backendTokenController.text.trim();
      final connectionChanged =
          scope.appState.connectionMode != _connectionMode ||
              scope.appState.backendUrl.replaceAll(RegExp(r'/+$'), '') !=
                  backendUrl.replaceAll(RegExp(r'/+$'), '');
      if (_connectionMode == BackendConnectionMode.remote) {
        _validateRemoteBackendUrl(backendUrl);
        if (backendToken.isEmpty) {
          throw StateError('远程后端必须填写连接 Token');
        }
        await scope.api.testConnection(
          baseUrl: backendUrl,
          token: backendToken,
        );
      }
      await scope.appState.setBackendConnection(
        mode: _connectionMode,
        url: backendUrl,
        token: backendToken,
      );
      await scope.backend.ensureReady();
      if (scope.backend.status != BackendStatus.ready) {
        throw StateError(scope.backend.message);
      }
      if (connectionChanged) {
        scope.library.resetForBackendSwitch();
        scope.sources.resetForBackendSwitch();
        scope.tasks.resetForBackendSwitch();
      }
      await scope.settings.save();
      await Future.wait<void>(<Future<void>>[
        scope.library.load(),
        scope.sources.load(),
        scope.tasks.load(),
      ]);
      if (mounted) {
        displayInfoBar(
          context,
          builder: (_, __) => const InfoBar(
            title: Text('设置已保存'),
            severity: InfoBarSeverity.success,
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        displayInfoBar(
          context,
          builder: (_, __) => InfoBar(
            title: const Text('保存失败'),
            content: Text('$error'),
            severity: InfoBarSeverity.error,
          ),
        );
      }
    }
  }

  @override
  void dispose() {
    unawaited(_voiceService.dispose());
    _backendController.dispose();
    _backendTokenController.dispose();
    _baseUrlController.dispose();
    _apiKeyController.dispose();
    _modelController.dispose();
    _promptController.dispose();
    _autoTranslateController.dispose();
    _concurrencyController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final settings = scope.settings;
    final compact = windowClassOf(context) == WindowClass.compact;
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[scope.appState, settings]),
      builder: (context, _) => PageFrame(
        title: '设置',
        subtitle: '管理界面主题、听书声音、后端连接和翻译服务。',
        command: FilledButton(
          onPressed: settings.saving ? null : _save,
          child: const Text('保存设置'),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const SectionTitle('界面主题'),
            SettingsSectionCard(
              icon: FluentIcons.color,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    '外观模式',
                    style: FluentTheme.of(context)
                        .typography
                        .bodyLarge
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '跟随系统可自动响应 Windows 的浅色与深色设置。',
                    style: FluentTheme.of(context).typography.caption,
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: AppThemeMode.values.map((mode) {
                      final label = switch (mode) {
                        AppThemeMode.system => '跟随系统',
                        AppThemeMode.light => '浅色',
                        AppThemeMode.dark => '深色',
                      };
                      return ToggleButton(
                        checked: scope.appState.themeMode == mode,
                        onChanged: (_) => scope.appState.setThemeMode(mode),
                        child: Text(label),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 30),
            const SectionTitle('听书声音'),
            SettingsSectionCard(
              icon: FluentIcons.volume3,
              child: _buildVoiceSettings(scope.appState, compact),
            ),
            const SizedBox(height: 30),
            const SectionTitle('后端连接'),
            SettingsSectionCard(
              icon: FluentIcons.plug_connected,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  InfoLabel(
                    label: '连接模式',
                    child: ComboBox<BackendConnectionMode>(
                      value: _connectionMode,
                      isExpanded: true,
                      items: const <ComboBoxItem<BackendConnectionMode>>[
                        ComboBoxItem<BackendConnectionMode>(
                          value: BackendConnectionMode.local,
                          child: Text('本机后端'),
                        ),
                        ComboBoxItem<BackendConnectionMode>(
                          value: BackendConnectionMode.remote,
                          child: Text('Linux 远程后端'),
                        ),
                      ],
                      onChanged: (value) {
                        if (value != null) {
                          setState(() => _connectionMode = value);
                        }
                      },
                    ),
                  ),
                  const SizedBox(height: 12),
                  InfoLabel(
                    label: 'FastAPI 地址',
                    child: TextBox(
                      controller: _backendController,
                      placeholder: 'http://127.0.0.1:19453',
                    ),
                  ),
                  if (_connectionMode ==
                      BackendConnectionMode.remote) ...<Widget>[
                    const SizedBox(height: 12),
                    InfoLabel(
                      label: '连接 Token',
                      child: TextBox(
                        controller: _backendTokenController,
                        obscureText: true,
                        placeholder: '由 Linux 服务端管理员生成',
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  Text(
                    _connectionMode == BackendConnectionMode.local
                        ? '本机模式会检查并按需启动随包后端。'
                        : '远程模式只连接指定服务，失败时不会启动本机后端。',
                    style: FluentTheme.of(context).typography.caption,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 30),
            const SectionTitle('翻译服务'),
            SettingsSectionCard(
              icon: FluentIcons.locale_language,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  const InfoBar(
                    title: Text('OpenAI 兼容接口'),
                    content: Text(
                      '统一使用 /v1/chat/completions。漫画默认由本地 RapidOCR 与 Windows OCR 识字，纯文本模型也可以翻译。',
                    ),
                    severity: InfoBarSeverity.info,
                  ),
                  const SizedBox(height: 14),
                  ToggleSwitch(
                    checked: _translationModelEnabled,
                    onChanged: (value) => setState(
                      () => _translationModelEnabled = value,
                    ),
                    content: const Text('启用翻译模型'),
                  ),
                  const SizedBox(height: 10),
                  ToggleSwitch(
                    checked: _translationModelSupportsVision,
                    onChanged: (value) => setState(
                      () => _translationModelSupportsVision = value,
                    ),
                    content: const Text('使用模型辅助识图'),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    '仅当模型明确支持图片输入时开启；关闭后图片不会发送给模型。',
                    style: FluentTheme.of(context).typography.caption,
                  ),
                  const SizedBox(height: 14),
                  InfoLabel(
                    label: 'API 地址',
                    child: TextBox(
                      controller: _baseUrlController,
                      placeholder: 'https://api.openai.com/v1',
                    ),
                  ),
                  const SizedBox(height: 12),
                  InfoLabel(
                    label: 'API 密钥',
                    child: TextBox(
                      controller: _apiKeyController,
                      obscureText: true,
                      placeholder:
                          scope.settings.value.translationModel.apiKeyConfigured
                              ? '已配置；留空保持不变'
                              : '尚未配置',
                    ),
                  ),
                  if (scope.settings.value.translationModel.apiKeyConfigured)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: ToggleSwitch(
                        checked: _clearTranslationApiKey,
                        onChanged: (value) => setState(
                          () => _clearTranslationApiKey = value,
                        ),
                        content: const Text('清除服务端已保存的 API 密钥'),
                      ),
                    ),
                  const SizedBox(height: 12),
                  InfoLabel(
                    label: '模型',
                    child: TextBox(
                      controller: _modelController,
                      placeholder: '文本模型名称',
                    ),
                  ),
                  const SizedBox(height: 26),
                  InfoLabel(
                    label: '系统提示词',
                    child: TextBox(
                      controller: _promptController,
                      maxLines: 5,
                    ),
                  ),
                  const SizedBox(height: 14),
                  _buildNumberSettings(compact),
                ],
              ),
            ),
            if (settings.error != null) ...<Widget>[
              const SizedBox(height: 16),
              InfoBar(
                title: const Text('设置服务不可用'),
                content: Text(settings.error!),
                severity: InfoBarSeverity.warning,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildNumberSettings(bool compact) {
    final autoTranslate = InfoLabel(
      label: '自动翻译后续章节数',
      child: TextBox(controller: _autoTranslateController),
    );
    final concurrency = InfoLabel(
      label: '下载并发数',
      child: TextBox(controller: _concurrencyController),
    );
    if (compact) {
      return Column(
        children: <Widget>[
          autoTranslate,
          const SizedBox(height: 12),
          concurrency,
        ],
      );
    }
    return Row(
      children: <Widget>[
        Expanded(child: autoTranslate),
        const SizedBox(width: 12),
        Expanded(child: concurrency),
      ],
    );
  }

  Widget _buildVoiceSettings(AppState appState, bool compact) {
    final selected = appState.ttsVoice;
    final selectedAvailable = selected == null ||
        _voices.any((voice) => voice.stableKey == selected.stableKey);
    final choices = <TtsVoice>[
      ..._voices,
      if (selected != null && !selectedAvailable) selected,
    ];
    final selectedKey = selected?.stableKey ?? _systemVoiceKey;
    final selectedVoice = selected == null
        ? null
        : choices.cast<TtsVoice?>().firstWhere(
              (voice) => voice?.stableKey == selected.stableKey,
              orElse: () => null,
            );
    final selector = SizedBox(
      width: compact ? double.infinity : 520,
      child: ComboBox<String>(
        value: selectedKey,
        isExpanded: true,
        items: <ComboBoxItem<String>>[
          const ComboBoxItem<String>(
            value: _systemVoiceKey,
            child: Text('跟随系统默认声音'),
          ),
          ...choices.map(
            (voice) => ComboBoxItem<String>(
              value: voice.stableKey,
              child: Text(
                '${voice.name} · ${voice.description}'
                ' · ${voice.qualityLabel}'
                '${!selectedAvailable && voice == selected ? '（当前不可用）' : ''}',
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        ],
        onChanged: _voicesLoading
            ? null
            : (key) => unawaited(_selectVoice(appState, key)),
      ),
    );
    final previewing =
        selectedVoice != null && _previewingVoiceKey == selectedVoice.stableKey;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        InfoLabel(
          label: '默认朗读风格',
          child: SizedBox(
            width: compact ? double.infinity : 320,
            child: ComboBox<TtsSpeechStyle>(
              value: appState.ttsSpeechStyle,
              isExpanded: true,
              items: TtsSpeechStyle.values
                  .map(
                    (style) => ComboBoxItem<TtsSpeechStyle>(
                      value: style,
                      child: Text(
                        '${style.label} · ${style.description}',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: (style) {
                if (style != null) {
                  unawaited(appState.setTtsSpeechStyle(style));
                }
              },
            ),
          ),
        ),
        const SizedBox(height: 14),
        InfoLabel(
          label: '系统声线',
          child: Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              selector,
              Button(
                onPressed: selectedVoice == null ||
                        _voicesLoading ||
                        _previewingVoiceKey != null ||
                        !selectedAvailable
                    ? null
                    : () => unawaited(
                          _previewVoice(
                            selectedVoice,
                            appState.ttsSpeechStyle,
                          ),
                        ),
                child: Text(previewing ? '试听中…' : '试听'),
              ),
              Tooltip(
                message: '重新扫描系统声音',
                child: IconButton(
                  icon: const Icon(
                    FluentIcons.refresh,
                    size: 16,
                    semanticLabel: '重新扫描系统声音',
                  ),
                  onPressed: _voicesLoading ? null : _loadVoices,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Text(
          _voicesLoading
              ? '正在读取 Windows 已安装声音…'
              : '已发现 ${_voices.length} 个系统声音。选择会立即保存，并用于之后打开的听书页面。',
          style: FluentTheme.of(context).typography.caption,
        ),
        if (!_voicesLoading) ...<Widget>[
          const SizedBox(height: 10),
          InfoBar(
            title: Text(
              _voices.any((voice) => voice.isNatural)
                  ? '已检测到自然声线'
                  : '建议安装 Natural / Neural 声线',
            ),
            content: Text(
              _voices.any((voice) => voice.isNatural)
                  ? '自然声线配合朗读风格，可获得更接近真人的节奏和语调。'
                  : '朗读风格会改善节奏、停顿和语调，但基础音色仍由 Windows 声线决定；标准声线可能保留机械感。',
            ),
            severity: _voices.any((voice) => voice.isNatural)
                ? InfoBarSeverity.success
                : InfoBarSeverity.warning,
          ),
        ],
        if (_voicesLoading) ...<Widget>[
          const SizedBox(height: 10),
          const ProgressBar(),
        ],
        if (_voiceError != null) ...<Widget>[
          const SizedBox(height: 12),
          InfoBar(
            title: const Text('声音服务不可用'),
            content: Text(_voiceError!),
            severity: InfoBarSeverity.warning,
          ),
        ],
      ],
    );
  }
}

void _validateRemoteBackendUrl(String value) {
  final uri = Uri.tryParse(value);
  if (uri == null || !uri.hasAuthority || uri.host.isEmpty) {
    throw const FormatException('FastAPI 地址格式无效');
  }
  if (uri.userInfo.isNotEmpty || uri.hasQuery || uri.hasFragment) {
    throw const FormatException('FastAPI 地址不能包含账号、查询参数或片段');
  }
  if (uri.scheme == 'https') return;
  if (uri.scheme == 'http' && _isPrivateBackendHost(uri.host)) return;
  throw const FormatException('远程后端必须使用 HTTPS；私有网络 IP 可使用 HTTP');
}

bool _isPrivateBackendHost(String host) {
  final normalized = host.toLowerCase();
  if (normalized == 'localhost' || normalized == '::1') return true;
  if (normalized.startsWith('fc') ||
      normalized.startsWith('fd') ||
      normalized.startsWith('fe80:')) {
    return true;
  }
  final parts = normalized.split('.').map(int.tryParse).toList();
  if (parts.length != 4 ||
      parts.any((part) => part == null || part < 0 || part > 255)) {
    return false;
  }
  final first = parts[0]!;
  final second = parts[1]!;
  return first == 10 ||
      first == 127 ||
      (first == 192 && second == 168) ||
      (first == 172 && second >= 16 && second <= 31) ||
      (first == 100 && second >= 64 && second <= 127) ||
      (first == 169 && second == 254);
}
