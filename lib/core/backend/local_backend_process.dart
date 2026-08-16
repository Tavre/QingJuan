import 'dart:async';
import 'dart:io';

import 'package:path/path.dart' as path;

import '../api/api_client.dart';
import '../api/api_exception.dart';
import '../models/book.dart';

abstract interface class LocalBackendLifecycle {
  Future<JsonMap> ensureRunning(ApiClient api);

  Future<void> openAdmin(Uri uri);

  Future<void> stop();
}

class LocalBackendException implements Exception {
  const LocalBackendException(this.message);

  final String message;

  @override
  String toString() => message;
}

class WindowsLocalBackendLifecycle implements LocalBackendLifecycle {
  WindowsLocalBackendLifecycle({
    LocalBackendCommand? commandOverride,
    Future<void> Function(Duration)? delay,
    bool Function()? isWindows,
    Future<void> Function(Uri uri)? openUri,
  })  : _commandOverride = commandOverride,
        _delay = delay ?? Future<void>.delayed,
        _isWindows = isWindows ?? (() => Platform.isWindows),
        _openUri = openUri;

  static const _readyAttempts = 30;
  static const _readyDelay = Duration(milliseconds: 300);

  final LocalBackendCommand? _commandOverride;
  final Future<void> Function(Duration) _delay;
  final bool Function() _isWindows;
  final Future<void> Function(Uri uri)? _openUri;
  Process? _ownedProcess;

  @override
  Future<JsonMap> ensureRunning(ApiClient api) async {
    if (!_isWindows()) {
      throw const LocalBackendException('当前平台不支持 Windows 本机后端');
    }

    if (await api.health()) {
      try {
        return await api.fetchServiceMeta();
      } catch (error) {
        throw _existingPortError(error);
      }
    }

    await stop();
    final command = _commandOverride ?? resolveLocalBackendCommand();
    if (command == null) {
      throw const LocalBackendException('未找到 Python 后端或随包后端程序');
    }

    try {
      _ownedProcess = await Process.start(
        command.executable,
        command.arguments,
        workingDirectory: command.workingDirectory,
        environment: const <String, String>{
          'QINGJUAN_TRUST_LOCAL_ADMIN': '1',
          'QINGJUAN_AUTH_TOKEN_SHA256': '',
          'QINGJUAN_ADMIN_PASSWORD_HASH': '',
          'QINGJUAN_ADMIN_SESSION_SECRET': '',
          'QINGJUAN_CONNECTION_TOKEN_FILE': '',
          'QINGJUAN_PUBLIC_URL': '',
        },
        mode: ProcessStartMode.normal,
        runInShell: false,
      );
      unawaited(_ownedProcess!.stdout.drain<void>());
      unawaited(_ownedProcess!.stderr.drain<void>());
    } catch (error) {
      throw LocalBackendException('本机后端进程启动失败：$error');
    }

    Object? compatibilityError;
    for (var attempt = 0; attempt < _readyAttempts; attempt++) {
      if (await api.health()) {
        try {
          return await api.fetchServiceMeta();
        } catch (error) {
          compatibilityError = error;
        }
      }
      await _delay(_readyDelay);
    }

    if (compatibilityError != null) {
      throw _existingPortError(compatibilityError);
    }
    throw const LocalBackendException('本机后端启动超时，请检查随包后端或 Python 依赖');
  }

  @override
  Future<void> openAdmin(Uri uri) async {
    if (!_isWindows()) {
      throw const LocalBackendException('当前平台不支持打开 Windows 本机管理界面');
    }
    if (uri.scheme != 'http' ||
        uri.host != '127.0.0.1' ||
        uri.port != 19453 ||
        uri.path != '/admin/' ||
        (uri.fragment.isNotEmpty && uri.fragment != 'settings')) {
      throw const LocalBackendException('拒绝打开非本机青卷管理地址');
    }
    try {
      final openUri = _openUri;
      if (openUri != null) {
        await openUri(uri);
        return;
      }
      await Process.start(
        'explorer.exe',
        <String>[uri.toString()],
        mode: ProcessStartMode.detached,
        runInShell: false,
      );
    } catch (error) {
      throw LocalBackendException('无法打开本机模型设置：$error');
    }
  }

