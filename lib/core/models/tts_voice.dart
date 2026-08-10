class TtsVoice {
  const TtsVoice({
    required this.name,
    required this.locale,
    this.gender = '',
    this.identifier = '',
  });

  factory TtsVoice.fromJson(Map<String, dynamic> json) => TtsVoice(
        name: _stringValue(json['name']),
        locale: _stringValue(json['locale']),
        gender: _stringValue(json['gender']),
        identifier: _stringValue(json['identifier']),
      );

  static TtsVoice? tryFromPluginValue(Object? value) {
    if (value is! Map) return null;
    final name = '${value['name'] ?? ''}'.trim();
    final locale = '${value['locale'] ?? ''}'.trim();
    if (name.isEmpty || locale.isEmpty) return null;
    return TtsVoice(
      name: name,
      locale: locale,
      gender: '${value['gender'] ?? ''}'.trim().toLowerCase(),
      identifier: '${value['identifier'] ?? ''}'.trim(),
    );
  }

  final String name;
  final String locale;
  final String gender;
  final String identifier;

  String get stableKey =>
      identifier.isNotEmpty ? identifier : '${locale.toLowerCase()}|$name';

  String get localeLabel => switch (locale.toLowerCase()) {
        'zh-cn' => '简体中文',
        'zh-hans' => '简体中文',
        'zh-tw' => '繁体中文',
        'zh-hk' => '粤语（香港）',
        'en-us' => '英语（美国）',
        'en-gb' => '英语（英国）',
        'ja-jp' => '日语',
        'ko-kr' => '韩语',
        _ => locale,
      };

  String get genderLabel => switch (gender) {
        'female' => '女声',
        'male' => '男声',
        _ => '未知声线',
      };

  String get description => '$localeLabel · $genderLabel';

  bool get isNatural {
    final searchable = '$name $identifier'.toLowerCase();
    return const <String>['natural', 'neural', 'online']
        .any(searchable.contains);
  }

  String get qualityLabel => isNatural ? '自然声线' : '标准声线';

  String get previewText {
    final language = locale.toLowerCase().split('-').first;
    return switch (language) {
      'en' => 'Hello, this is a voice preview from QingJuan.',
      'ja' => 'こんにちは、青巻の音声プレビューです。',
      'ko' => '안녕하세요. 청권 음성 미리 듣기입니다.',
      _ => '你好，这是青卷的声音试听。愿阅读常伴你左右。',
    };
  }

  Map<String, String> get pluginValue => <String, String>{
        'name': name,
        'locale': locale,
      };

  Map<String, dynamic> toJson() => <String, dynamic>{
        'name': name,
        'locale': locale,
        'gender': gender,
        'identifier': identifier,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is TtsVoice &&
          name == other.name &&
          locale == other.locale &&
          gender == other.gender &&
          identifier == other.identifier;

  @override
  int get hashCode => Object.hash(name, locale, gender, identifier);
}

String _stringValue(Object? value) => value is String ? value : '';

List<TtsVoice> parseTtsVoices(Object? rawVoices) {
  if (rawVoices is! Iterable) return const <TtsVoice>[];
  final byKey = <String, TtsVoice>{};
  for (final rawVoice in rawVoices) {
    final voice = TtsVoice.tryFromPluginValue(rawVoice);
    if (voice != null) byKey[voice.stableKey] = voice;
  }
  final voices = byKey.values.toList()
    ..sort((left, right) {
      if (left.isNatural != right.isNatural) return left.isNatural ? -1 : 1;
      final localeOrder = left.locale.compareTo(right.locale);
      if (localeOrder != 0) return localeOrder;
      return left.name.compareTo(right.name);
    });
  return List<TtsVoice>.unmodifiable(voices);
}
