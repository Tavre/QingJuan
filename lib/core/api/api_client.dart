import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/book.dart';
import '../models/link_job.dart';
import '../models/settings.dart';
import '../models/site_plugin.dart';
import '../models/source.dart';
import '../models/task.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(
    this._baseUrl, {
    String Function()? token,
    Map<String, String> Function()? deviceHeaders,
    http.Client? client,
  })  : _token = token ?? (() => ''),
        _deviceHeaders = deviceHeaders ?? (() => const <String, String>{}),
        _client = client ?? http.Client();

  static const _apiPrefix = '/api/v1';
  final String Function() _baseUrl;
  final String Function() _token;
  final Map<String, String> Function() _deviceHeaders;
  final http.Client _client;

  Uri _uri(String endpoint, [Map<String, dynamic>? query]) =>
      _uriFor(_baseUrl(), endpoint, query);

  Uri _uriFor(
    String baseUrl,
    String endpoint, [
    Map<String, dynamic>? query,
  ]) {
    final base = baseUrl.replaceAll(RegExp(r'/+$'), '');
    return Uri.parse('$base$_apiPrefix$endpoint').replace(
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
  }

  Map<String, String> _headers({bool json = false, String? token}) {
    final value = (token ?? _token()).trim();
    final headers = <String, String>{
      if (json) 'Content-Type': 'application/json',
    };
    if (value.isNotEmpty) {
      headers['Authorization'] = 'Bearer $value';
      headers.addAll(_deviceHeaders());
    }
    return headers;
  }

  Future<http.Response> _request(
    String method,
    String endpoint, {
    Object? body,
    Map<String, dynamic>? query,
  }) async {
    Object? lastError;
    for (var attempt = 0; attempt < 4; attempt++) {
      try {
        final uri = _uri(endpoint, query);
        final headers = _headers(json: body != null);
        final encoded = body == null ? null : jsonEncode(body);
        final requestFuture = switch (method) {
          'GET' => _client.get(uri, headers: headers),
          'POST' => _client.post(uri, headers: headers, body: encoded),
          'PUT' => _client.put(uri, headers: headers, body: encoded),
          'DELETE' => _client.delete(uri, headers: headers, body: encoded),
          _ => throw UnsupportedError('Unsupported HTTP method: $method'),
        };
        final response =
            await requestFuture.timeout(const Duration(minutes: 2));
        return response;
      } on SocketException catch (error) {
        lastError = error;
      } on http.ClientException catch (error) {
        lastError = error;
      } on TimeoutException catch (error) {
        lastError = error;
      }
      if (attempt < 3) {
        await Future<void>.delayed(
            Duration(milliseconds: 250 * (1 << attempt)));
      }
    }
    throw ApiException('无法连接青卷后端：${lastError ?? '网络不可用'}');
  }

  dynamic _decode(http.Response response) {
    dynamic payload;
    try {
      payload = response.bodyBytes.isEmpty
          ? null
          : jsonDecode(utf8.decode(response.bodyBytes));
    } on FormatException {
      payload = utf8.decode(response.bodyBytes);
    }
    if (response.statusCode >= 200 && response.statusCode < 300) return payload;
    final detail = payload is Map ? payload['detail'] : payload;
    final message = switch (detail) {
      String value when value.trim().isNotEmpty => value,
      List value =>
        value.map((entry) => entry is Map ? entry['msg'] : entry).join('\n'),
      _ => '请求失败（HTTP ${response.statusCode}）',
    };
    throw ApiException(message, statusCode: response.statusCode);
  }

  List<JsonMap> _list(dynamic payload) => (payload as List? ?? const [])
      .whereType<Map>()
      .map((item) => Map<String, dynamic>.from(item))
      .toList();

  JsonMap _map(dynamic payload) => Map<String, dynamic>.from(payload as Map);

  Future<bool> health() async {
    try {
      final response = await _client
          .get(
              Uri.parse('${_baseUrl().replaceAll(RegExp(r'/+$'), '')}/healthz'))
          .timeout(const Duration(seconds: 2));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<JsonMap> fetchServiceMeta() async {
    final payload = _decode(await _request('GET', '/meta'));
    final meta = _map(payload);
    if (meta['service'] != 'qingjuan-backend' || meta['apiVersion'] != '1') {
      throw const ApiException('目标服务不是兼容的青卷后端');
    }
    return meta;
  }

  Future<void> sendDeviceHeartbeat() async {
    _decode(await _request('POST', '/devices/heartbeat'));
  }

  Future<JsonMap> testConnection({
    required String baseUrl,
    required String token,
  }) async {
    final response = await _client
        .get(
          _uriFor(baseUrl, '/meta'),
          headers: _headers(token: token),
        )
        .timeout(const Duration(seconds: 8));
    final meta = _map(_decode(response));
    if (meta['service'] != 'qingjuan-backend' || meta['apiVersion'] != '1') {
      throw const ApiException('目标服务不是兼容的青卷后端');
    }
    return meta;
  }

  Future<TranslationModelCheck> checkTranslationModel({
    bool force = false,
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/translation-model/check',
        query: <String, dynamic>{'force': force},
      ),
    );
    return TranslationModelCheck.fromJson(_map(payload));
  }

  Future<List<Book>> fetchBooks() async {
    final payload = _decode(await _request('GET', '/books'));
    return _list(payload).map(Book.fromJson).toList();
  }

  Future<BookDetail> fetchBookDetail(String bookId) async {
    final payload = _decode(await _request('GET', '/books/$bookId'));
    return BookDetail.fromJson(_map(payload));
  }

  Future<ChapterContent> fetchChapter(
    String bookId,
    int chapterIndex, {
    String mode = 'translated',
  }) async {
    final payload = _decode(
      await _request('GET', '/books/$bookId/chapters/$chapterIndex',
          query: <String, dynamic>{'mode': mode}),
    );
    final chapter = ChapterContent.fromJson(_map(payload));
    final normalizedImages = chapter.imageSources.map(resolveUrl).toList();
    return ChapterContent(
      chapter: chapter.chapter,
      content: chapter.content,
      paragraphs: chapter.paragraphs,
      mode: chapter.mode,
      translatedAvailable: chapter.translatedAvailable,
      imageSources: normalizedImages,
      pageTranslations: chapter.pageTranslations,
    );
  }

  Future<BookPreview> previewBook(JsonMap payload) async {
    final response =
        _decode(await _request('POST', '/books/preview', body: payload));
    return BookPreview.fromJson(_map(response));
  }

  Future<LinkJob> startLinkJob(String mode, JsonMap payload) async {
    final response = _decode(
      await _request(
        'POST',
        '/books/link-jobs',
        body: <String, dynamic>{'mode': mode, 'payload': payload},
      ),
    );
    return LinkJob.fromJson(_map(response));
  }

  Future<LinkJob> fetchLinkJob(String jobId) async {
    final response = _decode(await _request('GET', '/books/link-jobs/$jobId'));
    return LinkJob.fromJson(_map(response));
  }

  Future<Book> importBook(JsonMap payload) async {
    final response =
        _decode(await _request('POST', '/books/import', body: payload));
    return Book.fromJson(_map(response));
  }

  Future<Book> importLocalBook({
    required String filePath,
    required String kind,
    required String language,
    required bool translate,
    String? title,
    void Function(int sentBytes, int totalBytes)? onProgress,
  }) async {
    final multipart = http.MultipartRequest('POST', _uri('/books/import-local'))
      ..headers.addAll(_headers())
      ..fields['bookKind'] = kind
      ..fields['language'] = language
      ..fields['needTranslation'] = '$translate';
    if (title != null && title.trim().isNotEmpty) {
      multipart.fields['title'] = title.trim();
    }
    multipart.files.add(
      await http.MultipartFile.fromPath('file', filePath),
    );
    final totalBytes = multipart.contentLength;
    final body = multipart.finalize();
    final request = http.StreamedRequest('POST', multipart.url)
      ..headers.addAll(multipart.headers);
    final responseFuture =
        _client.send(request).timeout(const Duration(minutes: 30));
    var sentBytes = 0;
    await for (final chunk in body) {
      request.sink.add(chunk);
      sentBytes += chunk.length;
      onProgress?.call(sentBytes, totalBytes);
    }
    await request.sink.close();
    final streamed = await responseFuture;
    final response = await http.Response.fromStream(streamed);
    return Book.fromJson(_map(_decode(response)));
  }

  Future<void> deleteBook(String bookId) async {
    _decode(await _request('DELETE', '/books/$bookId'));
  }

  Future<void> saveProgress(
      String bookId, int chapterIndex, double ratio) async {
    _decode(
      await _request(
        'PUT',
        '/books/$bookId/progress',
        body: <String, dynamic>{
          'chapterIndex': chapterIndex,
          'scrollRatio': ratio
        },
      ),
    );
  }

  Future<List<BookSource>> fetchSources() async {
    final payload = _decode(await _request('GET', '/sources'));
    return _list(payload).map(BookSource.fromJson).toList();
  }

  Future<List<SitePlugin>> fetchSitePlugins() async {
    final payload = _decode(await _request('GET', '/plugins'));
    return _list(payload).map(SitePlugin.fromJson).toList();
  }

  Future<SitePlugin> saveSitePluginEnabled(
      String pluginId, bool enabled) async {
    final payload = _decode(
      await _request(
        'PUT',
        '/plugins/${Uri.encodeComponent(pluginId)}',
        body: <String, dynamic>{'enabled': enabled},
      ),
    );
    return SitePlugin.fromJson(_map(payload));
  }

  Future<SitePluginAccount> fetchSitePluginAccount(String pluginId) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final payload =
        _decode(await _request('GET', '/plugins/$encodedId/account'));
    return SitePluginAccount.fromJson(_map(payload));
  }

  Future<SitePluginLoginQrCode> startSitePluginLogin(String pluginId) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final payload = _decode(
      await _request('POST', '/plugins/$encodedId/account/login-qrcode'),
    );
    return SitePluginLoginQrCode.fromJson(_map(payload));
  }

  Future<SitePluginLoginPoll> pollSitePluginLogin(
    String pluginId,
    String flowId,
  ) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final encodedFlowId = Uri.encodeComponent(flowId);
    final payload = _decode(
      await _request(
        'GET',
        '/plugins/$encodedId/account/login-qrcode/$encodedFlowId',
      ),
    );
    return SitePluginLoginPoll.fromJson(_map(payload));
  }

  Future<SitePluginAccount> logoutSitePluginAccount(String pluginId) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final payload =
        _decode(await _request('DELETE', '/plugins/$encodedId/account'));
    return SitePluginAccount.fromJson(_map(payload));
  }

  Future<SitePluginAccount> loginSitePluginWithCookies(
    String pluginId,
    String cookies,
  ) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final payload = _decode(
      await _request(
        'POST',
        '/plugins/$encodedId/account/login-cookies',
        body: <String, dynamic>{'cookies': cookies},
      ),
    );
    return SitePluginAccount.fromJson(_map(payload));
  }

  Future<SitePluginBookshelfImportJob> startSitePluginBookshelfImport(
    String pluginId,
  ) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final payload = _decode(
      await _request('POST', '/plugins/$encodedId/bookshelf/import-jobs'),
    );
    return SitePluginBookshelfImportJob.fromJson(_map(payload));
  }

  Future<SitePluginBookshelfImportJob> fetchSitePluginBookshelfImport(
    String pluginId,
    String jobId,
  ) async {
    final encodedId = Uri.encodeComponent(pluginId);
    final encodedJobId = Uri.encodeComponent(jobId);
    final payload = _decode(
      await _request(
        'GET',
        '/plugins/$encodedId/bookshelf/import-jobs/$encodedJobId',
      ),
    );
    return SitePluginBookshelfImportJob.fromJson(_map(payload));
  }

  Future<BookSource> saveSourceEnabled(String sourceId, bool enabled) async {
    final payload = _decode(
      await _request(
        'PUT',
        '/sources/${Uri.encodeComponent(sourceId)}/enabled',
        body: <String, dynamic>{'enabled': enabled},
      ),
    );
    return BookSource.fromJson(_map(payload));
  }

  Future<List<SourceSearchResult>> searchSources(String keyword,
      {List<String>? sourceIds}) async {
    final payload = _decode(
      await _request(
        'POST',
        '/sources/search',
        body: <String, dynamic>{
          'keyword': keyword,
          'sourceIds': sourceIds,
          'limit': 60
        },
      ),
    );
    return _list(payload).map(SourceSearchResult.fromJson).toList();
  }

  Future<List<SourceSearchResult>> searchBuiltinSite(
    String keyword, {
    required String sourceId,
    required String sourceName,
    required String sourceLanguage,
    int limit = 20,
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/builtin-sites/search',
        body: <String, dynamic>{
          'sourceId': sourceId,
          'keyword': keyword,
          'limit': limit,
        },
      ),
    );
    return _list(payload).map((item) {
      final result = _map(item);
      return SourceSearchResult.fromJson(<String, dynamic>{
        ...result,
        'sourceId': sourceId,
        'sourceName': sourceName,
        'sourceLanguage': sourceLanguage,
      });
    }).toList();
  }

  Future<SourceImportResult> importSourcesFromUrl(String url) async {
    final payload = _decode(await _request('POST', '/sources/import-url',
        body: <String, dynamic>{'url': url}));
    return SourceImportResult.fromJson(_map(payload));
  }

  Future<SourceImportResult> importSourcesFromText(String content) async {
    final payload = _decode(await _request('POST', '/sources/import-text',
        body: <String, dynamic>{'content': content}));
    return SourceImportResult.fromJson(_map(payload));
  }

  Future<List<BookTask>> fetchTasks() async {
    final payload = _decode(await _request('GET', '/tasks'));
    return _list(payload).map(BookTask.fromJson).toList();
  }

  Future<List<TaskPageResult>> fetchTaskPageResults(
    String taskId, {
    int after = 0,
  }) async {
    final payload = _decode(
      await _request('GET', '/tasks/$taskId/page-results?after=$after'),
    );
    return _list(payload).map(TaskPageResult.fromJson).toList();
  }

  Future<BookTask> enqueueTask(
      String bookId, String action, List<int> chapters) async {
    final payload = _decode(
      await _request(
        'POST',
        '/books/$bookId/chapters/$action',
        body: <String, dynamic>{'chapterIndexes': chapters},
      ),
    );
    return BookTask.fromJson(_map(payload));
  }

  Future<JsonMap> exportChapter({
    required String bookId,
    required int chapterIndex,
    required String format,
    required String targetPath,
    void Function(int receivedBytes, int totalBytes)? onProgress,
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/books/$bookId/chapters/$chapterIndex/export',
        body: <String, dynamic>{
          'format': format,
        },
      ),
    );
    final result = _map(payload);
    await _downloadArtifact(result, targetPath, onProgress: onProgress);
    return <String, dynamic>{...result, 'localFilePath': targetPath};
  }

  Future<JsonMap> exportBook({
    required String bookId,
    required List<int> chapterIndexes,
    required String format,
    required String targetPath,
    void Function(int receivedBytes, int totalBytes)? onProgress,
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/books/$bookId/export',
        body: <String, dynamic>{
          'format': format,
          'chapterIndexes': chapterIndexes,
        },
      ),
    );
    final result = _map(payload);
    await _downloadArtifact(result, targetPath, onProgress: onProgress);
    return <String, dynamic>{...result, 'localFilePath': targetPath};
  }

  Future<BookTask> retryTask(String taskId) async {
    final payload = _decode(await _request('POST', '/tasks/$taskId/retry'));
    return BookTask.fromJson(_map(payload));
  }

  Future<TranslationSettings> fetchSettings() async {
    final payload = _decode(await _request('GET', '/settings'));
    return TranslationSettings.fromJson(_map(payload));
  }

  Future<TranslationSettings> saveSettings(TranslationSettings settings) async {
    final payload =
        _decode(await _request('PUT', '/settings', body: settings.toJson()));
    return TranslationSettings.fromJson(_map(payload));
  }

  String resolveUrl(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty ||
        trimmed.startsWith('http://') ||
        trimmed.startsWith('https://')) {
      return trimmed;
    }
    return '${_baseUrl().replaceAll(RegExp(r'/+$'), '')}$_apiPrefix/${trimmed.replaceFirst(RegExp(r'^/+'), '')}';
  }

  Map<String, String> headersForUrl(String value) {
    final resolved = Uri.parse(resolveUrl(value));
    final backendBase = _baseUrl().replaceAll(RegExp(r'/+$'), '');
    final backend = Uri.parse(backendBase);
    final apiRoot = Uri.parse('$backendBase$_apiPrefix/');
    final sameOrigin = resolved.scheme == backend.scheme &&
        resolved.host == backend.host &&
        resolved.port == backend.port &&
        resolved.path.startsWith(apiRoot.path);
    return sameOrigin ? _headers() : const <String, String>{};
  }

  Future<void> _downloadArtifact(
    JsonMap artifact,
    String targetPath, {
    void Function(int receivedBytes, int totalBytes)? onProgress,
  }) async {
    final downloadUrl = artifact['downloadUrl'] as String? ?? '';
    if (downloadUrl.isEmpty) {
      throw const ApiException('后端未返回导出下载地址');
    }
    final target = File(targetPath);
    final temporary = File('$targetPath.qingjuan-part');
    await temporary.parent.create(recursive: true);
    try {
      final request = http.Request('GET', Uri.parse(resolveUrl(downloadUrl)))
        ..headers.addAll(headersForUrl(downloadUrl));
      final response =
          await _client.send(request).timeout(const Duration(minutes: 2));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final decoded = await http.Response.fromStream(response);
        _decode(decoded);
      }
      final sink = temporary.openWrite();
      final totalBytes = response.contentLength ??
          (artifact['sizeBytes'] as num?)?.toInt() ??
          0;
      var receivedBytes = 0;
      try {
        await for (final chunk
            in response.stream.timeout(const Duration(minutes: 2))) {
          sink.add(chunk);
          receivedBytes += chunk.length;
          onProgress?.call(receivedBytes, totalBytes);
        }
      } finally {
        await sink.close();
      }
      if (await target.exists()) await target.delete();
      await temporary.rename(target.path);
    } catch (_) {
      if (await temporary.exists()) await temporary.delete();
      rethrow;
    }
  }

  void close() => _client.close();
}
