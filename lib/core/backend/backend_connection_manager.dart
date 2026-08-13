import 'dart:async';

import '../api/api_client.dart';
import '../models/book.dart';
import '../models/settings.dart';
import 'local_backend_process.dart';

enum BackendStatus { unconfigured, checking, starting, ready, failed }

class BackendConnectionManager {
  BackendConnectionManager(
    this.api, {
    required bool Function() isConfigured,
    bool Function()? isLocal,
    LocalBackendLifecycle? localBackend,
    void Function()? validateConfiguration,
  })  : _isConfigured = isConfigured,
        _isLocal = isLocal ?? (() => false),
        _localBackend = localBackend,
        _validateConfiguration = validateConfiguration;

  final ApiClient api;
  final bool Function() _isConfigured;
  final bool Function() _isLocal;
  final LocalBackendLifecycle? _localBackend;
  final void Function()? _validateConfiguration;

  BackendStatus status = BackendStatus.unconfigured;
  String message = '请先配置 Linux 后端';
  TranslationModelCheck? translationModelCheck;
  bool translationModelCheckInProgress = false;
  Timer? _heartbeatTimer;

  Future<void> ensureReady() async {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    translationModelCheck = null;
    translationModelCheckInProgress = false;
    if (_isLocal()) {
      await _ensureLocalReady();
      return;
    }

    await _localBackend?.stop();
    if (!_isConfigured()) {
      status = BackendStatus.unconfigured;
      message = '请先填写 Linux 后端地址和连接 Token';
      return;
    }

    status = BackendStatus.checking;
    message = '正在连接 Linux 后端';
    try {
      _validateConfiguration?.call();
      final meta = await api.fetchServiceMeta();
      await _finishReady(meta, label: 'Linux 后端', enableHeartbeat: true);
    } catch (error) {
      status = BackendStatus.failed;
      message = 'Linux 后端连接失败：$error';
    }
  }

  Future<void> _ensureLocalReady() async {
    final localBackend = _localBackend;
    if (localBackend == null) {
      status = BackendStatus.failed;
      message = '当前平台不支持 Windows 本机后端';
      return;
    }

    status = BackendStatus.starting;
    message = '正在检查并启动本机后端';
    try {
      final meta = await localBackend.ensureRunning(api);
      await _finishReady(meta, label: '本机后端', enableHeartbeat: false);
    } catch (error) {
      await localBackend.stop();
      status = BackendStatus.failed;
      message = '本机后端启动失败：$error';
    }
  }

  Future<void> _finishReady(
    JsonMap meta, {
    required String label,
    required bool enableHeartbeat,
  }) async {
    status = BackendStatus.ready;
    final rawCapabilities = meta['capabilities'];
    final capabilities = rawCapabilities is Map
        ? Map<String, dynamic>.from(rawCapabilities)
        : const <String, dynamic>{};
    if (capabilities['translationModelCheck'] == true) {
      final modelCheck = await checkTranslationModel();
      message = modelCheck.available
          ? '$label已连接，服务端翻译模型自检通过'
          : '$label已连接；${modelCheck.message}';
    } else {
      translationModelCheck = null;
      message = '$label已连接；当前服务版本不支持翻译模型自检';
    }
    if (enableHeartbeat) {
      _heartbeatTimer = Timer.periodic(const Duration(seconds: 60), (_) {
        unawaited(api.sendDeviceHeartbeat().catchError((_) {}));
      });
    }
  }

  Future<TranslationModelCheck> checkTranslationModel({
    bool force = false,
  }) async {
    translationModelCheckInProgress = true;
    try {
      translationModelCheck = await api.checkTranslationModel(force: force);
    } catch (_) {
      translationModelCheck = TranslationModelCheck.clientFailure();
    } finally {
      translationModelCheckInProgress = false;
    }
    return translationModelCheck!;
  }

  Future<void> dispose() async {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    await _localBackend?.stop();
  }
}
