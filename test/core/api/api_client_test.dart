import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/models/settings.dart';

void main() {
  test('Bearer token is limited to the configured QingJuan origin', () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/meta');
        expect(request.headers['Authorization'], 'Bearer connection-token');
        return http.Response(
          jsonEncode(<String, Object?>{
            'service': 'qingjuan-backend',
            'appVersion': '1.3.1',
            'apiVersion': '1',
            'instanceId': 'instance-1',
            'capabilities': <String, bool>{'rapidOcr': true},
          }),
          200,
        );
      }),
    );

    await api.fetchServiceMeta();

    expect(
      api.headersForUrl('/books/book-1/assets/cover.jpg'),
      <String, String>{'Authorization': 'Bearer connection-token'},
    );
    expect(
      api.headersForUrl('https://images.example.test/cover.jpg'),
      isEmpty,
    );
    api.close();
  });

  test('Bearer token supports a backend mounted below a URL path', () {
    final api = ApiClient(
      () => 'https://gateway.example.test/qingjuan',
      token: () => 'connection-token',
    );

    expect(
      api.headersForUrl('/books/book-1/assets/cover.jpg'),
      <String, String>{'Authorization': 'Bearer connection-token'},
    );
    expect(
      api.headersForUrl('https://gateway.example.test/api/v1/books/book-1'),
      isEmpty,
    );
    api.close();
  });

  test('device identity headers are limited to the configured backend origin',
      () async {
    const deviceHeaders = <String, String>{
      'X-QingJuan-Device-ID': '0123456789abcdef0123456789abcdef',
      'X-QingJuan-Device-Name': 'Windows%20reader',
      'X-QingJuan-Device-Platform': 'windows',
    };
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      deviceHeaders: () => deviceHeaders,
      client: MockClient((request) async {
        expect(request.headers['X-QingJuan-Device-ID'],
            deviceHeaders['X-QingJuan-Device-ID']);
        return http.Response(
          jsonEncode(<String, Object?>{
            'service': 'qingjuan-backend',
            'appVersion': '1.4.0',
            'apiVersion': '1',
            'instanceId': 'instance-1',
            'capabilities': <String, bool>{'deviceRegistry': true},
          }),
          200,
        );
      }),
    );

    await api.fetchServiceMeta();

    expect(
      api.headersForUrl('/books/book-1/assets/cover.jpg'),
      <String, String>{
        'Authorization': 'Bearer connection-token',
        ...deviceHeaders,
      },
    );
    expect(api.headersForUrl('https://images.example.test/cover.jpg'), isEmpty);
    api.close();
  });

  test('translation model check uses the authenticated Linux backend',
      () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/translation-model/check');
        expect(request.url.queryParameters['force'], 'false');
        expect(request.headers['Authorization'], 'Bearer connection-token');
        return http.Response.bytes(
          utf8.encode(jsonEncode(<String, Object?>{
            'enabled': true,
            'configured': true,
            'available': true,
            'status': 'ready',
            'model': 'server-model',
            'supportsVision': false,
            'checkedAt': '2030-01-01T00:00:00Z',
            'latencyMs': 16,
            'message': '自检通过',
            'cached': false,
          })),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final result = await api.checkTranslationModel();

    expect(result.status, TranslationModelCheckStatus.ready);
    expect(result.available, isTrue);
    expect(result.model, 'server-model');
    expect(result.latencyMs, 16);
    api.close();
  });

  test('task page results are fetched incrementally by sequence', () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/tasks/task-1/page-results');
        expect(request.url.queryParameters['after'], '7');
        return http.Response(
          jsonEncode(<Map<String, Object?>>[
            <String, Object?>{
              'sequence': 8,
              'taskId': 'task-1',
              'chapterIndex': 1,
              'chapterTitle': '第一话',
              'pageNumber': 1,
              'totalPages': 2,
              'texts': <Map<String, Object?>>[
                <String, Object?>{
                  'order': 1,
                  'sourceText': 'こんにちは',
                  'translation': '你好',
                },
              ],
            },
          ]),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final results = await api.fetchTaskPageResults('task-1', after: 7);

    expect(results.single.sequence, 8);
    expect(results.single.displayText, 'こんにちは → 你好');
    api.close();
  });
}
