import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';

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
