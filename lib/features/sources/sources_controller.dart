import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/models/source.dart';
import '../../core/state/load_state.dart';

class SourcesController extends ChangeNotifier {
  SourcesController(this.api);

  final ApiClient api;
  LoadState state = LoadState.idle;
  List<BookSource> sources = const [];
  List<SourceSearchResult> results = const [];
  bool searching = false;
  String? error;

  void resetForBackendSwitch() {
    sources = const [];
    results = const [];
    searching = false;
    error = null;
    state = LoadState.idle;
    notifyListeners();
  }

  Future<void> load() async {
    state = LoadState.loading;
    error = null;
    notifyListeners();
    try {
      sources = await api.fetchSources();
      state = sources.isEmpty ? LoadState.empty : LoadState.ready;
    } catch (exception) {
      error = '$exception';
      state = LoadState.error;
    }
    notifyListeners();
  }

  Future<void> search(String keyword) async {
    final normalized = keyword.trim();
    if (normalized.isEmpty) return;
    searching = true;
    error = null;
    results = const [];
    notifyListeners();
    try {
      final enabledIds = sources
          .where((source) => source.enabled)
          .map((source) => source.id)
          .toList();
      results = await api.searchSources(normalized, sourceIds: enabledIds);
    } catch (exception) {
      error = '$exception';
    } finally {
      searching = false;
      notifyListeners();
    }
  }

  Future<SourceImportResult> importUrl(String url) async {
    final result = await api.importSourcesFromUrl(url.trim());
    await load();
    return result;
  }

  Future<SourceImportResult> importText(String content) async {
    final result = await api.importSourcesFromText(content);
    await load();
    return result;
  }
}
