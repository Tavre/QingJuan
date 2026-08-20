import 'package:fluent_ui/fluent_ui.dart';

import '../../../app/app_state.dart';
import '../../../core/backend/backend_connection_manager.dart';
import '../../../shared/responsive.dart';
import 'settings_section_card.dart';

class BackendConnectionCard extends StatelessWidget {
  const BackendConnectionCard({
    required this.backend,
    required this.activeMode,
    required this.draftMode,
    required this.localBackendSupported,
    required this.backendUrlController,
    required this.backendTokenController,
    required this.onModeChanged,
    required this.openingLocalModelSettings,
    required this.onOpenLocalModelSettings,
    super.key,
  });

  final BackendConnectionManager backend;
  final BackendConnectionMode activeMode;
  final BackendConnectionMode draftMode;
  final bool localBackendSupported;
  final TextEditingController backendUrlController;
  final TextEditingController backendTokenController;
  final ValueChanged<BackendConnectionMode> onModeChanged;
  final bool openingLocalModelSettings;
  final VoidCallback onOpenLocalModelSettings;

  @override
  Widget build(BuildContext context) {
    return SettingsSectionCard(
      icon: FluentIcons.plug_connected,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _connectionStatusBar(),
          const SizedBox(height: 12),
          if (localBackendSupported) ...<Widget>[
            InfoLabel(
              label: '连接模式',
              child: ComboBox<BackendConnectionMode>(
                key: const ValueKey('backend-connection-mode'),
                value: draftMode,
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
                  if (value != null) onModeChanged(value);
                },
              ),
            ),
            const SizedBox(height: 12),
          ],
          if (draftMode == BackendConnectionMode.remote) ...<Widget>[
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
                controller: backendUrlController,
                magnifierConfiguration:
                    textInputMagnifierConfiguration(context),
                placeholder: 'https://qingjuan.example.com',
              ),
            ),
            const SizedBox(height: 12),
            InfoLabel(
              label: '连接 Token',
              child: TextBox(
                key: const ValueKey('linux-backend-token'),
                controller: backendTokenController,
                magnifierConfiguration:
                    textInputMagnifierConfiguration(context),
                obscureText: true,
                enableInteractiveSelection: true,
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
                '翻译模型、API 密钥与 OCR 在后端管理界面的“模型设置”中维护。',
              ),
              severity: InfoBarSeverity.info,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                FilledButton(
                  key: const ValueKey('open-local-model-settings'),
                  onPressed: activeMode == BackendConnectionMode.local &&
                          backend.status == BackendStatus.ready &&
                          !openingLocalModelSettings
                      ? onOpenLocalModelSettings
                      : null,
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      if (openingLocalModelSettings)
                        const SizedBox(
                          width: 16,
                          height: 16,
                          child: ProgressRing(strokeWidth: 2),
                        )
                      else
                        const Icon(
                          FluentIcons.open_in_new_window,
                          size: 16,
                          semanticLabel: '在系统浏览器打开',
                        ),
                      const SizedBox(width: 8),
                      const Text('打开模型设置'),
                    ],
                  ),
                ),
                Text(
                  activeMode == BackendConnectionMode.local &&
                          backend.status == BackendStatus.ready
                      ? '${AppState.defaultLocalBackendUrl}/admin/#settings'
                      : '请先保存本机模式并等待后端连接成功',
                  style: FluentTheme.of(context).typography.caption,
                ),
              ],
            ),
          ],
          const SizedBox(height: 8),
          Text(
            draftMode == BackendConnectionMode.local
                ? '切换到远程模式时会停止本应用启动的本机后端；已保存的远程地址和 Token 会继续保留。'
                : '公网地址必须使用 HTTPS；局域网、Tailscale 或 WireGuard 私有地址可使用 HTTP。远程失败不会回退本机。',
            style: FluentTheme.of(context).typography.caption,
          ),
        ],
      ),
    );
  }

  Widget _connectionStatusBar() {
    final status = backend.status;
    final isLocal = activeMode == BackendConnectionMode.local;
    final title = switch (status) {
      BackendStatus.unconfigured => '首次使用需要连接服务器',
      BackendStatus.checking => '正在检查 Linux 后端',
      BackendStatus.starting => '正在启动本机后端',
      BackendStatus.ready => isLocal ? '本机后端已连接' : 'Linux 后端已连接',
      BackendStatus.failed => isLocal ? '本机后端启动失败' : 'Linux 后端连接失败',
    };
    final content = switch (status) {
      BackendStatus.ready || BackendStatus.failed => backend.message,
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
}
