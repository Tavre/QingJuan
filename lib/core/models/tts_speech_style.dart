enum TtsSpeechStyle { natural, gentle, immersive, lively, calm }

extension TtsSpeechStyleDetails on TtsSpeechStyle {
  String get label => switch (this) {
        TtsSpeechStyle.natural => '自然叙述',
        TtsSpeechStyle.gentle => '温柔陪伴',
        TtsSpeechStyle.immersive => '沉浸小说',
        TtsSpeechStyle.lively => '活力对白',
        TtsSpeechStyle.calm => '安静夜读',
      };

  String get description => switch (this) {
        TtsSpeechStyle.natural => '均衡、克制，适合长时间听书',
        TtsSpeechStyle.gentle => '稍慢且柔和，减少听觉疲劳',
        TtsSpeechStyle.immersive => '根据对白和标点动态调整语调',
        TtsSpeechStyle.lively => '节奏更轻快，对话更有起伏',
        TtsSpeechStyle.calm => '低缓、留白更多，适合夜间收听',
      };

  double get defaultRate => switch (this) {
        TtsSpeechStyle.natural => 0.47,
        TtsSpeechStyle.gentle => 0.42,
        TtsSpeechStyle.immersive => 0.45,
        TtsSpeechStyle.lively => 0.52,
        TtsSpeechStyle.calm => 0.38,
      };

  double get basePitch => switch (this) {
        TtsSpeechStyle.natural => 1,
        TtsSpeechStyle.gentle => 1.01,
        TtsSpeechStyle.immersive => 0.98,
        TtsSpeechStyle.lively => 1.03,
        TtsSpeechStyle.calm => 0.96,
      };

  bool get usesDynamicProsody =>
      this == TtsSpeechStyle.immersive || this == TtsSpeechStyle.lively;

  double pitchFor(String text) {
    var pitch = basePitch;
    if (!usesDynamicProsody) return pitch;
    final trimmed = text.trim();
    if (_looksLikeDialogue(trimmed)) pitch += 0.025;
    if (trimmed.endsWith('？') || trimmed.endsWith('?')) pitch += 0.035;
    if (trimmed.endsWith('！') || trimmed.endsWith('!')) pitch += 0.045;
    if (trimmed.endsWith('……') || trimmed.endsWith('…')) pitch -= 0.025;
    return pitch.clamp(0.85, 1.15);
  }

  double rateFor(String text, double selectedRate) {
    if (!usesDynamicProsody) return selectedRate;
    final trimmed = text.trim();
    var rate = selectedRate;
    if (_looksLikeDialogue(trimmed)) rate += 0.015;
    if (trimmed.endsWith('！') || trimmed.endsWith('!')) rate += 0.025;
    if (trimmed.endsWith('……') || trimmed.endsWith('…')) rate -= 0.035;
    return rate.clamp(0.2, 1);
  }

  Duration pauseAfter(String text) {
    final trimmed = text.trim();
    if (trimmed.endsWith('……') || trimmed.endsWith('…')) {
      return const Duration(milliseconds: 180);
    }
    if (trimmed.endsWith('。') ||
        trimmed.endsWith('！') ||
        trimmed.endsWith('？') ||
        trimmed.endsWith('.') ||
        trimmed.endsWith('!') ||
        trimmed.endsWith('?')) {
      return Duration(milliseconds: this == TtsSpeechStyle.calm ? 140 : 80);
    }
    return Duration(milliseconds: this == TtsSpeechStyle.calm ? 90 : 40);
  }
}

TtsSpeechStyle parseTtsSpeechStyle(String? value) =>
    TtsSpeechStyle.values.firstWhere(
      (style) => style.name == value,
      orElse: () => TtsSpeechStyle.natural,
    );

bool _looksLikeDialogue(String text) {
  if (text.isEmpty) return false;
  return text.startsWith('“') ||
      text.startsWith('「') ||
      text.startsWith('『') ||
      text.startsWith('"') ||
      text.contains('： “') ||
      text.contains('：“');
}
