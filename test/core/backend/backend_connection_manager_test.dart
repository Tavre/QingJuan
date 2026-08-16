import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/backend/local_backend_process.dart';
import 'package:qingjuan/core/models/settings.dart';

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
    await manager.dispose();
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
    await manager.dispose();
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
    await manager.dispose();
    api.close();
  });

  test('local mode starts the Windows lifecycle without requiring a token',
      () async {
    final api = ApiClient(
      () => 'http://127.0.0.1:19453',
      client: MockClient((request) async {
        fail('fake local lifecycle should provide metadata directly');
      }),
    );
    final lifecycle = _FakeLocalBackendLifecycle(
      meta: <String, dynamic>{
        'service': 'qingjuan-backend',
        'apiVersion': '1',
        'capabilities': <String, dynamic>{},
      },
    );
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => false,
      isLocal: () => true,
      localBackend: lifecycle,
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.ready);
    expect(manager.message, contains('本机后端已连接'));
    expect(lifecycle.ensureCalls, 1);
    await manager.dispose();
    expect(lifecycle.stopCalls, 1);
    api.close();
  });

  test('local startup failure remains local and reports a diagnostic',
      () async {
    final api = ApiClient(() => 'http://127.0.0.1:19453');
    final lifecycle = _FakeLocalBackendLifecycle(
      error: StateError('未找到随包后端'),
    );
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => true,
      isLocal: () => true,
      localBackend: lifecycle,
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.failed);
    expect(manager.message, contains('未找到随包后端'));
    expect(manager.message, isNot(contains('Linux 后端')));
    await manager.dispose();
    api.close();
  });

  test('remote mode stops an owned local process before connecting', () async {
    final api = ApiClient(() => '');
    final lifecycle = _FakeLocalBackendLifecycle();
    final manager = BackendConnectionManager(
      api,
      isConfigured: () => false,
      isLocal: () => false,
      localBackend: lifecycle,
    );

    await manager.ensureReady();

    expect(manager.status, BackendStatus.unconfigured);
    expect(lifecycle.stopCalls, 1);
    await manager.dispose();
    api.close();
  });

  test('ready connection automatically checks the Linux translation model',
      () async {
    final requestedPaths = <String>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      client: MockClient((request) async {
        requestedPaths.add(request.url.path);
        if (request.url.path == '/api/v1/meta') {
          return http.Response(
            '{"service":"qingjuan-backend","apiVersion":"1",'
            '"capabilities":{"translationModelCheck":true}}',
            200,
          );
        }
        expect(request.method, 'POST');
        expect(request.url.queryParameters['force'], 'false');
        return http.Response.bytes(
          utf8.encode(
            '{"enabled":true,"configured":true,"available":true,'
            '"status":"ready","model":"server-model","supportsVision":false,'
            '"checkedAt":"2030-01-01T00:00:00Z","latencyMs":24,'
            '"message":"自检通过","cached":false}',
          ),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final manager = BackendConnectionManager(api, isConfigured: () => true);

    await manager.ensureReady();

    expect(manager.status, BackendStatus.ready);
    expect(manager.translationModelCheck?.status,
        TranslationModelCheckStatus.ready);
    expect(manager.translationModelCheck?.model, 'server-model');
    expect(manager.message, contains('模型自检通过'));
    expect(requestedPaths,
        <String>['/api/v1/meta', '/api/v1/translation-model/check']);
    await manager.dispose();
    api.close();
  });

  test('model check failure keeps reading connection ready with warning',
      () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/meta') {
          return http.Response(
            '{"service":"qingjuan-backend","apiVersion":"1",'
            '"capabilities":{"translationModelCheck":true}}',
            200,
          );
        }
        return http.Response.bytes(
          utf8.encode(
            '{"enabled":true,"configured":true,"available":false,'
            '"status":"failed","model":"server-model","supportsVision":false,'
            '"checkedAt":"2030-01-01T00:00:00Z","latencyMs":null,'
            '"message":"翻译服务自检超时","cached":false}',
          ),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );
    final manager = BackendConnectionManager(api, isConfigured: () => true);

    await manager.ensureReady();

    expect(manager.status, BackendStatus.ready);
    expect(manager.translationModelCheck?.available, isFalse);
    expect(manager.message, contains('翻译服务自检超时'));
    await manager.dispose();
    api.close();
  });
}

class _FakeLocalBackendLifecycle implements LocalBackendLifecycle {
  _FakeLocalBackendLifecycle({this.meta, this.error});

  final Map<String, dynamic>? meta;
  final Object? error;
  int ensureCalls = 0;
  int openAdminCalls = 0;
  int stopCalls = 0;

  @override
  Future<Map<String, dynamic>> ensureRunning(ApiClient api) async {
    ensureCalls += 1;
    if (error != null) throw error!;
    return meta ??
        <String, dynamic>{
          'service': 'qingjuan-backend',
          'apiVersion': '1',
          'capabilities': <String, dynamic>{},
        };
  }

  @override
  Future<void> openAdmin(Uri uri) async {
    openAdminCalls += 1;
  }

  @override
  Future<void> stop() async {
    stopCalls += 1;
  }
}
