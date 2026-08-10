import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/foundation.dart' show ValueListenable, ValueNotifier;
import 'package:shared_preferences/shared_preferences.dart';

import '../core/backend/connection_secret_store.dart';
import '../core/models/tts_speech_style.dart';
import '../core/models/tts_voice.dart';

enum AppSection { library, search, sources, tasks, settings, about }

enum AppThemeMode { system, light, dark }

enum BackendConnectionMode { local, remote }

class AppState extends ChangeNotifier {
  AppState(
    this._preferences, {
    ConnectionSecretStore? secretStore,
    String initialBackendToken = '',
  })  : _secretStore = secretStore,
        _themeMode = AppThemeMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_themeKey),
          orElse: () => AppThemeMode.system,
        ),
        _connectionMode = BackendConnectionMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_backendModeKey),
          orElse: () => BackendConnectionMode.local,
        ),
        _backendUrl = _preferences.getString(_backendKey) ?? _defaultBackendUrl,
        _backendToken = initialBackendToken,
        _ttsVoice = _readTtsVoice(_preferences),
        _ttsSpeechStyle = parseTtsSpeechStyle(
          _preferences.getString(_ttsSpeechStyleKey),
        ) {
    _themeModeListenable = ValueNotifier<ThemeMode>(fluentThemeMode);
  }

  static const _themeKey = 'qingjuan.theme';
  static const _backendKey = 'qingjuan.backendUrl';
  static const _backendModeKey = 'qingjuan.backendMode';
  static const _ttsVoiceKey = 'qingjuan.ttsVoice';
  static const _ttsSpeechStyleKey = 'qingjuan.ttsSpeechStyle';
  static const _defaultBackendUrl = 'http://127.0.0.1:19453';

  final SharedPreferences _preferences;
  final ConnectionSecretStore? _secretStore;
  AppSection _section = AppSection.library;
  final ValueNotifier<AppSection> _sectionListenable =
      ValueNotifier<AppSection>(AppSection.library);
  AppThemeMode _themeMode;
  late final ValueNotifier<ThemeMode> _themeModeListenable;
  String _backendUrl;
  String _backendToken;
  BackendConnectionMode _connectionMode;
  TtsVoice? _ttsVoice;
  TtsSpeechStyle _ttsSpeechStyle;
  String? _notice;

  AppSection get section => _section;
  AppThemeMode get themeMode => _themeMode;
  String get backendUrl => _backendUrl;
  String get backendToken => _backendToken;
  BackendConnectionMode get connectionMode => _connectionMode;
  TtsVoice? get ttsVoice => _ttsVoice;
  TtsSpeechStyle get ttsSpeechStyle => _ttsSpeechStyle;
  String? get notice => _notice;
  ValueListenable<AppSection> get sectionListenable => _sectionListenable;
  ValueListenable<ThemeMode> get themeModeListenable => _themeModeListenable;

  ThemeMode get fluentThemeMode => switch (_themeMode) {
        AppThemeMode.system => ThemeMode.system,
        AppThemeMode.light => ThemeMode.light,
        AppThemeMode.dark => ThemeMode.dark,
      };

  void selectSection(AppSection value) {
    if (_section == value) return;
    _section = value;
    _sectionListenable.value = value;
    notifyListeners();
  }

  @override
  void dispose() {
    _sectionListenable.dispose();
    _themeModeListenable.dispose();
    super.dispose();
  }

  Future<void> setThemeMode(AppThemeMode value) async {
    if (_themeMode == value) return;
    _themeMode = value;
    _themeModeListenable.value = fluentThemeMode;
    notifyListeners();
    await _preferences.setString(_themeKey, value.name);
  }

  Future<void> setBackendUrl(String value) async {
    final normalized = value.trim().replaceAll(RegExp(r'/+$'), '');
    if (normalized.isEmpty || normalized == _backendUrl) return;
    _backendUrl = normalized;
    await _preferences.setString(_backendKey, normalized);
    notifyListeners();
  }

  Future<void> setBackendConnection({
    required BackendConnectionMode mode,
    required String url,
    required String token,
  }) async {
    final normalized = url.trim().replaceAll(RegExp(r'/+$'), '');
    if (normalized.isEmpty) return;
    final normalizedToken =
        mode == BackendConnectionMode.remote ? token.trim() : '';
    _connectionMode = mode;
    _backendUrl = normalized;
    _backendToken = normalizedToken;
    await _preferences.setString(_backendModeKey, mode.name);
    await _preferences.setString(_backendKey, normalized);
    final secretStore = _secretStore;
    if (secretStore != null) {
      if (normalizedToken.isEmpty) {
        await secretStore.deleteToken();
      } else {
        await secretStore.writeToken(normalizedToken);
      }
    }
    notifyListeners();
  }

  Future<void> setTtsVoice(TtsVoice? value) async {
    if (_ttsVoice == value) return;
    _ttsVoice = value;
    notifyListeners();
    if (value == null) {
      await _preferences.remove(_ttsVoiceKey);
    } else {
      await _preferences.setString(_ttsVoiceKey, jsonEncode(value.toJson()));
    }
  }

  Future<void> setTtsSpeechStyle(TtsSpeechStyle value) async {
    if (_ttsSpeechStyle == value) return;
    _ttsSpeechStyle = value;
    notifyListeners();
    await _preferences.setString(_ttsSpeechStyleKey, value.name);
  }

  void showNotice(String message) {
    _notice = message;
    notifyListeners();
  }

  void clearNotice() {
    if (_notice == null) return;
    _notice = null;
    notifyListeners();
  }

  static TtsVoice? _readTtsVoice(SharedPreferences preferences) {
    final raw = preferences.getString(_ttsVoiceKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final json = jsonDecode(raw);
      if (json is! Map) return null;
      final voice = TtsVoice.fromJson(Map<String, dynamic>.from(json));
      return voice.name.isEmpty || voice.locale.isEmpty ? null : voice;
    } catch (_) {
      return null;
    }
  }
}
