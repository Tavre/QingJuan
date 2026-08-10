import 'book.dart';

class TranslationModelSettings {
  const TranslationModelSettings({
    required this.enabled,
    required this.baseUrl,
    required this.apiKey,
    required this.model,
    required this.supportsVision,
    required this.apiKeyConfigured,
    this.clearApiKey = false,
  });

  factory TranslationModelSettings.fromJson(JsonMap json) =>
      TranslationModelSettings(
        enabled: json['enabled'] as bool? ?? false,
        baseUrl: json['baseUrl'] as String? ?? 'https://api.openai.com/v1',
        apiKey: json['apiKey'] as String? ?? '',
        model: json['model'] as String? ?? 'gpt-5.4',
        supportsVision: json['supportsVision'] as bool? ?? false,
        apiKeyConfigured: json['apiKeyConfigured'] as bool? ?? false,
      );

  const TranslationModelSettings.defaults()
      : enabled = false,
        baseUrl = 'https://api.openai.com/v1',
        apiKey = '',
        model = 'gpt-5.4',
        supportsVision = false,
        apiKeyConfigured = false,
        clearApiKey = false;

  JsonMap toJson() => <String, dynamic>{
        'enabled': enabled,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'apiKeyAction': clearApiKey
            ? 'clear'
            : (apiKey.trim().isEmpty ? 'keep' : 'replace'),
        'model': model,
        'supportsVision': supportsVision,
      };

  TranslationModelSettings copyWith({
    bool? enabled,
    String? baseUrl,
    String? apiKey,
    String? model,
    bool? supportsVision,
    bool? apiKeyConfigured,
    bool? clearApiKey,
  }) =>
      TranslationModelSettings(
        enabled: enabled ?? this.enabled,
        baseUrl: baseUrl ?? this.baseUrl,
        apiKey: apiKey ?? this.apiKey,
        model: model ?? this.model,
        supportsVision: supportsVision ?? this.supportsVision,
        apiKeyConfigured: apiKeyConfigured ?? this.apiKeyConfigured,
        clearApiKey: clearApiKey ?? this.clearApiKey,
      );

  final bool enabled;
  final String baseUrl;
  final String apiKey;
  final String model;
  final bool supportsVision;
  final bool apiKeyConfigured;
  final bool clearApiKey;
}

class TranslationSettings {
  const TranslationSettings({
    required this.systemPrompt,
    required this.autoTranslateNextChapters,
    required this.downloadConcurrency,
    required this.translationModel,
    required this.mangaOcr,
    required this.bika,
  });

  factory TranslationSettings.fromJson(JsonMap json) {
    final rawTranslationModel = json['translationModel'] as JsonMap?;
    final rawProviders = (json['providers'] as JsonMap?) ?? const {};
    final selectedProvider = json['defaultProvider'] as String? ?? 'openai';
    final legacySelected = rawProviders[selectedProvider] as JsonMap?;
    final legacyOpenAi = rawProviders['openai'] as JsonMap?;
    final migratedTranslationModel = rawTranslationModel ??
        (selectedProvider != 'anthropic' ? legacySelected : null) ??
        legacyOpenAi ??
        const <String, dynamic>{};
    return TranslationSettings(
      systemPrompt: json['systemPrompt'] as String? ?? '',
      autoTranslateNextChapters:
          (json['autoTranslateNextChapters'] as num?)?.toInt() ?? 2,
      downloadConcurrency: (json['downloadConcurrency'] as num?)?.toInt() ?? 4,
      translationModel:
          TranslationModelSettings.fromJson(migratedTranslationModel),
      mangaOcr: (json['mangaOcr'] as JsonMap?) ?? <String, dynamic>{},
      bika: (json['bika'] as JsonMap?) ?? <String, dynamic>{},
    );
  }

  factory TranslationSettings.defaults() => const TranslationSettings(
        systemPrompt: '请准确翻译并保留原文段落结构。',
        autoTranslateNextChapters: 2,
        downloadConcurrency: 4,
        translationModel: TranslationModelSettings.defaults(),
        mangaOcr: <String, dynamic>{
          'enabled': false,
          'baseUrl': '',
          'apiKey': ''
        },
        bika: <String, dynamic>{'email': '', 'password': ''},
      );

  JsonMap toJson() => <String, dynamic>{
        'systemPrompt': systemPrompt,
        'autoTranslateNextChapters': autoTranslateNextChapters,
        'downloadConcurrency': downloadConcurrency,
        'translationModel': translationModel.toJson(),
        'mangaOcr': mangaOcr,
        'bika': bika,
      };

  TranslationSettings copyWith({
    String? systemPrompt,
    int? autoTranslateNextChapters,
    int? downloadConcurrency,
    TranslationModelSettings? translationModel,
  }) =>
      TranslationSettings(
        systemPrompt: systemPrompt ?? this.systemPrompt,
        autoTranslateNextChapters:
            autoTranslateNextChapters ?? this.autoTranslateNextChapters,
        downloadConcurrency: downloadConcurrency ?? this.downloadConcurrency,
        translationModel: translationModel ?? this.translationModel,
        mangaOcr: mangaOcr,
        bika: bika,
      );

  final String systemPrompt;
  final int autoTranslateNextChapters;
  final int downloadConcurrency;
  final TranslationModelSettings translationModel;
  final JsonMap mangaOcr;
  final JsonMap bika;
}
