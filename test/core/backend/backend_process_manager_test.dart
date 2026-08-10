import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_process_manager.dart';

void main() {
  test('remote connection failure never falls back to a local process',
      () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'invalid-token',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/meta');
        return http.Response('{"detail":"连接凭据无效"}', 401);
      }),
    );
    final manager = BackendProcessManager(api, isRemote: () => true);

    await manager.ensureReady();

    expect(manager.status, BackendStatus.failed);
    expect(manager.message, contains('远程后端连接失败'));
    await manager.dispose();
    api.close();
  });
}
