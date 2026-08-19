import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../core/backend/backend_connection_manager.dart';
import '../../core/backend/backend_url_validator.dart';
import '../../shared/app_surface.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../audiobook/tts_voice_service.dart';
import 'widgets/backend_connection_card.dart';
import 'widgets/theme_settings_card.dart';
import 'widgets/translation_model_card.dart';
import 'widgets/tts_voice_settings_card.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({this.voiceService, super.key});

  final TtsVoiceService? voiceService;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static final _localModelSettingsUri = Uri.parse(
    '${AppState.defaultLocalBackendUrl}/admin/#settings',
  );

  final _backendController = TextEditingController();
  final _backendTokenController = TextEditingController();
  BackendConnectionMode _connectionMode = BackendConnectionMode.remote;
  bool _savingConnection = false;
  bool _modelChecking = false;
  bool _openingLocalModelSettings = false;
  bool _initialized = false;

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
    _backendController.dispose();
    _backendTokenController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final settings = scope.settings;
    final compact = usesMobileUi(context);
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[scope.appState, settings]),
      builder: (context, _) => PageFrame(
        title: compact ? '我的' : '设置',
        subtitle: '管理界面主题、设备听书、后端连接和翻译服务。',
        compactHeader: ReadingPageHeader(
          title: '我的',
          subtitle: '阅读偏好与服务器连接',
          actions: <Widget>[
            if (scope.appState.clientPluginManagementAvailable) ...<Widget>[
              Tooltip(
                message: '插件配置',
                child: IconButton(
                  key: const ValueKey('settings-plugins-button'),
                  icon: const Icon(
                    FluentIcons.plug_connected,
                    semanticLabel: '插件配置',
                  ),
                  onPressed: () =>
                      scope.appState.selectSection(AppSection.plugins),
                ),
              ),
              const SizedBox(width: 7),
            ],
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
                icon: FluentIcons.contact,
                title: '设备与服务',
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
            ThemeSettingsCard(
              themeMode: scope.appState.themeMode,
              onChanged: (mode) => unawaited(scope.appState.setThemeMode(mode)),
            ),
            const SizedBox(height: 30),
            const SectionTitle('听书声音'),
            TtsVoiceSettingsCard(
              appState: scope.appState,
              compact: compact,
              voiceService: widget.voiceService,
            ),
            const SizedBox(height: 30),
            const SectionTitle('后端连接'),
            BackendConnectionCard(
              backend: scope.backend,
              activeMode: scope.appState.connectionMode,
              draftMode: _connectionMode,
              localBackendSupported: scope.appState.localBackendSupported,
              backendUrlController: _backendController,
              backendTokenController: _backendTokenController,
              onModeChanged: (mode) => setState(() => _connectionMode = mode),
              openingLocalModelSettings: _openingLocalModelSettings,
              onOpenLocalModelSettings: () =>
                  unawaited(_openLocalModelSettings(scope)),
            ),
            const SizedBox(height: 30),
            const SectionTitle('翻译服务'),
            TranslationModelCard(
              backend: scope.backend,
              checking: _modelChecking,
              onCheck: () => _checkTranslationModel(scope),
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

  Future<void> _openLocalModelSettings(AppScope scope) async {
    if (_openingLocalModelSettings) return;
    setState(() => _openingLocalModelSettings = true);
    try {
      await scope.backend.openLocalAdmin(_localModelSettingsUri);
    } catch (error) {
      if (!mounted) return;
      displayInfoBar(
        context,
        builder: (_, __) => InfoBar(
          title: const Text('无法打开模型设置'),
          content: Text('$error'),
          severity: InfoBarSeverity.error,
        ),
      );
    } finally {
      if (mounted) setState(() => _openingLocalModelSettings = false);
    }
  }
}
