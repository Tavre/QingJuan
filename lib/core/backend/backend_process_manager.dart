import 'dart:async';
import 'dart:io';

import 'package:path/path.dart' as path;

import '../api/api_client.dart';

enum BackendStatus { checking, starting, ready, remote, failed }

class BackendProcessManager {
  BackendProcessManager(
    this.api, {
    bool Function()? isRemote,
  }) : _isRemote = isRemote ?? (() => false);

  final ApiClient api;
  final bool Function() _isRemote;
  Process? _process;
  BackendStatus status = BackendStatus.checking;
  String message = '正在检查后端服务';

  Future<void> ensureReady() async {
    status = BackendStatus.checking;
    if (_isRemote()) {
      await _stopOwnedProcess();
      try {
        await api.fetchServiceMeta();
        status = BackendStatus.ready;
        message = '远程后端已连接';
      } catch (error) {
        status = BackendStatus.failed;
        message = '远程后端连接失败：$error';
      }
      return;
    }
    if (await api.health()) {
      try {
        await api.fetchServiceMeta();
        status = BackendStatus.ready;
        message = '后端服务已连接';
      } catch (error) {
        status = BackendStatus.failed;
        message = '本机端口不是兼容的青卷后端：$error';
      }
      return;
    }
    if (!Platform.isWindows) {
      status = BackendStatus.remote;
      message = '请在设置中填写电脑端后端地址';
      return;
    }

    status = BackendStatus.starting;
    message = '正在启动本地后端';
    final command = _resolveBackendCommand();
    if (command == null) {
      status = BackendStatus.failed;
      message = '未找到 Python 后端或随包后端程序';
      return;
    }

    try {
      _process = await Process.start(
        command.executable,
        command.arguments,
        workingDirectory: command.workingDirectory,
        mode: ProcessStartMode.normal,
        runInShell: false,
      );
      unawaited(_process!.stdout.drain<void>());
      unawaited(_process!.stderr.drain<void>());
      for (var attempt = 0; attempt < 30; attempt++) {
        if (await api.health()) {
          try {
            await api.fetchServiceMeta();
            status = BackendStatus.ready;
            message = '本地后端已启动';
            return;
          } catch (_) {
            // 进程可能仍在初始化路由，继续有限轮询。
          }
        }
        await Future<void>.delayed(const Duration(milliseconds: 300));
      }
      status = BackendStatus.failed;
      message = '后端启动超时，请检查 Python 依赖';
    } catch (error) {
      status = BackendStatus.failed;
      message = '后端启动失败：$error';
    }
  }

  _BackendCommand? _resolveBackendCommand() {
    final executableDir = path.dirname(Platform.resolvedExecutable);
    final packagedCandidates = <String>[
      path.join(executableDir, 'backend', 'qingjuan-desktop.exe'),
      path.join(executableDir, 'qingjuan-desktop.exe'),
    ];
    for (final candidate in packagedCandidates) {
      if (File(candidate).existsSync()) {
        return _BackendCommand(
          candidate,
          <String>['--parent-pid', '$pid'],
        );
      }
    }

    Directory current = Directory.current.absolute;
    for (var depth = 0; depth < 8; depth++) {
      final backend = Directory(path.join(current.path, 'python-backend'));
      if (File(path.join(backend.path, 'app', 'main.py')).existsSync()) {
        return _BackendCommand(
          'python',
          <String>[
            '-m',
            'app.main',
            'serve',
            '--host',
            '127.0.0.1',
            '--port',
            '19453',
            '--parent-pid',
            '$pid',
          ],
          workingDirectory: backend.path,
        );
      }
      final parent = current.parent;
      if (parent.path == current.path) break;
      current = parent;
    }
    return null;
  }

  Future<void> dispose() async {
    await _stopOwnedProcess();
  }

  Future<void> _stopOwnedProcess() async {
    final process = _process;
    _process = null;
    if (process != null) {
      process.kill(ProcessSignal.sigterm);
      try {
        await process.exitCode.timeout(const Duration(seconds: 2));
      } on TimeoutException {
        process.kill(ProcessSignal.sigkill);
      }
    }
  }
}

class _BackendCommand {
  const _BackendCommand(this.executable, this.arguments,
      {this.workingDirectory});

  final String executable;
  final List<String> arguments;
  final String? workingDirectory;
}
