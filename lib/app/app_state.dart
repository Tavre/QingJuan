import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:shared_preferences/shared_preferences.dart';

import '../core/models/tts_voice.dart';

enum AppSection { library, search, sources, tasks, settings, about }

enum AppThemeMode { system, light, dark }

class AppState extends ChangeNotifier {
  AppState(this._preferences)
      : _themeMode = AppThemeMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_themeKey),
          orElse: () => AppThemeMode.system,
        ),
        _backendUrl = _preferences.getString(_backendKey) ?? _defaultBackendUrl,
        _ttsVoice = _readTtsVoice(_preferences) {
    _themeModeListenable = ValueNotifier<ThemeMode>(fluentThemeMode);
  }

  static const _themeKey = 'qingjuan.theme';
  static const _backendKey = 'qingjuan.backendUrl';
  static const _ttsVoiceKey = 'qingjuan.ttsVoice';
  static const _defaultBackendUrl = 'http://127.0.0.1:19453';

  final SharedPreferences _preferences;
  AppSection _section = AppSection.library;
  AppThemeMode _themeMode;
  late final ValueNotifier<ThemeMode> _themeModeListenable;
  String _backendUrl;
  TtsVoice? _ttsVoice;
  String? _notice;

  AppSection get section => _section;
  AppThemeMode get themeMode => _themeMode;
  String get backendUrl => _backendUrl;
  TtsVoice? get ttsVoice => _ttsVoice;
  String? get notice => _notice;
  ValueListenable<ThemeMode> get themeModeListenable => _themeModeListenable;

  ThemeMode get fluentThemeMode => switch (_themeMode) {
        AppThemeMode.system => ThemeMode.system,
        AppThemeMode.light => ThemeMode.light,
        AppThemeMode.dark => ThemeMode.dark,
      };

  void selectSection(AppSection value) {
    if (_section == value) return;
    _section = value;
    notifyListeners();
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
