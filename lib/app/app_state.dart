import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/foundation.dart' show ValueListenable, ValueNotifier;
import 'package:shared_preferences/shared_preferences.dart';

import '../core/backend/connection_secret_store.dart';
import '../core/models/tts_speech_style.dart';
import '../core/models/tts_voice.dart';

enum AppSection { library, search, sources, tasks, settings, about }

enum AppThemeMode { system, light, dark }

enum ReaderFlowMode { paged, continuous }

enum ReaderPaletteMode { white, parchment, eyeCare, mist, night }

enum ReaderPageAnimation { cover, slide, fade, none }

enum ReaderLineSpacing { compact, standard, relaxed }

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
        _backendUrl = _preferences.getString(_backendKey)?.trim() ?? '',
        _backendToken = initialBackendToken,
        _ttsVoice = _readTtsVoice(_preferences),
        _ttsSpeechStyle = parseTtsSpeechStyle(
          _preferences.getString(_ttsSpeechStyleKey),
        ),
        _readerFlowMode = ReaderFlowMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_readerFlowModeKey),
          orElse: () => ReaderFlowMode.paged,
        ),
        _readerPaletteMode = ReaderPaletteMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_readerPaletteKey),
          orElse: () => ReaderPaletteMode.parchment,
        ),
        _readerPageAnimation = ReaderPageAnimation.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_readerAnimationKey),
          orElse: () => ReaderPageAnimation.cover,
        ),
        _readerLineSpacing = ReaderLineSpacing.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_readerSpacingKey),
          orElse: () => ReaderLineSpacing.standard,
        ),
        _readerFontSize =
            (_preferences.getDouble(_readerFontSizeKey) ?? 19).clamp(15, 30),
        _volumeKeyReadingEnabled =
            _preferences.getBool(_volumeKeyReadingKey) ?? false {
    _section = hasBackendConnection ? AppSection.library : AppSection.settings;
    _sectionListenable = ValueNotifier<AppSection>(_section);
    _themeModeListenable = ValueNotifier<ThemeMode>(fluentThemeMode);
  }

  static const _themeKey = 'qingjuan.theme';
  static const _backendKey = 'qingjuan.backendUrl';
  static const _ttsVoiceKey = 'qingjuan.ttsVoice';
  static const _ttsSpeechStyleKey = 'qingjuan.ttsSpeechStyle';
  static const _readerFlowModeKey = 'qingjuan.readerFlowMode';
  static const _readerPaletteKey = 'qingjuan.readerPalette';
  static const _readerAnimationKey = 'qingjuan.readerPageAnimation';
  static const _readerSpacingKey = 'qingjuan.readerLineSpacing';
  static const _readerFontSizeKey = 'qingjuan.readerFontSize';
  static const _volumeKeyReadingKey = 'qingjuan.volumeKeyReading';

  final SharedPreferences _preferences;
  final ConnectionSecretStore? _secretStore;
  late AppSection _section;
  late final ValueNotifier<AppSection> _sectionListenable;
  AppThemeMode _themeMode;
  late final ValueNotifier<ThemeMode> _themeModeListenable;
  String _backendUrl;
  String _backendToken;
  TtsVoice? _ttsVoice;
  TtsSpeechStyle _ttsSpeechStyle;
  ReaderFlowMode _readerFlowMode;
  ReaderPaletteMode _readerPaletteMode;
  ReaderPageAnimation _readerPageAnimation;
  ReaderLineSpacing _readerLineSpacing;
  double _readerFontSize;
  bool _volumeKeyReadingEnabled;
  String? _notice;

  AppSection get section => _section;
  AppThemeMode get themeMode => _themeMode;
  String get backendUrl => _backendUrl;
  String get backendToken => _backendToken;
  bool get hasBackendConnection =>
      _backendUrl.isNotEmpty && _backendToken.isNotEmpty;
  TtsVoice? get ttsVoice => _ttsVoice;
  TtsSpeechStyle get ttsSpeechStyle => _ttsSpeechStyle;
  ReaderFlowMode get readerFlowMode => _readerFlowMode;
  ReaderPaletteMode get readerPaletteMode => _readerPaletteMode;
  ReaderPageAnimation get readerPageAnimation => _readerPageAnimation;
  ReaderLineSpacing get readerLineSpacing => _readerLineSpacing;
  double get readerFontSize => _readerFontSize;
  bool get volumeKeyReadingEnabled => _volumeKeyReadingEnabled;
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

  Future<void> setBackendConnection({
    required String url,
    required String token,
  }) async {
    final normalized = url.trim().replaceAll(RegExp(r'/+$'), '');
    if (normalized.isEmpty) return;
    final normalizedToken = token.trim();
    final secretStore = _secretStore;
    if (secretStore != null) {
      if (normalizedToken.isEmpty) {
        await secretStore.deleteToken();
      } else {
        await secretStore.writeToken(normalizedToken);
      }
    }
    await _preferences.setString(_backendKey, normalized);
    await _preferences.remove('qingjuan.backendMode');
    _backendUrl = normalized;
    _backendToken = normalizedToken;
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

  Future<void> setReaderFlowMode(ReaderFlowMode value) async {
    if (_readerFlowMode == value) return;
    _readerFlowMode = value;
    notifyListeners();
    await _preferences.setString(_readerFlowModeKey, value.name);
  }

  Future<void> setReaderPaletteMode(ReaderPaletteMode value) async {
    if (_readerPaletteMode == value) return;
    _readerPaletteMode = value;
    notifyListeners();
    await _preferences.setString(_readerPaletteKey, value.name);
  }

  Future<void> setReaderPageAnimation(ReaderPageAnimation value) async {
    if (_readerPageAnimation == value) return;
    _readerPageAnimation = value;
    notifyListeners();
    await _preferences.setString(_readerAnimationKey, value.name);
  }

  Future<void> setReaderLineSpacing(ReaderLineSpacing value) async {
    if (_readerLineSpacing == value) return;
    _readerLineSpacing = value;
    notifyListeners();
    await _preferences.setString(_readerSpacingKey, value.name);
  }

  Future<void> setReaderFontSize(double value) async {
    final normalized = value.clamp(15, 30).toDouble();
    if (_readerFontSize == normalized) return;
    _readerFontSize = normalized;
    notifyListeners();
    await _preferences.setDouble(_readerFontSizeKey, normalized);
  }

  Future<void> setVolumeKeyReadingEnabled(bool value) async {
    if (_volumeKeyReadingEnabled == value) return;
    _volumeKeyReadingEnabled = value;
    notifyListeners();
    await _preferences.setBool(_volumeKeyReadingKey, value);
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
