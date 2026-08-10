import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../models/book.dart';
import '../models/link_job.dart';
import '../models/settings.dart';
import '../models/source.dart';
import '../models/task.dart';
import 'api_exception.dart';

class ApiClient {
  ApiClient(this._baseUrl, {http.Client? client})
      : _client = client ?? http.Client();

  final String Function() _baseUrl;
  final http.Client _client;

  Uri _uri(String endpoint, [Map<String, dynamic>? query]) {
    final base = _baseUrl().replaceAll(RegExp(r'/+$'), '');
    return Uri.parse('$base$endpoint').replace(
      queryParameters: query?.map((key, value) => MapEntry(key, '$value')),
    );
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
        final headers = body == null
            ? null
            : <String, String>{'Content-Type': 'application/json'};
        final encoded = body == null ? null : jsonEncode(body);
        final response = switch (method) {
          'GET' => await _client.get(uri),
          'POST' => await _client.post(uri, headers: headers, body: encoded),
          'PUT' => await _client.put(uri, headers: headers, body: encoded),
          'DELETE' =>
            await _client.delete(uri, headers: headers, body: encoded),
          _ => throw UnsupportedError('Unsupported HTTP method: $method'),
        };
        return response;
      } on SocketException catch (error) {
        lastError = error;
      } on http.ClientException catch (error) {
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
          .get(_uri('/health'))
          .timeout(const Duration(seconds: 2));
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
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
  }) async {
    final request = http.MultipartRequest('POST', _uri('/books/import-local'))
      ..fields['bookKind'] = kind
      ..fields['language'] = language
      ..fields['needTranslation'] = '$translate';
    if (title != null && title.trim().isNotEmpty) {
      request.fields['title'] = title.trim();
    }
    request.files.add(
      await http.MultipartFile.fromPath('file', filePath),
    );
    final streamed = await _client.send(request);
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
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/books/$bookId/chapters/$chapterIndex/export',
        body: <String, dynamic>{
          'format': format,
          'targetPath': targetPath,
        },
      ),
    );
    return _map(payload);
  }

  Future<JsonMap> exportBook({
    required String bookId,
    required List<int> chapterIndexes,
    required String format,
    required String targetPath,
  }) async {
    final payload = _decode(
      await _request(
        'POST',
        '/books/$bookId/export',
        body: <String, dynamic>{
          'format': format,
          'targetPath': targetPath,
          'chapterIndexes': chapterIndexes,
        },
      ),
    );
    return _map(payload);
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
    return '${_baseUrl().replaceAll(RegExp(r'/+$'), '')}/${trimmed.replaceFirst(RegExp(r'^/+'), '')}';
  }

  void close() => _client.close();
}
