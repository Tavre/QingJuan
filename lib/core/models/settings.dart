import 'book.dart';

const providerKeys = <String>[
  'openai',
  'newapi',
  'anthropic',
  'grok2api',
  'custom'
];

class ProviderSettings {
  const ProviderSettings({
    required this.enabled,
    required this.baseUrl,
    required this.apiKey,
    required this.model,
  });

  factory ProviderSettings.fromJson(JsonMap json) => ProviderSettings(
        enabled: json['enabled'] as bool? ?? false,
        baseUrl: json['baseUrl'] as String? ?? '',
        apiKey: json['apiKey'] as String? ?? '',
        model: json['model'] as String? ?? '',
      );

  const ProviderSettings.empty()
      : enabled = false,
        baseUrl = '',
        apiKey = '',
        model = '';

  JsonMap toJson() => <String, dynamic>{
        'enabled': enabled,
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'model': model,
      };

  ProviderSettings copyWith({
    bool? enabled,
    String? baseUrl,
    String? apiKey,
    String? model,
  }) =>
      ProviderSettings(
        enabled: enabled ?? this.enabled,
        baseUrl: baseUrl ?? this.baseUrl,
        apiKey: apiKey ?? this.apiKey,
        model: model ?? this.model,
      );

  final bool enabled;
  final String baseUrl;
  final String apiKey;
  final String model;
}

class TranslationSettings {
  const TranslationSettings({
    required this.defaultProvider,
    required this.systemPrompt,
    required this.autoTranslateNextChapters,
    required this.downloadConcurrency,
    required this.providers,
    required this.mangaOcr,
    required this.bika,
  });

  factory TranslationSettings.fromJson(JsonMap json) {
    final rawProviders = (json['providers'] as JsonMap?) ?? const {};
    return TranslationSettings(
      defaultProvider: json['defaultProvider'] as String? ?? 'openai',
      systemPrompt: json['systemPrompt'] as String? ?? '',
      autoTranslateNextChapters:
          (json['autoTranslateNextChapters'] as num?)?.toInt() ?? 2,
      downloadConcurrency: (json['downloadConcurrency'] as num?)?.toInt() ?? 4,
      providers: <String, ProviderSettings>{
        for (final key in providerKeys)
          key: ProviderSettings.fromJson(
              (rawProviders[key] as JsonMap?) ?? const {}),
      },
      mangaOcr: (json['mangaOcr'] as JsonMap?) ?? <String, dynamic>{},
      bika: (json['bika'] as JsonMap?) ?? <String, dynamic>{},
    );
  }

  factory TranslationSettings.defaults() => TranslationSettings(
        defaultProvider: 'openai',
        systemPrompt: '请准确翻译并保留原文段落结构。',
        autoTranslateNextChapters: 2,
        downloadConcurrency: 4,
        providers: <String, ProviderSettings>{
          for (final key in providerKeys) key: const ProviderSettings.empty(),
        },
        mangaOcr: <String, dynamic>{
          'enabled': false,
          'baseUrl': '',
          'apiKey': ''
        },
        bika: <String, dynamic>{'email': '', 'password': ''},
      );

  JsonMap toJson() => <String, dynamic>{
        'defaultProvider': defaultProvider,
        'systemPrompt': systemPrompt,
        'autoTranslateNextChapters': autoTranslateNextChapters,
        'downloadConcurrency': downloadConcurrency,
        'providers':
            providers.map((key, value) => MapEntry(key, value.toJson())),
        'mangaOcr': mangaOcr,
        'bika': bika,
      };

  TranslationSettings copyWith({
    String? defaultProvider,
    String? systemPrompt,
    int? autoTranslateNextChapters,
    int? downloadConcurrency,
    Map<String, ProviderSettings>? providers,
  }) =>
      TranslationSettings(
        defaultProvider: defaultProvider ?? this.defaultProvider,
        systemPrompt: systemPrompt ?? this.systemPrompt,
        autoTranslateNextChapters:
            autoTranslateNextChapters ?? this.autoTranslateNextChapters,
        downloadConcurrency: downloadConcurrency ?? this.downloadConcurrency,
        providers: providers ?? this.providers,
        mangaOcr: mangaOcr,
        bika: bika,
      );

  final String defaultProvider;
  final String systemPrompt;
  final int autoTranslateNextChapters;
  final int downloadConcurrency;
  final Map<String, ProviderSettings> providers;
  final JsonMap mangaOcr;
  final JsonMap bika;
}
