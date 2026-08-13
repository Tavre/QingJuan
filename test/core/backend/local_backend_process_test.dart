import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'package:qingjuan/core/backend/local_backend_process.dart';

void main() {
  test('packaged backend beside the Windows client has priority', () {
    final root = path.join('C:', 'QingJuan');
    final packaged = path.join(root, 'backend', 'qingjuan-desktop.exe');

    final command = resolveLocalBackendCommand(
      resolvedExecutable: path.join(root, 'qingjuan.exe'),
      currentDirectory: path.join(root, 'data'),
      parentPid: 42,
      fileExists: (value) => value == packaged,
    );

    expect(command, isNotNull);
    expect(command!.executable, packaged);
    expect(command.workingDirectory, isNull);
    expect(
      command.arguments,
      <String>[
        'serve',
        '--host',
        '127.0.0.1',
        '--port',
        '19453',
        '--parent-pid',
        '42',
      ],
    );
  });

  test('source checkout uses Python from the backend working directory', () {
    final root = path.absolute(path.join('workspace', 'qingjuan'));
    final backend = path.join(root, 'python-backend');
    final entrypoint = path.join(backend, 'app', 'main.py');

    final command = resolveLocalBackendCommand(
      resolvedExecutable: path.join(root, 'build', 'qingjuan.exe'),
      currentDirectory: path.join(root, 'nested', 'client'),
      parentPid: 84,
      fileExists: (value) => value == entrypoint,
    );

    expect(command, isNotNull);
    expect(command!.executable, 'python');
    expect(command.workingDirectory, backend);
    expect(
        command.arguments,
        containsAllInOrder(<String>[
          '-m',
          'app.main',
          'serve',
          '--host',
          '127.0.0.1',
          '--port',
          '19453',
          '--parent-pid',
          '84',
        ]));
  });

  test('missing packaged and source backends return no command', () {
    final command = resolveLocalBackendCommand(
      resolvedExecutable: path.join('missing', 'qingjuan.exe'),
      currentDirectory: path.join('missing', 'client'),
      fileExists: (_) => false,
    );

    expect(command, isNull);
  });
}
