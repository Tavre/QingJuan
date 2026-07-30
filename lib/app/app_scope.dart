import 'package:flutter/widgets.dart';

import '../core/api/api_client.dart';
import '../core/backend/backend_process_manager.dart';
import '../features/library/library_controller.dart';
import '../features/settings/settings_controller.dart';
import '../features/sources/sources_controller.dart';
import '../features/tasks/tasks_controller.dart';
import 'app_state.dart';

class AppScope extends InheritedWidget {
  const AppScope({
    required this.appState,
    required this.api,
    required this.backend,
    required this.library,
    required this.sources,
    required this.tasks,
    required this.settings,
    required super.child,
    super.key,
  });

  final AppState appState;
  final ApiClient api;
  final BackendProcessManager backend;
  final LibraryController library;
  final SourcesController sources;
  final TasksController tasks;
  final SettingsController settings;

  static AppScope of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(scope != null, 'AppScope is missing above this context');
    return scope!;
  }

  @override
  bool updateShouldNotify(AppScope oldWidget) {
    return appState != oldWidget.appState || api != oldWidget.api;
  }
}
