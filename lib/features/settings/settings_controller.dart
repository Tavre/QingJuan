import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/models/settings.dart';
import '../../core/state/load_state.dart';

class SettingsController extends ChangeNotifier {
  SettingsController(this.api);

  final ApiClient api;
  LoadState state = LoadState.idle;
  TranslationSettings value = TranslationSettings.defaults();
  String? error;
  bool saving = false;
  int _contextGeneration = 0;
  bool _disposed = false;

  void resetForBackendSwitch() {
    _contextGeneration += 1;
    state = LoadState.idle;
    value = TranslationSettings.defaults();
    error = null;
    saving = false;
    notifyListeners();
  }

  Future<void> load() async {
    final generation = _contextGeneration;
    state = LoadState.loading;
    error = null;
    notifyListeners();
    try {
      final loaded = await api.fetchSettings();
      if (_disposed || generation != _contextGeneration) return;
      value = loaded;
      state = LoadState.ready;
    } catch (exception) {
      if (_disposed || generation != _contextGeneration) return;
      error = '$exception';
      state = LoadState.error;
    }
    if (!_disposed && generation == _contextGeneration) notifyListeners();
  }

  void update(TranslationSettings next) {
    value = next;
    notifyListeners();
  }

  Future<void> save() async {
    final generation = _contextGeneration;
    saving = true;
    error = null;
    notifyListeners();
    try {
      final saved = await api.saveSettings(value);
      if (_disposed || generation != _contextGeneration) return;
      value = saved;
      state = LoadState.ready;
    } catch (exception) {
      if (_disposed || generation != _contextGeneration) return;
      error = '$exception';
      rethrow;
    } finally {
      if (!_disposed && generation == _contextGeneration) {
        saving = false;
        notifyListeners();
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
