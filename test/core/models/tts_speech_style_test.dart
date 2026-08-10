import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/tts_speech_style.dart';

void main() {
  test('immersive style varies dialogue and punctuation prosody', () {
    const style = TtsSpeechStyle.immersive;

    expect(style.pitchFor('普通叙述。'), style.basePitch);
    expect(style.pitchFor('“你要去哪儿？”'), greaterThan(style.basePitch));
    expect(
      style.rateFor('他沉默了……', style.defaultRate),
      lessThan(style.defaultRate),
    );
  });

  test('unknown persisted style falls back to natural narration', () {
    expect(parseTtsSpeechStyle('missing'), TtsSpeechStyle.natural);
  });
}
