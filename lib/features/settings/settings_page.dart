import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../core/backend/backend_connection_manager.dart';
import '../../core/backend/backend_url_validator.dart';
import '../../core/models/settings.dart';
import '../../core/models/tts_speech_style.dart';
import '../../core/models/tts_voice.dart';
import '../../shared/app_surface.dart';
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
  BackendConnectionMode _connectionMode = BackendConnectionMode.remote;
  bool _savingConnection = false;
  bool _modelChecking = false;
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
          _voiceError = '当前设备没有可用的系统声音，请先安装或启用 TTS 语音包。';
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
    _backendController.text = scope.appState.remoteBackendUrl;
    _backendTokenController.text = scope.appState.remoteBackendToken;
    _connectionMode = scope.appState.connectionMode;
  }

  Future<void> _save() async {
    final scope = AppScope.of(context);
    setState(() => _savingConnection = true);
    try {
      final backendUrl = _backendController.text.trim();
      final backendToken = _backendTokenController.text.trim();
      final connectionChanged = scope.appState.connectionMode !=
              _connectionMode ||
          (_connectionMode == BackendConnectionMode.remote &&
              (scope.appState.remoteBackendUrl.replaceAll(RegExp(r'/+$'), '') !=
                      backendUrl.replaceAll(RegExp(r'/+$'), '') ||
                  scope.appState.remoteBackendToken != backendToken));
      if (_connectionMode == BackendConnectionMode.remote) {
        validateBackendUrl(backendUrl);
        if (backendToken.isEmpty) {
          throw StateError('Linux 后端必须填写连接 Token');
        }
        await scope.api.testConnection(
          baseUrl: backendUrl,
          token: backendToken,
        );
      }
      if (_connectionMode == BackendConnectionMode.remote) {
        await scope.appState.saveRemoteBackendConnection(
          url: backendUrl,
          token: backendToken,
        );
      }
      await scope.appState.selectBackendMode(_connectionMode);
      await scope.backend.ensureReady();
      if (scope.backend.status != BackendStatus.ready) {
        throw StateError(scope.backend.message);
      }
      scope.appState.clearNotice();
      if (connectionChanged) {
        scope.library.resetForBackendSwitch();
        scope.sources.resetForBackendSwitch();
        scope.tasks.resetForBackendSwitch();
      }
      await Future.wait<void>(<Future<void>>[
        scope.library.load(),
        scope.sources.load(),
        scope.tasks.load(),
        scope.settings.load(),
      ]);
      if (mounted) {
        final modelReady =
            scope.backend.translationModelCheck?.available == true;
        displayInfoBar(
          context,
          builder: (_, __) => InfoBar(
            title: Text(modelReady ? '连接与模型自检已完成' : '连接已保存'),
            content: Text(scope.backend.message),
            severity:
                modelReady ? InfoBarSeverity.success : InfoBarSeverity.warning,
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
    } finally {
      if (mounted) setState(() => _savingConnection = false);
    }
  }

  @override
  void dispose() {
    unawaited(_voiceService.dispose());
    _backendController.dispose();
    _backendTokenController.dispose();
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
        subtitle: '管理界面主题、设备听书、后端连接和翻译服务。',
        compactHeader: ReadingPageHeader(
          title: '设置',
          subtitle: '偏好、听书与服务器连接',
          actions: <Widget>[
            Tooltip(
              message: '关于青卷',
              child: IconButton(
                key: const ValueKey('settings-about-button'),
                icon: const Icon(
                  FluentIcons.info,
                  semanticLabel: '关于青卷',
                ),
                onPressed: () => scope.appState.selectSection(AppSection.about),
              ),
            ),
            const SizedBox(width: 7),
            FilledButton(
              onPressed: _savingConnection || settings.saving ? null : _save,
              child: const Text('保存连接'),
            ),
          ],
        ),
        command: Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            if (compact)
              Button(
                key: const ValueKey('settings-about-button'),
                onPressed: () => scope.appState.selectSection(AppSection.about),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Icon(FluentIcons.info, size: 16),
                    SizedBox(width: 8),
                    Text('关于青卷'),
                  ],
                ),
              ),
            FilledButton(
              onPressed: _savingConnection || settings.saving ? null : _save,
              child: const Text('保存连接'),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (compact) ...<Widget>[
              FeatureHero(
                icon: FluentIcons.settings,
                title: '让青卷更适合你',
                message: scope.appState.localBackendSupported
                    ? '界面与设备偏好保存在本机，书架和任务由当前选择的后端管理。'
                    : '界面与设备偏好保存在手机，连接、书架和任务数据由 Linux 后端统一管理。',
                child: Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: <Widget>[
                    StatusPill(
                      switch (scope.appState.themeMode) {
                        AppThemeMode.system => '跟随系统',
                        AppThemeMode.light => '浅色外观',
                        AppThemeMode.dark => '深色外观',
                      },
                      accented: true,
                      icon: FluentIcons.color,
                    ),
                    StatusPill(
                      scope.backend.status == BackendStatus.ready
                          ? scope.appState.connectionMode ==
                                  BackendConnectionMode.local
                              ? '本机后端已连接'
                              : '服务器已连接'
                          : '后端待检查',
                      icon: scope.backend.status == BackendStatus.ready
                          ? FluentIcons.plug_connected
                          : FluentIcons.warning,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 28),
            ],
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
                    '跟随系统可自动响应 Android 的浅色与深色设置。',
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
                      final icon = switch (mode) {
                        AppThemeMode.system => FluentIcons.cell_phone,
                        AppThemeMode.light => FluentIcons.sunny,
                        AppThemeMode.dark => FluentIcons.clear_night,
                      };
                      return _ThemeModeChoice(
                        label: label,
                        icon: icon,
                        selected: scope.appState.themeMode == mode,
                        onPressed: () => scope.appState.setThemeMode(mode),
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
                  _connectionStatusBar(scope),
                  const SizedBox(height: 12),
                  if (scope.appState.localBackendSupported) ...<Widget>[
                    InfoLabel(
                      label: '连接模式',
                      child: ComboBox<BackendConnectionMode>(
                        key: const ValueKey('backend-connection-mode'),
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
                  ],
                  if (_connectionMode ==
                      BackendConnectionMode.remote) ...<Widget>[
                    const InfoBar(
                      title: Text('Linux 连接参数独立保存'),
                      content: Text(
                        '此处的地址与 Token 只属于 Linux 远程后端，切换到本机后端不会覆盖或清空。',
                      ),
                      severity: InfoBarSeverity.info,
                    ),
                    const SizedBox(height: 12),
                    InfoLabel(
                      label: 'FastAPI 地址',
                      child: TextBox(
                        key: const ValueKey('linux-backend-url'),
                        controller: _backendController,
                        placeholder: 'https://qingjuan.example.com',
                      ),
                    ),
                    const SizedBox(height: 12),
                    InfoLabel(
                      label: '连接 Token',
                      child: TextBox(
                        key: const ValueKey('linux-backend-token'),
                        controller: _backendTokenController,
                        obscureText: true,
                        enableSuggestions: false,
                        autocorrect: false,
                        placeholder: '由 Linux 服务端管理员生成',
                      ),
                    ),
                  ] else ...<Widget>[
                    const InfoBar(
                      title: Text('本机模式使用固定回环地址'),
                      content: Text(
                        '${AppState.defaultLocalBackendUrl}；保存后会检查并按需启动随包后端，无需连接 Token。'
                        '服务设置入口：${AppState.defaultLocalBackendUrl}/admin/',
                      ),
                      severity: InfoBarSeverity.info,
                    ),
                  ],
                  const SizedBox(height: 8),
                  Text(
                    _connectionMode == BackendConnectionMode.local
                        ? '切换到远程模式时会停止本应用启动的本机后端；已保存的远程地址和 Token 会继续保留。'
                        : '公网地址必须使用 HTTPS；局域网、Tailscale 或 WireGuard 私有地址可使用 HTTP。远程失败不会回退本机。',
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
                    title: Text('由后端管理界面统一配置'),
                    content: Text(
                      '客户端只创建服务端翻译任务，不保存模型密钥或直连模型供应商；每次连接都会执行模型自检。',
                    ),
                    severity: InfoBarSeverity.info,
                  ),
                  const SizedBox(height: 14),
                  _translationModelStatusBar(scope),
                  const SizedBox(height: 12),
                  Button(
                    onPressed: scope.backend.status == BackendStatus.ready &&
                            !_modelChecking
                        ? () => _checkTranslationModel(scope)
                        : null,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: <Widget>[
                        if (_modelChecking) ...<Widget>[
                          const SizedBox(
                            width: 14,
                            height: 14,
                            child: ProgressRing(strokeWidth: 2),
                          ),
                          const SizedBox(width: 8),
                        ] else ...<Widget>[
                          const Icon(FluentIcons.refresh, size: 14),
                          const SizedBox(width: 8),
                        ],
                        Text(_modelChecking ? '正在检测' : '重新检测模型'),
                      ],
                    ),
                  ),
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

  Future<void> _checkTranslationModel(AppScope scope) async {
    setState(() => _modelChecking = true);
    final result = await scope.backend.checkTranslationModel();
    if (!mounted) return;
    setState(() => _modelChecking = false);
    displayInfoBar(
      context,
      builder: (_, __) => InfoBar(
        title: Text(result.available ? '模型自检通过' : '模型自检未通过'),
        content: Text(result.message),
        severity: result.available
            ? InfoBarSeverity.success
            : InfoBarSeverity.warning,
      ),
    );
  }

  Widget _translationModelStatusBar(AppScope scope) {
    final check = scope.backend.translationModelCheck;
    if (check == null) {
      return const InfoBar(
        title: Text('等待服务端模型自检'),
        content: Text('连接后端后会自动检查管理界面保存的翻译模型。'),
        severity: InfoBarSeverity.info,
      );
    }
    final title = switch (check.status) {
      TranslationModelCheckStatus.ready => '服务端翻译模型可用',
      TranslationModelCheckStatus.disabled => '服务端翻译模型未启用',
      TranslationModelCheckStatus.unconfigured => '服务端翻译模型未配置完整',
      TranslationModelCheckStatus.failed => '服务端翻译模型自检失败',
    };
    final details = <String>[
      if (check.model != null && check.model!.isNotEmpty) check.model!,
      if (check.latencyMs != null) '${check.latencyMs} ms',
      if (check.available) check.supportsVision ? '支持视觉' : '仅文本',
      if (check.cached) '近期检查结果',
    ];
    return InfoBar(
      title: Text(title),
      content: Text(check.available && details.isNotEmpty
          ? details.join(' · ')
          : check.message),
      severity: switch (check.status) {
        TranslationModelCheckStatus.ready => InfoBarSeverity.success,
        TranslationModelCheckStatus.failed => InfoBarSeverity.error,
        _ => InfoBarSeverity.warning,
      },
    );
  }

  Widget _connectionStatusBar(AppScope scope) {
    final status = scope.backend.status;
    final isLocal =
        scope.appState.connectionMode == BackendConnectionMode.local;
    final title = switch (status) {
      BackendStatus.unconfigured => '首次使用需要连接服务器',
      BackendStatus.checking => '正在检查 Linux 后端',
      BackendStatus.starting => '正在启动本机后端',
      BackendStatus.ready => isLocal ? '本机后端已连接' : 'Linux 后端已连接',
      BackendStatus.failed => isLocal ? '本机后端启动失败' : 'Linux 后端连接失败',
    };
    final content = switch (status) {
      BackendStatus.ready || BackendStatus.failed => scope.backend.message,
      BackendStatus.starting => '正在检查固定回环端口并按需启动随包后端。',
      _ => '请填写 Linux 服务端提供的地址和 Token。',
    };
    final severity = switch (status) {
      BackendStatus.unconfigured => InfoBarSeverity.warning,
      BackendStatus.checking || BackendStatus.starting => InfoBarSeverity.info,
      BackendStatus.ready => InfoBarSeverity.success,
      BackendStatus.failed => InfoBarSeverity.error,
    };
    return InfoBar(
      title: Text(title),
      content: Text(content),
      severity: severity,
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
              ? '正在读取设备已安装声音…'
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
                  : '朗读风格会改善节奏、停顿和语调，但基础音色仍由系统 TTS 引擎决定；标准声线可能保留机械感。',
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

class _ThemeModeChoice extends StatelessWidget {
  const _ThemeModeChoice({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return SizedBox(
      width: 92,
      child: AppSurface(
        onPressed: onPressed,
        selected: selected,
        tone: selected ? AppSurfaceTone.accent : AppSurfaceTone.muted,
        borderRadius: 16,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
        child: Column(
          children: <Widget>[
            Icon(
              icon,
              size: 20,
              color: selected
                  ? theme.accentColor
                  : theme.resources.textFillColorSecondary,
            ),
            const SizedBox(height: 7),
            Text(
              label,
              maxLines: 1,
              style: theme.typography.caption?.copyWith(
                color: selected ? theme.accentColor : null,
                fontWeight: selected ? FontWeight.w700 : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
