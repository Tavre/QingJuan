import 'package:flutter/services.dart';

enum ReaderHardwareKey { up, down }

class ReaderHardwareKeyService {
  ReaderHardwareKeyService({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel(_channelName);

  static const _channelName = 'qingjuan/reader';

  final MethodChannel _channel;
  void Function(ReaderHardwareKey key)? _listener;
  bool _attached = false;

  Future<void> attach({
    required bool enabled,
    required void Function(ReaderHardwareKey key) onKey,
  }) async {
    _listener = onKey;
    _attached = true;
    _channel.setMethodCallHandler(_handleMethod);
    await setEnabled(enabled);
  }

  Future<void> setEnabled(bool enabled) async {
    if (!_attached) return;
    try {
      await _channel.invokeMethod<void>('setVolumeKeyEnabled', enabled);
    } on MissingPluginException {
      // 非 Android 平台和 Widget 测试没有原生按键通道。
    } on PlatformException {
      // 硬件按键是增强功能，平台失败不能阻断正文阅读。
    }
  }

  Future<void> detach() async {
    if (!_attached) return;
    await setEnabled(false);
    _attached = false;
    _listener = null;
    _channel.setMethodCallHandler(null);
  }

  Future<void> _handleMethod(MethodCall call) async {
    if (call.method != 'volumeKey') return;
    final key = switch (call.arguments) {
      'up' => ReaderHardwareKey.up,
      'down' => ReaderHardwareKey.down,
      _ => null,
    };
    if (key != null) _listener?.call(key);
  }
}
