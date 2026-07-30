import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:shared_preferences/shared_preferences.dart';

enum AppSection { library, search, sources, tasks, settings, about }

enum AppThemeMode { system, light, dark }

class AppState extends ChangeNotifier {
  AppState(this._preferences)
      : _themeMode = AppThemeMode.values.firstWhere(
          (mode) => mode.name == _preferences.getString(_themeKey),
          orElse: () => AppThemeMode.system,
        ),
        _backendUrl =
            _preferences.getString(_backendKey) ?? _defaultBackendUrl {
    _themeModeListenable = ValueNotifier<ThemeMode>(fluentThemeMode);
  }

  static const _themeKey = 'qingjuan.theme';
  static const _backendKey = 'qingjuan.backendUrl';
  static const _defaultBackendUrl = 'http://127.0.0.1:19453';

  final SharedPreferences _preferences;
  AppSection _section = AppSection.library;
  AppThemeMode _themeMode;
  late final ValueNotifier<ThemeMode> _themeModeListenable;
  String _backendUrl;
  String? _notice;

  AppSection get section => _section;
  AppThemeMode get themeMode => _themeMode;
  String get backendUrl => _backendUrl;
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

  void showNotice(String message) {
    _notice = message;
    notifyListeners();
  }

  void clearNotice() {
    if (_notice == null) return;
    _notice = null;
    notifyListeners();
  }
}
