import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as path;
import 'package:qingjuan/core/api/api_client.dart';
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

  test('source checkout is found from the executable when cwd is unrelated',
      () {
    final root = path.absolute(path.join('workspace', 'qingjuan'));
    final backend = path.join(root, 'python-backend');
    final entrypoint = path.join(backend, 'app', 'main.py');

    final command = resolveLocalBackendCommand(
      resolvedExecutable: path.join(
        root,
        'build',
        'windows',
        'x64',
        'runner',
        'Release',
        'qingjuan.exe',
      ),
      currentDirectory: path.absolute(path.join('unrelated', 'launcher')),
      parentPid: 126,
      fileExists: (value) => value == entrypoint,
    );

    expect(command, isNotNull);
    expect(command!.executable, 'python');
    expect(command.workingDirectory, backend);
    expect(command.arguments, contains('--parent-pid'));
    expect(command.arguments, contains('126'));
  });

  test('missing packaged and source backends return no command', () {
    final command = resolveLocalBackendCommand(
      resolvedExecutable: path.join('missing', 'qingjuan.exe'),
      currentDirectory: path.join('missing', 'client'),
      fileExists: (_) => false,
    );

    expect(command, isNull);
  });

  test('authenticated QingJuan service on the local port is actionable',
      () async {
    final api = ApiClient(
      () => 'http://127.0.0.1:19453',
      client: MockClient((request) async {
        if (request.url.path == '/healthz') {
          return http.Response('{"status":"ok"}', 200);
        }
        expect(request.url.path, '/api/v1/meta');
        return http.Response('{"detail":"invalid token"}', 401);
      }),
    );
    final lifecycle = WindowsLocalBackendLifecycle(isWindows: () => true);
    addTearDown(api.close);

    await expectLater(
      lifecycle.ensureRunning(api),
      throwsA(
        isA<LocalBackendException>()
            .having(
                (error) => error.toString(), 'message', contains('端口 19453'))
            .having(
                (error) => error.toString(), 'message', contains('连接 Token'))
            .having((error) => error.toString(), 'message',
                isNot(contains('Bad state'))),
      ),
    );
  });

  test('local admin launcher only opens the fixed model settings address',
      () async {
    Uri? opened;
    final lifecycle = WindowsLocalBackendLifecycle(
      isWindows: () => true,
      openUri: (uri) async => opened = uri,
    );
    final modelSettings = Uri.parse('http://127.0.0.1:19453/admin/#settings');

    await lifecycle.openAdmin(modelSettings);

    expect(opened, modelSettings);
    await expectLater(
      lifecycle.openAdmin(Uri.parse('https://example.test/admin/#settings')),
      throwsA(
        isA<LocalBackendException>().having(
          (error) => error.toString(),
          'message',
          contains('拒绝打开'),
        ),
      ),
    );
  });
}
