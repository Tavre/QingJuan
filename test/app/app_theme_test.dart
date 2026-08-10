import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';

void main() {
  test('theme uses responsive desktop motion timings', () {
    final theme = buildQingJuanTheme(Brightness.light);

    expect(theme.fasterAnimationDuration, const Duration(milliseconds: 60));
    expect(theme.fastAnimationDuration, const Duration(milliseconds: 110));
    expect(theme.mediumAnimationDuration, const Duration(milliseconds: 170));
    expect(theme.slowAnimationDuration, const Duration(milliseconds: 240));
    expect(theme.animationCurve, Curves.easeOutCubic);
    expect(
      theme.navigationPaneTheme.animationDuration,
      const Duration(milliseconds: 110),
    );
  });
}
