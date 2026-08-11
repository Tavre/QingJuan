import '../api/api_client.dart';

enum BackendStatus { unconfigured, checking, ready, failed }

class BackendConnectionManager {
  BackendConnectionManager(
    this.api, {
    required bool Function() isConfigured,
    void Function()? validateConfiguration,
  })  : _isConfigured = isConfigured,
        _validateConfiguration = validateConfiguration;

  final ApiClient api;
  final bool Function() _isConfigured;
  final void Function()? _validateConfiguration;

  BackendStatus status = BackendStatus.unconfigured;
  String message = '请先配置 Linux 后端';

  Future<void> ensureReady() async {
    if (!_isConfigured()) {
      status = BackendStatus.unconfigured;
      message = '请先填写 Linux 后端地址和连接 Token';
      return;
    }

    status = BackendStatus.checking;
    message = '正在连接 Linux 后端';
    try {
      _validateConfiguration?.call();
      await api.fetchServiceMeta();
      status = BackendStatus.ready;
      message = 'Linux 后端已连接';
    } catch (error) {
      status = BackendStatus.failed;
      message = 'Linux 后端连接失败：$error';
    }
  }
}
