import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/shared/motion.dart';

void main() {
  testWidgets('page switcher animates only the incoming page', (
    tester,
  ) async {
    final page = ValueNotifier<int>(0);
    addTearDown(page.dispose);

    await tester.pumpWidget(
      _MotionHarness(
        child: ValueListenableBuilder<int>(
          valueListenable: page,
          builder: (context, value, _) => QjPageSwitcher(
            pageKey: value,
            child: Center(child: Text('页面 $value')),
          ),
        ),
      ),
    );

    final switcher = tester.widget<TweenAnimationBuilder<double>>(
      find.byType(TweenAnimationBuilder<double>),
    );
    expect(switcher.duration, const Duration(milliseconds: 170));

    page.value = 1;
    await tester.pump();

    expect(find.text('页面 0'), findsNothing);
    expect(find.text('页面 1'), findsOneWidget);

    await tester.pumpAndSettle();
    expect(find.text('页面 0'), findsNothing);
    expect(find.text('页面 1'), findsOneWidget);
  });

  testWidgets('reduced motion removes shared switch and route durations', (
    tester,
  ) async {
    late Duration resolvedDuration;
    late PageRoute<void> route;

    await tester.pumpWidget(
      _MotionHarness(
        disableAnimations: true,
        child: Builder(
          builder: (context) {
            resolvedDuration = QjMotion.duration(context);
            route = qjPageRoute<void>(
              context: context,
              builder: (_) => const Text('下一页'),
            );
            return const QjPageSwitcher(
              pageKey: 'current',
              child: Text('当前页'),
            );
          },
        ),
      ),
    );

    expect(resolvedDuration, Duration.zero);
    expect(route.transitionDuration, Duration.zero);
    expect(route.reverseTransitionDuration, Duration.zero);
    expect(find.byType(TweenAnimationBuilder<double>), findsNothing);
    expect(find.text('当前页'), findsOneWidget);
  });
}

class _MotionHarness extends StatelessWidget {
  const _MotionHarness({
    required this.child,
    this.disableAnimations = false,
  });

  final Widget child;
  final bool disableAnimations;

  @override
  Widget build(BuildContext context) {
    return FluentApp(
      theme: buildQingJuanTheme(
        Brightness.light,
        platform: TargetPlatform.windows,
      ),
      home: MediaQuery(
        data: MediaQueryData(
          size: const Size(1280, 800),
          disableAnimations: disableAnimations,
        ),
        child: child,
      ),
    );
  }
}
