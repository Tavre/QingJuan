import 'package:flutter/services.dart';

enum ReaderHardwareKey { up, down }

class ReaderHardwareKeyService {
  ReaderHardwareKeyService({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel(_channelName);

  static const _channelName = 'qingjuan/reader';
  static final Expando<Map<String, _ReaderHardwareKeyChannelState>>
      _statesByMessenger =
      Expando<Map<String, _ReaderHardwareKeyChannelState>>();

  final MethodChannel _channel;
  void Function(ReaderHardwareKey key)? _listener;
  bool _attached = false;
  bool _enabled = false;

  _ReaderHardwareKeyChannelState get _channelState {
    final messenger = _channel.binaryMessenger;
    var states = _statesByMessenger[messenger];
    if (states == null) {
      states = <String, _ReaderHardwareKeyChannelState>{};
      _statesByMessenger[messenger] = states;
    }
    return states.putIfAbsent(
      _channel.name,
      _ReaderHardwareKeyChannelState.new,
    );
  }

  Future<void> attach({
    required bool enabled,
    required void Function(ReaderHardwareKey key) onKey,
  }) async {
    _listener = onKey;
    _attached = true;
    _enabled = enabled;
    final state = _channelState;
    state.owner = this;
    final generation = ++state.generation;
    _channel.setMethodCallHandler(_handleMethod);
    await _enqueuePlatformState(
      state,
      enabled: enabled,
      generation: generation,
      owner: this,
    );
  }

  Future<void> setEnabled(bool enabled) async {
    final state = _channelState;
    if (!_attached || !identical(state.owner, this)) return;
    _enabled = enabled;
    await _enqueuePlatformState(
      state,
      enabled: enabled,
      generation: state.generation,
      owner: this,
    );
  }

  Future<void> detach() async {
    if (!_attached) return;
    _attached = false;
    _enabled = false;
    _listener = null;
    final state = _channelState;
    if (!identical(state.owner, this)) return;
    state.owner = null;
    final generation = ++state.generation;
    await _enqueuePlatformState(
      state,
      enabled: false,
      generation: generation,
    );
    if (state.owner == null && state.generation == generation) {
      _channel.setMethodCallHandler(null);
      _statesByMessenger[_channel.binaryMessenger]?.remove(_channel.name);
    }
  }

  Future<void> _enqueuePlatformState(
    _ReaderHardwareKeyChannelState state, {
    required bool enabled,
    required int generation,
    ReaderHardwareKeyService? owner,
  }) {
    final operation = state.pending.then((_) async {
      if (state.generation != generation ||
          (owner == null
              ? state.owner != null
              : !identical(state.owner, owner))) {
        return;
      }
      try {
        await _channel.invokeMethod<void>('setVolumeKeyEnabled', enabled);
      } on MissingPluginException {
        // 非 Android 平台和 Widget 测试没有原生按键通道。
      } on PlatformException {
        // 硬件按键是增强功能，平台失败不能阻断正文阅读。
      } catch (_) {
        // 通道关闭或 Engine 正在销毁时同样不能阻断页面生命周期。
      }
    });
    state.pending = operation;
    return operation;
  }

  Future<void> _handleMethod(MethodCall call) async {
    if (!_attached ||
        !_enabled ||
        !identical(_channelState.owner, this) ||
        call.method != 'volumeKey') {
      return;
    }
    final key = switch (call.arguments) {
      'up' => ReaderHardwareKey.up,
      'down' => ReaderHardwareKey.down,
      _ => null,
    };
    if (key != null) _listener?.call(key);
  }
}

class _ReaderHardwareKeyChannelState {
  ReaderHardwareKeyService? owner;
  int generation = 0;
  Future<void> pending = Future<void>.value();
}
