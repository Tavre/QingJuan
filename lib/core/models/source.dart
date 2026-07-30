import 'book.dart';

class BookSource {
  const BookSource({
    required this.id,
    required this.name,
    required this.baseUrl,
    required this.description,
    required this.enabled,
    required this.supported,
    required this.status,
    required this.statusMessage,
    required this.tags,
  });

  factory BookSource.fromJson(JsonMap json) => BookSource(
        id: json['id'] as String? ?? '',
        name: json['name'] as String? ?? '未命名书源',
        baseUrl: json['baseUrl'] as String? ?? '',
        description: json['description'] as String? ?? '',
        enabled: json['enabled'] as bool? ?? true,
        supported: json['supported'] as bool? ?? false,
        status: json['status'] as String? ?? 'unknown',
        statusMessage: json['statusMessage'] as String? ?? '',
        tags:
            ((json['tags'] as List?) ?? const []).whereType<String>().toList(),
      );

  final String id;
  final String name;
  final String baseUrl;
  final String description;
  final bool enabled;
  final bool supported;
  final String status;
  final String statusMessage;
  final List<String> tags;
}

class SourceSearchResult {
  const SourceSearchResult({
    required this.title,
    required this.author,
    required this.synopsis,
    required this.sourceUrl,
    required this.sourceId,
    required this.sourceName,
    required this.kind,
    required this.language,
    this.cover,
  });

  factory SourceSearchResult.fromJson(JsonMap json) => SourceSearchResult(
        title: json['title'] as String? ?? '未命名作品',
        author: json['author'] as String? ?? '',
        synopsis: json['synopsis'] as String? ?? '',
        sourceUrl: json['sourceUrl'] as String? ?? '',
        sourceId: json['sourceId'] as String? ?? '',
        sourceName: json['sourceName'] as String? ?? '',
        kind: json['bookKind'] as String? ?? '长小说',
        language: json['sourceLanguage'] as String? ?? '中文',
        cover: json['cover'] as String?,
      );

  JsonMap toImportPayload({bool translate = false}) => <String, dynamic>{
        'sourceUrl': sourceUrl,
        'bookKind': kind,
        'title': title,
        'language': language,
        'needTranslation': translate,
        'sourceId': sourceId,
        'synopsis': synopsis,
        'cover': cover,
      };

  final String title;
  final String author;
  final String synopsis;
  final String sourceUrl;
  final String sourceId;
  final String sourceName;
  final String kind;
  final String language;
  final String? cover;
}

class SourceImportResult {
  const SourceImportResult({
    required this.imported,
    required this.updated,
    required this.duplicates,
    required this.ignored,
  });

  factory SourceImportResult.fromJson(JsonMap json) => SourceImportResult(
        imported: ((json['imported'] as List?) ?? const [])
            .whereType<JsonMap>()
            .map(BookSource.fromJson)
            .toList(),
        updated: ((json['updated'] as List?) ?? const [])
            .whereType<JsonMap>()
            .map(BookSource.fromJson)
            .toList(),
        duplicates: ((json['duplicates'] as List?) ?? const [])
            .whereType<String>()
            .toList(),
        ignored: ((json['ignored'] as List?) ?? const [])
            .whereType<String>()
            .toList(),
      );

  final List<BookSource> imported;
  final List<BookSource> updated;
  final List<String> duplicates;
  final List<String> ignored;
}
