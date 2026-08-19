import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/shared/app_surface.dart';

void main() {
  testWidgets('surface hover animation respects reduced motion',
      (tester) async {
    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(Brightness.light),
        home: const MediaQuery(
          data: MediaQueryData(disableAnimations: true),
          child: AppSurface(
            onPressed: _noop,
            child: Text('可点击卡片'),
          ),
        ),
      ),
    );

    final container = tester.widget<AnimatedContainer>(
      find.byType(AnimatedContainer),
    );
    expect(container.duration, Duration.zero);
  });

  testWidgets('static mobile surface avoids an idle implicit animation',
      (tester) async {
    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(Brightness.light),
        home: const AppSurface(
          key: ValueKey('static-mobile-surface'),
          child: Text('静态卡片'),
        ),
      ),
    );

    expect(
      find.descendant(
        of: find.byKey(const ValueKey('static-mobile-surface')),
        matching: find.byType(AnimatedContainer),
      ),
      findsNothing,
    );
  });
}

void _noop() {}
