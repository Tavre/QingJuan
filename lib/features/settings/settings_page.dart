import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../core/models/settings.dart';
import '../../core/models/tts_voice.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../audiobook/tts_voice_service.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({this.voiceService, super.key});

  final TtsVoiceService? voiceService;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static const _systemVoiceKey = '__system_default__';

  final _backendController = TextEditingController();
  final _baseUrlController = TextEditingController();
  final _apiKeyController = TextEditingController();
  final _modelController = TextEditingController();
  final _promptController = TextEditingController();
  final _autoTranslateController = TextEditingController();
  final _concurrencyController = TextEditingController();
  String _provider = 'openai';
  bool _providerEnabled = false;
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

  Future<void> _previewVoice(TtsVoice voice) async {
    setState(() {
      _previewingVoiceKey = voice.stableKey;
      _voiceError = null;
    });
    try {
      await _voiceService.preview(voice);
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
    _loadModel(scope.settings.value);
  }

  void _loadModel(TranslationSettings settings) {
    final provider =
        settings.providers[_provider] ?? const ProviderSettings.empty();
    _baseUrlController.text = provider.baseUrl;
    _apiKeyController.text = provider.apiKey;
    _modelController.text = provider.model;
    _promptController.text = settings.systemPrompt;
    _autoTranslateController.text = '${settings.autoTranslateNextChapters}';
    _concurrencyController.text = '${settings.downloadConcurrency}';
    _providerEnabled = provider.enabled;
  }

  TranslationSettings _commitProvider(TranslationSettings settings) {
    final providers = Map<String, ProviderSettings>.from(settings.providers);
    providers[_provider] = ProviderSettings(
      enabled: _providerEnabled,
      baseUrl: _baseUrlController.text.trim(),
      apiKey: _apiKeyController.text.trim(),
      model: _modelController.text.trim(),
    );
    return settings.copyWith(providers: providers);
  }

  void _selectProvider(String provider) {
    final controller = AppScope.of(context).settings;
    controller.update(_commitProvider(controller.value));
    setState(() {
      _provider = provider;
      _loadModel(controller.value);
    });
  }

  Future<void> _save() async {
    final scope = AppScope.of(context);
    var settings = _commitProvider(scope.settings.value);
    settings = settings.copyWith(
      systemPrompt: _promptController.text,
      autoTranslateNextChapters:
          int.tryParse(_autoTranslateController.text) ?? 2,
      downloadConcurrency: int.tryParse(_concurrencyController.text) ?? 4,
    );
    scope.settings.update(settings);
    try {
      await scope.appState.setBackendUrl(_backendController.text);
      await scope.backend.ensureReady();
      await scope.settings.save();
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
            const SizedBox(height: 30),
            const SectionTitle('听书声音'),
            _buildVoiceSettings(scope.appState, compact),
            const SizedBox(height: 30),
            const SectionTitle('后端连接'),
            InfoLabel(
              label: 'FastAPI 地址',
              child: TextBox(
                controller: _backendController,
                placeholder: 'http://127.0.0.1:19453',
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '应用会优先启动本地后端，也可以填写其他可信 FastAPI 服务地址。',
              style: FluentTheme.of(context).typography.caption,
            ),
            const SizedBox(height: 30),
            const SectionTitle('翻译服务'),
            Flex(
              direction: compact ? Axis.vertical : Axis.horizontal,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                SizedBox(
                  width: compact ? double.infinity : 210,
                  child: Column(
                    children: providerKeys
                        .map(
                          (provider) => Padding(
                            padding: const EdgeInsets.only(bottom: 6),
                            child: SizedBox(
                              width: double.infinity,
                              child: ToggleButton(
                                checked: _provider == provider,
                                onChanged: (_) => _selectProvider(provider),
                                child: Align(
                                  alignment: Alignment.centerLeft,
                                  child: Text(provider),
                                ),
                              ),
                            ),
                          ),
                        )
                        .toList(),
                  ),
                ),
                SizedBox(width: compact ? 0 : 22, height: compact ? 18 : 0),
                Expanded(
                  flex: compact ? 0 : 1,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      ToggleSwitch(
                        checked: _providerEnabled,
                        onChanged: (value) =>
                            setState(() => _providerEnabled = value),
                        content: const Text('启用当前提供商'),
                      ),
                      const SizedBox(height: 14),
                      InfoLabel(
                          label: 'API 地址',
                          child: TextBox(controller: _baseUrlController)),
                      const SizedBox(height: 12),
                      InfoLabel(
                        label: 'API 密钥',
                        child: TextBox(
                            controller: _apiKeyController, obscureText: true),
                      ),
                      const SizedBox(height: 12),
                      InfoLabel(
                          label: '模型',
                          child: TextBox(controller: _modelController)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 26),
            InfoLabel(
              label: '系统提示词',
              child: TextBox(controller: _promptController, maxLines: 5),
            ),
            const SizedBox(height: 14),
            Row(
              children: <Widget>[
                Expanded(
                  child: InfoLabel(
                    label: '自动翻译后续章节数',
                    child: TextBox(controller: _autoTranslateController),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: InfoLabel(
                    label: '下载并发数',
                    child: TextBox(controller: _concurrencyController),
                  ),
                ),
              ],
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
                    : () => unawaited(_previewVoice(selectedVoice)),
                child: Text(previewing ? '试听中…' : '试听'),
              ),
              IconButton(
                icon: const Icon(FluentIcons.refresh, size: 16),
                onPressed: _voicesLoading ? null : _loadVoices,
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
