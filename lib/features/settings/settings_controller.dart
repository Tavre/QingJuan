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

  Future<void> load() async {
    state = LoadState.loading;
    error = null;
    notifyListeners();
    try {
      value = await api.fetchSettings();
      state = LoadState.ready;
    } catch (exception) {
      error = '$exception';
      state = LoadState.error;
    }
    notifyListeners();
  }

  void update(TranslationSettings next) {
    value = next;
    notifyListeners();
  }

  Future<void> save() async {
    saving = true;
    error = null;
    notifyListeners();
    try {
      value = await api.saveSettings(value);
      state = LoadState.ready;
    } catch (exception) {
      error = '$exception';
      rethrow;
    } finally {
      saving = false;
      notifyListeners();
    }
  }
}
