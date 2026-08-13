import 'dart:async';
import 'dart:io';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api/api_client.dart';
import '../core/backend/backend_connection_manager.dart';
import '../core/backend/backend_url_validator.dart';
import '../core/backend/connection_secret_store.dart';
import '../core/backend/device_identity.dart';
import '../core/backend/local_backend_process.dart';
import '../features/library/library_controller.dart';
import '../features/settings/settings_controller.dart';
import '../features/shell/app_shell.dart';
import '../features/sources/sources_controller.dart';
import '../features/tasks/tasks_controller.dart';
import 'app_scope.dart';
import 'app_state.dart';
import 'app_theme.dart';

class QingJuanApp extends StatefulWidget {
  const QingJuanApp._({
    required this.appState,
    required this.api,
    required this.backend,
    required this.library,
    required this.sources,
    required this.tasks,
    required this.settings,
  });

  static Future<QingJuanApp> bootstrap() async {
    final preferences = await SharedPreferences.getInstance();
    const secretStore = SecureConnectionSecretStore();
    final token = await secretStore.readToken() ?? '';
    final deviceIdentity = await DeviceIdentity.load(preferences);
    final appState = AppState(
      preferences,
      secretStore: secretStore,
      initialRemoteBackendToken: token,
      localBackendSupported: Platform.isWindows,
    );
    final api = ApiClient(
      () => appState.backendUrl,
      token: () => appState.backendToken,
      deviceHeaders: () => deviceIdentity.headers,
    );
    final backend = BackendConnectionManager(
      api,
      isConfigured: () => appState.hasBackendConnection,
      isLocal: () => appState.connectionMode == BackendConnectionMode.local,
      localBackend: Platform.isWindows ? WindowsLocalBackendLifecycle() : null,
      validateConfiguration: () => validateBackendUrl(appState.backendUrl),
    );
    return QingJuanApp._(
      appState: appState,
      api: api,
      backend: backend,
      library: LibraryController(api),
      sources: SourcesController(api),
      tasks: TasksController(api),
      settings: SettingsController(api),
    );
  }

  final AppState appState;
  final ApiClient api;
  final BackendConnectionManager backend;
  final LibraryController library;
  final SourcesController sources;
  final TasksController tasks;
  final SettingsController settings;

  @override
  State<QingJuanApp> createState() => _QingJuanAppState();
}

class _QingJuanAppState extends State<QingJuanApp> {
  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    await widget.backend.ensureReady();
    widget.appState.showNotice(widget.backend.message);
    if (widget.backend.status == BackendStatus.ready) {
      await Future.wait<void>(<Future<void>>[
        widget.library.load(),
        widget.sources.load(),
        widget.tasks.load(),
        widget.settings.load(),
      ]);
    } else {
      widget.appState.selectSection(AppSection.settings);
    }
  }

  @override
  void dispose() {
    widget.library.dispose();
    widget.sources.dispose();
    widget.tasks.dispose();
    widget.settings.dispose();
    unawaited(widget.backend.dispose());
    widget.api.close();
    widget.appState.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      appState: widget.appState,
      api: widget.api,
      backend: widget.backend,
      library: widget.library,
      sources: widget.sources,
      tasks: widget.tasks,
      settings: widget.settings,
      child: AnimatedBuilder(
        animation: widget.appState.themeModeListenable,
        builder: (context, _) {
          return FluentApp(
            debugShowCheckedModeBanner: false,
            title: '青卷',
            themeMode: widget.appState.themeModeListenable.value,
            theme: buildQingJuanTheme(Brightness.light),
            darkTheme: buildQingJuanTheme(Brightness.dark),
            locale: const Locale('zh', 'CN'),
            supportedLocales: const <Locale>[Locale('zh', 'CN'), Locale('en')],
            localizationsDelegates: const <LocalizationsDelegate<dynamic>>[
              GlobalWidgetsLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            home: const AppShell(),
          );
        },
      ),
    );
  }
}
