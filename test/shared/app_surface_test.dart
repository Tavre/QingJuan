import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/shared/app_surface.dart';
import 'package:qingjuan/shared/responsive.dart';

void main() {
  testWidgets('surface hover animation respects reduced motion',
      (tester) async {
    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(Brightness.light),
        home: const MediaQuery(
          data: MediaQueryData(disableAnimations: true),
          child: UiPlatformScope(
            platform: TargetPlatform.windows,
            child: AppSurface(
              onPressed: _noop,
              child: Text('可点击卡片'),
            ),
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

  testWidgets('glass surface clips and bounds its backdrop blur',
      (tester) async {
    await tester.pumpWidget(_glassHarness());

    final glassFinder = find.byKey(const ValueKey('test-glass-surface'));
    expect(
      find.descendant(
        of: glassFinder,
        matching: find.byType(RepaintBoundary),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: glassFinder,
        matching: find.byType(BackdropFilter),
      ),
      findsOneWidget,
    );
    final clip = tester.widget<ClipRRect>(
      find.descendant(
        of: glassFinder,
        matching: find.byType(ClipRRect),
      ),
    );
    expect(clip.borderRadius, BorderRadius.circular(22));
  });

  testWidgets('glass surface falls back to opaque in high contrast mode',
      (tester) async {
    await tester.pumpWidget(_glassHarness(highContrast: true));

    expect(
      find.descendant(
        of: find.byKey(const ValueKey('test-glass-surface')),
        matching: find.byType(BackdropFilter),
      ),
      findsNothing,
    );
  });
}

Widget _glassHarness({bool highContrast = false}) {
  return FluentApp(
    theme: buildQingJuanTheme(
      Brightness.light,
      platform: TargetPlatform.android,
    ),
    home: MediaQuery(
      data: MediaQueryData(highContrast: highContrast),
      child: const Center(
        child: SizedBox(
          width: 300,
          height: 68,
          child: AppGlassSurface(
            key: ValueKey('test-glass-surface'),
            child: Text('玻璃表面'),
          ),
        ),
      ),
    ),
  );
}

void _noop() {}
