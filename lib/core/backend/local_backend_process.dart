import 'dart:async';
import 'dart:io';

import 'package:path/path.dart' as path;

import '../api/api_client.dart';
import '../models/book.dart';

abstract interface class LocalBackendLifecycle {
  Future<JsonMap> ensureRunning(ApiClient api);

  Future<void> stop();
}

class WindowsLocalBackendLifecycle implements LocalBackendLifecycle {
  WindowsLocalBackendLifecycle({
    LocalBackendCommand? commandOverride,
    Future<void> Function(Duration)? delay,
  })  : _commandOverride = commandOverride,
        _delay = delay ?? Future<void>.delayed;

  static const _readyAttempts = 30;
  static const _readyDelay = Duration(milliseconds: 300);

  final LocalBackendCommand? _commandOverride;
  final Future<void> Function(Duration) _delay;
  Process? _ownedProcess;

  @override
  Future<JsonMap> ensureRunning(ApiClient api) async {
    if (!Platform.isWindows) {
      throw StateError('当前平台不支持 Windows 本机后端');
    }

    if (await api.health()) {
      try {
        return await api.fetchServiceMeta();
      } catch (error) {
        throw StateError('本机端口不是兼容的青卷后端：$error');
      }
    }

    await stop();
    final command = _commandOverride ?? resolveLocalBackendCommand();
    if (command == null) {
      throw StateError('未找到 Python 后端或随包后端程序');
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
      throw StateError('本机后端启动失败：$error');
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
      throw StateError('本机端口不是兼容的青卷后端：$compatibilityError');
    }
    throw StateError('本机后端启动超时，请检查随包后端或 Python 依赖');
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

  var current = path.absolute(workingPath);
  for (var depth = 0; depth < 8; depth++) {
    final backend = path.join(current, 'python-backend');
    if (isFile(path.join(backend, 'app', 'main.py'))) {
      return LocalBackendCommand(
        'python',
        <String>['-m', 'app.main', ...arguments],
        workingDirectory: backend,
      );
    }
    final parent = path.dirname(current);
    if (parent == current) break;
    current = parent;
  }
  return null;
}
