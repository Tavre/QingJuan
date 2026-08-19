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

  test('site plugin and source switches use dedicated state endpoints',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests.add(request);
        if (request.method == 'GET' && request.url.path.endsWith('/plugins')) {
          return http.Response.bytes(
            utf8.encode(jsonEncode(<Map<String, Object?>>[
              <String, Object?>{
                'id': 'fanqie',
                'name': '番茄小说',
                'description': '站点解析器',
                'category': 'novel',
                'domains': <String>['fanqienovel.com'],
                'bookKinds': <String>['长小说'],
                'tags': <String>['中文'],
                'capabilities': <String>['preview', 'chapter'],
                'version': '1.0.0',
                'enabled': true,
                'defaultEnabled': true,
              },
            ])),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        final decoded = jsonDecode(request.body) as Map<String, dynamic>;
        if (request.url.path.endsWith('/plugins/fanqie')) {
          return http.Response.bytes(
            utf8.encode(jsonEncode(<String, Object?>{
              'id': 'fanqie',
              'name': '番茄小说',
              'description': '站点解析器',
              'category': 'novel',
              'domains': <String>['fanqienovel.com'],
              'bookKinds': <String>['长小说'],
              'tags': <String>['中文'],
              'capabilities': <String>['preview', 'chapter'],
              'version': '1.0.0',
              'enabled': decoded['enabled'],
              'defaultEnabled': true,
            })),
            200,
            headers: <String, String>{'content-type': 'application/json'},
          );
        }
        return http.Response.bytes(
          utf8.encode(jsonEncode(<String, Object?>{
            'id': 'source-1',
            'name': '测试书源',
            'baseUrl': 'https://source.example.test',
            'enabled': decoded['enabled'],
            'supported': true,
            'status': 'online',
          })),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final plugins = await api.fetchSitePlugins();
    final plugin = await api.saveSitePluginEnabled('fanqie', false);
    final source = await api.saveSourceEnabled('source-1', false);

    expect(plugins.single.name, '番茄小说');
    expect(plugin.enabled, isFalse);
    expect(source.enabled, isFalse);
    expect(requests[1].url.path, '/api/v1/plugins/fanqie');
    expect(requests[2].url.path, '/api/v1/sources/source-1/enabled');
    api.close();
  });

  test('qidian account login and bookshelf import use opaque job endpoints',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests.add(request);
        final payload = switch (request.url.path) {
          '/api/v1/plugins/qidian/account/login-qrcode' => <String, Object?>{
              'flowId': 'opaque-flow',
              'qrImageBase64': 'aW1hZ2U=',
              'expiresAt': '2030-01-01T00:03:00Z',
            },
          '/api/v1/plugins/qidian/account/login-qrcode/opaque-flow' =>
            <String, Object?>{
              'status': 'success',
              'message': '登录成功',
              'loggedIn': true,
            },
          '/api/v1/plugins/qidian/bookshelf/import-jobs' => <String, Object?>{
              'id': 'job-1',
              'pluginId': 'qidian',
              'status': 'queued',
              'progress': 0,
              'message': '等待导入',
              'discoveredCount': 0,
              'processedCount': 0,
              'importedCount': 0,
              'skippedCount': 0,
              'unsupportedCount': 0,
              'failedCount': 0,
              'items': <Object?>[],
            },
          '/api/v1/plugins/qidian/bookshelf/import-jobs/job-1' =>
            <String, Object?>{
              'id': 'job-1',
              'pluginId': 'qidian',
              'status': 'completed',
              'progress': 100,
              'message': '导入完成',
              'discoveredCount': 2,
              'processedCount': 2,
              'importedCount': 1,
              'skippedCount': 1,
              'unsupportedCount': 0,
              'failedCount': 0,
              'items': <Map<String, Object?>>[
                <String, Object?>{
                  'sourceId': '1001',
                  'title': '测试作品',
                  'status': 'imported',
                  'message': '已添加',
                  'bookId': 'book-1',
                },
              ],
            },
          _ => throw StateError('Unexpected path: ${request.url.path}'),
        };
        return http.Response.bytes(
          utf8.encode(jsonEncode(payload)),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final qr = await api.startSitePluginLogin('qidian');
    final login = await api.pollSitePluginLogin('qidian', qr.flowId);
    final queued = await api.startSitePluginBookshelfImport('qidian');
    final completed =
        await api.fetchSitePluginBookshelfImport('qidian', queued.id);

    expect(qr.flowId, 'opaque-flow');
    expect(login.loggedIn, isTrue);
    expect(completed.importedCount, 1);
    expect(completed.skippedCount, 1);
    expect(completed.items.single.bookId, 'book-1');
    expect(requests.map((request) => request.method),
        <String>['POST', 'GET', 'POST', 'GET']);
    expect(
      requests.map((request) => request.url.path),
      <String>[
        '/api/v1/plugins/qidian/account/login-qrcode',
        '/api/v1/plugins/qidian/account/login-qrcode/opaque-flow',
        '/api/v1/plugins/qidian/bookshelf/import-jobs',
        '/api/v1/plugins/qidian/bookshelf/import-jobs/job-1',
      ],
    );
    expect(requests.map((request) => request.url.toString()).join(),
        isNot(contains('cookie')));
    api.close();
  });

  test('builtin search normalizes Quark results for the shared import model',
      () async {
    late Map<String, dynamic> requestBody;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/builtin-sites/search');
        requestBody = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response.bytes(
          utf8.encode(jsonEncode(<Map<String, Object?>>[
            <String, Object?>{
              'title': '斗罗大陆',
              'author': '唐家三少',
              'synopsis': '公开简介',
              'cover': 'https://img.example.test/cover.jpg',
              'sourceUrl': 'https://www.shuqi.com/book/46543.html',
              'bookKind': '长小说',
            },
          ])),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      }),
    );

    final results = await api.searchBuiltinSite(
      '斗罗大陆',
      sourceId: 'source-builtin-quark',
      sourceName: '夸克小说',
      sourceLanguage: '中文',
    );

    expect(requestBody, <String, Object?>{
      'sourceId': 'source-builtin-quark',
      'keyword': '斗罗大陆',
      'limit': 20,
    });
    expect(results.single.sourceId, 'source-builtin-quark');
    expect(results.single.sourceName, '夸克小说');
    expect(results.single.language, '中文');
    expect(results.single.sourceUrl, 'https://www.shuqi.com/book/46543.html');
    expect(
        results.single.toImportPayload()['sourceId'], 'source-builtin-quark');
    api.close();
  });
}
