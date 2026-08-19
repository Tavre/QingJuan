import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/features/library/library_controller.dart';

void main() {
  test('search import uses an asynchronous link job instead of sync import',
      () async {
    final requests = <http.Request>[];
    var jobPolls = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'POST' &&
            request.url.path == '/api/v1/books/link-jobs') {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          expect(body['mode'], 'import');
          expect(
            (body['payload'] as Map<String, dynamic>)['downloadMode'],
            'on_demand',
          );
          return _jsonResponse(_job(status: 'queued'));
        }
        if (request.method == 'GET' &&
            request.url.path == '/api/v1/books/link-jobs/link-1') {
          jobPolls += 1;
          return _jsonResponse(
            _job(
              status: jobPolls == 1 ? 'running' : 'completed',
              book: jobPolls == 1 ? null : _book,
            ),
          );
        }
        if (request.method == 'GET' && request.url.path == '/api/v1/books') {
          return _jsonResponse(<Map<String, Object?>>[_book]);
        }
        return _jsonResponse(<String, Object?>{'detail': 'unexpected'}, 404);
      }),
    );
    final controller = LibraryController(api);
    addTearDown(() {
      controller.dispose();
      api.close();
    });

    final book = await controller.importFromSearch(
      <String, dynamic>{
        'sourceUrl': 'https://www.shuqi.com/book/46543.html',
        'bookKind': '长小说',
        'language': '中文',
        'sourceId': 'source-builtin-quark',
        'downloadMode': 'on_demand',
      },
      pollInterval: Duration.zero,
    );

    expect(book.id, 'book-1');
    expect(
      requests.where((request) => request.url.path == '/api/v1/books/import'),
      isEmpty,
    );
    expect(jobPolls, 2);
  });
}

const _book = <String, Object?>{
  'id': 'book-1',
  'title': '斗罗大陆',
  'sourceUrl': 'https://www.shuqi.com/book/46543.html',
  'bookKind': '长小说',
  'language': '中文',
  'status': '待处理',
  'chapterCount': 1,
  'translated': false,
  'localPath': 'library/book-1',
  'updatedAt': '2026-08-19T12:00:00Z',
  'synopsis': '公开简介',
};

Map<String, Object?> _job({
  required String status,
  Map<String, Object?>? book,
}) =>
    <String, Object?>{
      'id': 'link-1',
      'mode': 'import',
      'status': status,
      'progress': status == 'completed' ? 100 : 40,
      'message': status == 'completed' ? '链接导入完成' : '正在解析目录',
      'logs': <Object?>[],
      'book': book,
      'createdAt': '2026-08-19T12:00:00Z',
      'updatedAt': '2026-08-19T12:00:01Z',
    };

http.Response _jsonResponse(Object body, [int statusCode = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: const <String, String>{'content-type': 'application/json'},
    );
