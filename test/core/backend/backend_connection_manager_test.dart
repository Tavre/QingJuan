import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';

void main() {
  test('unconfigured client does not make a network request', () async {
    final api = ApiClient(
      () => '',
      client: MockClient((request) async {
        fail('unconfigured client must not request ${request.url}');
      }),
    );
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => false,
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.unconfigured);
    expect(manager.message, contains('Linux 后端'));
    api.close();
  });

  test('connection failure never falls back to a local process', () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'invalid-token',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/meta');
        return http.Response('{"detail":"连接凭据无效"}', 401);
      }),
    );
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => true,
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.failed);
    expect(manager.message, contains('Linux 后端连接失败'));
    api.close();
  });

  test('invalid persisted address fails before making a request', () async {
    final api = ApiClient(
      () => 'http://127.0.0.1:19453',
      client: MockClient((request) async {
        fail('invalid address must not request ${request.url}');
      }),
    );
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => true,
      validateConfiguration: () => throw const FormatException('不能使用手机回环地址'),
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.failed);
    expect(manager.message, contains('不能使用手机回环地址'));
    api.close();
  });
}