  @override
  Future<void> stop() async {
    final process = _ownedProcess;
    _ownedProcess = null;
    if (process == null) return;

    try {
      await process.exitCode.timeout(Duration.zero);
      return;
    } on TimeoutException {
      // 仍由当前客户端拥有，继续回收整个 PyInstaller 进程树。
    }

    if (Platform.isWindows) {
      try {
        final result = await Process.run(
          'taskkill.exe',
          <String>['/PID', '${process.pid}', '/T', '/F'],
          runInShell: false,
        ).timeout(const Duration(seconds: 3));
        if (result.exitCode == 0) {
          try {
            await process.exitCode.timeout(const Duration(seconds: 2));
          } on TimeoutException {
            // taskkill 已按记录的 PID 回收进程树，不再扩大终止范围。
          }
          return;
        }
      } on Object {
        // 回退到 Process 句柄终止；不按端口扫描或终止外部进程。
      }
    }

    process.kill(ProcessSignal.sigterm);
    try {
      await process.exitCode.timeout(const Duration(seconds: 2));
    } on TimeoutException {
      process.kill(ProcessSignal.sigkill);
    }
  }
}

LocalBackendException _existingPortError(Object error) {
  if (error is ApiException && error.statusCode == 401) {
    return const LocalBackendException(
      '端口 19453 已被启用连接 Token 的青卷后端占用。请先结束该服务，或切换到 Linux 远程模式并填写匹配的 Token。',
    );
  }
  return LocalBackendException(
    '端口 19453 已被其他或不兼容的服务占用：$error',
  );
}

class LocalBackendCommand {
  const LocalBackendCommand(
    this.executable,
    this.arguments, {
    this.workingDirectory,
  });

  final String executable;
  final List<String> arguments;
  final String? workingDirectory;
}

LocalBackendCommand? resolveLocalBackendCommand({
  String? resolvedExecutable,
  String? currentDirectory,
  int? parentPid,
  bool Function(String value)? fileExists,
}) {
  final executablePath = resolvedExecutable ?? Platform.resolvedExecutable;
  final workingPath = currentDirectory ?? Directory.current.absolute.path;
  final ownerPid = parentPid ?? pid;
  final isFile = fileExists ?? (String value) => File(value).existsSync();
  final arguments = <String>[
    'serve',
    '--host',
    '127.0.0.1',
    '--port',
    '19453',
    '--parent-pid',
    '$ownerPid',
  ];

  final executableDirectory = path.dirname(executablePath);
  final packagedCandidates = <String>[
    path.join(executableDirectory, 'backend', 'qingjuan-desktop.exe'),
    path.join(executableDirectory, 'qingjuan-desktop.exe'),
  ];
  for (final candidate in packagedCandidates) {
    if (isFile(candidate)) {
      return LocalBackendCommand(candidate, arguments);
    }
  }

  final visitedDirectories = <String>{};
  for (final searchRoot in <String>[workingPath, executableDirectory]) {
    var current = path.absolute(searchRoot);
    for (var depth = 0; depth < 8; depth++) {
      final normalized = path.normalize(current);
      if (visitedDirectories.add(normalized)) {
        final backend = path.join(normalized, 'python-backend');
        if (isFile(path.join(backend, 'app', 'main.py'))) {
          return LocalBackendCommand(
            'python',
            <String>['-m', 'app.main', ...arguments],
            workingDirectory: backend,
          );
        }
      }
      final parent = path.dirname(normalized);
      if (parent == normalized) break;
      current = parent;
    }
  }
  return null;
}
